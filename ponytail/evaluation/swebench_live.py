"""Leak-safe SWE-bench-Live task and official-evaluator adapter."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import time
from pathlib import Path

from .minimal_change_experiment import (
    TASK_EXECUTION_CONTRACT,
    YAGNI_NOTICE,
    _build_agent,
    _file_snapshot,
    _write_patch,
)
from .context_cost import _usage_from_trace


PUBLIC_TASK_SCHEMA_VERSION = 1
MODEL_VISIBLE_FIELDS = (
    "instance_id",
    "repo",
    "base_commit",
    "problem_statement",
)
EVALUATOR_ONLY_FIELDS = frozenset(
    {
        "patch",
        "test_patch",
        "FAIL_TO_PASS",
        "PASS_TO_PASS",
        "gold_patch",
    }
)


def project_model_task(record: dict) -> dict:
    """Return the only SWE-bench fields that may enter the Runtime."""
    if not isinstance(record, dict):
        raise ValueError("SWE-bench-Live task must be a mapping")
    missing = [field for field in MODEL_VISIBLE_FIELDS if field not in record]
    if missing:
        raise ValueError(f"SWE-bench-Live task is missing fields: {', '.join(missing)}")
    projected = {field: str(record[field]).strip() for field in MODEL_VISIBLE_FIELDS}
    if not projected["instance_id"]:
        raise ValueError("instance_id must not be empty")
    if "/" not in projected["repo"]:
        raise ValueError("repo must use owner/name form")
    commit = projected["base_commit"].lower()
    if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        raise ValueError("base_commit must be a full commit SHA")
    projected["base_commit"] = commit
    if not projected["problem_statement"]:
        raise ValueError("problem_statement must not be empty")
    return projected


def assert_no_evaluator_data(value) -> None:
    """Reject evaluator-only fields from any model-side serialized object."""
    if isinstance(value, dict):
        leaked = sorted(EVALUATOR_ONLY_FIELDS.intersection(value))
        if leaked:
            raise ValueError(f"evaluator-only fields are not allowed: {', '.join(leaked)}")
        for item in value.values():
            assert_no_evaluator_data(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_evaluator_data(item)


def load_public_tasks(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    assert_no_evaluator_data(data)
    if data.get("schema_version") != PUBLIC_TASK_SCHEMA_VERSION:
        raise ValueError("unsupported SWE-bench-Live public task schema_version")
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("SWE-bench-Live public task suite must contain tasks")
    seen = set()
    normalized = []
    allowed = set(MODEL_VISIBLE_FIELDS)
    for task in tasks:
        extra = sorted(set(task) - allowed)
        if extra:
            raise ValueError(f"public task contains unsupported fields: {', '.join(extra)}")
        item = project_model_task(task)
        if item["instance_id"] in seen:
            raise ValueError(f"duplicate instance_id: {item['instance_id']}")
        seen.add(item["instance_id"])
        normalized.append(item)
    return {"schema_version": PUBLIC_TASK_SCHEMA_VERSION, "tasks": normalized}


def build_runtime_task(
    task: dict,
    *,
    source: str | Path,
    max_steps: int = 30,
    timeout: int = 600,
    test_image: str = "",
) -> dict:
    item = project_model_task(task)
    source = Path(source).resolve()
    if not source.is_dir():
        raise ValueError(f"source directory does not exist: {source}")
    if int(max_steps) < 1 or int(timeout) < 1:
        raise ValueError("max_steps and timeout must be positive")
    prompt = (
        f"Resolve this repository issue:\n\n{item['problem_statement']}\n\n"
        "Work only from the checked-out repository and its local tests. Do not search for the "
        "upstream issue, pull request, later commits, or reference patch."
    )
    if test_image:
        prompt += (
            "\n\nRepository dependencies are available in the frozen Linux test image. "
            "When a repository command needs that environment, run it with: "
            f"docker run --rm -v \"%CD%:/testbed\" -w /testbed {test_image} "
            'bash -lc "<repository command>". Replace only the placeholder command.'
        )
    runtime_task = {
        "task_id": item["instance_id"],
        "instance_id": item["instance_id"],
        "repo": item["repo"],
        "base_commit": item["base_commit"],
        "category": "swebench_live",
        "fixture_repo": str(source),
        "fixture_revision": item["base_commit"],
        "prompt": prompt,
        "allowed_tools": ["read_file", "patch_file", "run_shell", "search", "list_files"],
        "step_budget": int(max_steps),
        "timeout_seconds": int(timeout),
        "allowed_change_paths": [],
        "test_image": str(test_image),
        "status": "valid",
    }
    assert_no_evaluator_data(runtime_task)
    return runtime_task


def official_image_name(instance_id: str, namespace: str) -> str:
    image_id = str(instance_id).replace("__", "_1776_").lower()
    return f"{namespace}/sweb.eval.x86_64.{image_id}:latest"


def runtime_prompt(task: dict) -> str:
    return (
        f"{task['prompt']}\n\n{TASK_EXECUTION_CONTRACT} "
        "Keep all changes inside the repository and avoid unrelated refactoring.\n\n"
        f"{YAGNI_NOTICE}"
    )


def select_resume_tasks(tasks: list[dict], count: int = 2) -> list[dict]:
    """Select resume cases deterministically without using agent outcomes."""
    if int(count) < 1:
        raise ValueError("resume task count must be positive")
    ranked = sorted(
        tasks,
        key=lambda task: (
            hashlib.sha256(str(task["instance_id"]).encode("utf-8")).hexdigest(),
            str(task["instance_id"]),
        ),
    )
    return ranked[: int(count)]


def aggregate_trace_metrics(trace_paths: list[str | Path]) -> dict:
    """Aggregate attempts, tools, reads, and provider usage across Runtime processes."""
    events = []
    usage_rows = []
    for trace_path in trace_paths:
        path = Path(trace_path)
        if not path.is_file():
            continue
        events.extend(_read_jsonl(path))
        usage_rows.append(_usage_from_trace(path)["usage"])
    read_paths = [
        str((event.get("args", {}) or {}).get("path", "")).strip()
        for event in events
        if event.get("event") == "tool_executed"
        and event.get("name") == "read_file"
        and str((event.get("args", {}) or {}).get("path", "")).strip()
    ]
    usage_source = (
        "actual"
        if usage_rows and all(row.usage_source == "actual" for row in usage_rows)
        else "estimated_proxy"
    )
    return {
        "attempts": sum(event.get("event") == "model_requested" for event in events),
        "tool_steps": sum(event.get("event") == "tool_executed" for event in events),
        "read_paths": read_paths,
        "input_tokens": sum(int(row.input_tokens) for row in usage_rows),
        "cached_tokens": sum(int(row.cached_tokens) for row in usage_rows),
        "output_tokens": sum(int(row.output_tokens) for row in usage_rows),
        "total_tokens": sum(
            int(row.input_tokens) + int(row.output_tokens) for row in usage_rows
        ),
        "usage_source": usage_source,
    }


def repeated_reads_after_resume(
    before_trace: str | Path,
    resumed_trace: str | Path,
) -> dict:
    before_requests = _read_requests(before_trace)
    resumed_requests = _read_requests(resumed_trace)
    known_requests = {_read_signature(request) for request in before_requests}
    known_paths = {request["path"] for request in before_requests}
    exact = [
        request
        for request in resumed_requests
        if _read_signature(request) in known_requests
    ]
    same_file = [
        request["path"] for request in resumed_requests if request["path"] in known_paths
    ]
    return {
        "count": len(exact),
        "paths": [request["path"] for request in exact],
        "same_file_count": len(same_file),
        "same_file_paths": sorted(set(same_file)),
    }


def _read_requests(path: str | Path) -> list[dict]:
    requests = []
    for event in _read_jsonl(Path(path)):
        if event.get("event") != "tool_executed" or event.get("name") != "read_file":
            continue
        args = dict(event.get("args", {}) or {})
        file_path = str(args.get("path", "")).strip()
        if not file_path:
            continue
        requests.append(
            {
                "path": file_path,
                "start": args.get("start"),
                "end": args.get("end"),
            }
        )
    return requests


def _read_signature(request: dict) -> str:
    return json.dumps(request, sort_keys=True, separators=(",", ":"))


def _read_jsonl(path: str | Path) -> list[dict]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def run_runtime_task(
    task: dict,
    entry: dict,
    *,
    output_dir: str | Path,
    max_steps: int,
    provider_args=None,
    model_client=None,
) -> dict:
    """Run PonyCode once and produce a patch without reading hidden tests."""
    run_root = Path(output_dir) / "runs" / entry["run_key"]
    workspace = run_root / "workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    shutil.copytree(Path(task["fixture_repo"]), workspace, dirs_exist_ok=True)
    before = _file_snapshot(workspace)
    started = time.monotonic()
    row = dict(entry)
    row.update(
        {
            "instance_id": task["instance_id"],
            "repo": task["repo"],
            "base_commit": task["base_commit"],
            "status": "runtime_failed",
            "runtime_completed": False,
            "resolved": False,
            "failure_category": "runtime_error",
        }
    )
    try:
        agent = _build_agent(
            task,
            workspace,
            output_dir,
            provider_args,
            "minimal_policy",
            max_steps,
            model_client=model_client,
        )
        answer = agent.ask(runtime_prompt(task))
        after = _file_snapshot(workspace)
        patch_path = _write_patch(before, after, run_root / "patch.diff")
        task_state = agent.current_task_state.to_dict()
        report_path = agent.run_store.report_path(agent.current_task_state)
        trace_path = agent.run_store.trace_path(agent.current_task_state)
        trace_usage = _usage_from_trace(trace_path)["usage"]
        usage = {
            "input_tokens": trace_usage.input_tokens,
            "output_tokens": trace_usage.output_tokens,
            "cached_tokens": trace_usage.cached_tokens,
            "total_tokens": trace_usage.input_tokens + trace_usage.output_tokens,
            "usage_source": trace_usage.usage_source,
        }
        patch_nonempty = bool(patch_path.read_text(encoding="utf-8").strip())
        row.update(
            {
                "status": "pending_official_evaluation",
                "runtime_completed": True,
                "failure_category": "",
                "model_answer_nonempty": bool(str(answer).strip()),
                "patch_nonempty": patch_nonempty,
                "patch_path": str(patch_path),
                "report_path": str(report_path),
                "trace_path": str(trace_path),
                "tool_steps": task_state.get("tool_steps", 0),
                "attempts": task_state.get("attempts", 0),
                "changed_paths": task_state.get("changed_paths", []),
                "changed_files": len(task_state.get("changed_paths", []) or []),
                "runtime_run_id": task_state.get("run_id", ""),
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "cached_tokens": usage.get("cached_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "usage_source": usage.get("usage_source"),
            }
        )
    except Exception as exc:
        row["error"] = str(exc)
    row["duration_ms"] = round((time.monotonic() - started) * 1000, 2)
    return row


def write_official_predictions(
    path: str | Path,
    rows: list[dict],
    *,
    model_name: str,
) -> Path:
    predictions = []
    for row in rows:
        patch_path = Path(str(row.get("patch_path") or ""))
        patch = patch_path.read_text(encoding="utf-8") if patch_path.is_file() else ""
        predictions.append(
            {
                "instance_id": row["instance_id"],
                "model_name_or_path": str(model_name),
                "model_patch": patch,
            }
        )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(predictions, indent=2) + "\n", encoding="utf-8", newline="\n")
    return target


def build_official_evaluator_command(
    *,
    evaluator_python: str | Path,
    dataset_path: str | Path,
    predictions_path: str | Path,
    instance_ids: list[str],
    run_id: str,
    namespace: str = "",
    timeout: int = 1800,
) -> list[str]:
    command = [
        str(Path(evaluator_python).resolve()),
        "-m",
        "swebench.harness.run_evaluation",
        "--dataset_name",
        str(Path(dataset_path).resolve()),
        "--split",
        "lite",
        "--instance_ids",
        *instance_ids,
        "--predictions_path",
        str(Path(predictions_path).resolve()),
        "--max_workers",
        "1",
        "--cache_level",
        "instance",
        "--timeout",
        str(int(timeout)),
        "--run_id",
        str(run_id),
    ]
    if namespace:
        command.extend(["--namespace", str(namespace)])
    return command


def run_official_evaluator(
    command: list[str],
    *,
    evaluator_root: str | Path,
    timeout: int,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=Path(evaluator_root).resolve(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        timeout=int(timeout),
        check=False,
    )


def official_report_path(
    evaluator_root: str | Path,
    *,
    run_id: str,
    model_name: str,
    instance_id: str,
) -> Path:
    safe_model = str(model_name).replace("/", "__")
    return (
        Path(evaluator_root)
        / "logs"
        / "run_evaluation"
        / run_id
        / safe_model
        / instance_id
        / "report.json"
    )


def load_official_result(
    path: str | Path,
    instance_id: str,
    *,
    patch_nonempty: bool = True,
) -> dict:
    if not patch_nonempty:
        return {
            "resolved": False,
            "fail2pass_passed": False,
            "pass2pass_passed": False,
            "patch_successfully_applied": False,
            "evaluation_error": "",
        }
    path = Path(path)
    if not path.is_file():
        return {
            "resolved": False,
            "fail2pass_passed": False,
            "pass2pass_passed": False,
            "patch_successfully_applied": False,
            "evaluation_error": "official report is missing",
        }
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        result = report[instance_id]
        tests = result.get("tests_status", {}) or {}
        fail2pass = tests.get("FAIL_TO_PASS", {}) or {}
        pass2pass = tests.get("PASS_TO_PASS", {}) or {}
        return {
            "resolved": bool(result.get("resolved")),
            "fail2pass_passed": bool(fail2pass.get("success"))
            and not bool(fail2pass.get("failure")),
            "pass2pass_passed": not bool(pass2pass.get("failure")),
            "patch_successfully_applied": bool(result.get("patch_successfully_applied")),
            "evaluation_error": "",
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "resolved": False,
            "fail2pass_passed": False,
            "pass2pass_passed": False,
            "patch_successfully_applied": False,
            "evaluation_error": f"invalid official report: {exc}",
        }


def enrich_with_official_result(row: dict, result: dict) -> dict:
    enriched = dict(row)
    enriched.update(result)
    if not enriched.get("runtime_completed"):
        enriched["status"] = "failed"
        enriched["failure_category"] = "runtime_error"
    elif not enriched.get("patch_nonempty"):
        enriched["status"] = "failed"
        enriched["failure_category"] = "patch_not_applied"
    elif result.get("evaluation_error"):
        enriched["status"] = "failed"
        enriched["failure_category"] = "evaluation_error"
    elif not result.get("patch_successfully_applied"):
        enriched["status"] = "failed"
        enriched["failure_category"] = "patch_not_applied"
    elif not result.get("fail2pass_passed"):
        enriched["status"] = "failed"
        enriched["failure_category"] = "fail2pass_failed"
    elif not result.get("pass2pass_passed"):
        enriched["status"] = "failed"
        enriched["failure_category"] = "pass2pass_regression"
    else:
        enriched["status"] = "passed"
        enriched["failure_category"] = ""
    return enriched


def summarize_results(rows: list[dict]) -> dict:
    total = len(rows)

    def count(field):
        return sum(bool(row.get(field)) for row in rows)

    def mean(field):
        values = [float(row[field]) for row in rows if row.get(field) is not None]
        return round(statistics.mean(values), 2) if values else None

    resolved = count("resolved")
    return {
        "runs": total,
        "resolved": resolved,
        "resolution_rate": round(resolved / total, 4) if total else 0.0,
        "runtime_completed": count("runtime_completed"),
        "fail2pass_passed": count("fail2pass_passed"),
        "pass2pass_passed": count("pass2pass_passed"),
        "empty_patches": total - count("patch_nonempty"),
        "evaluation_errors": sum(bool(row.get("evaluation_error")) for row in rows),
        "mean_attempts": mean("attempts"),
        "mean_tool_steps": mean("tool_steps"),
        "mean_total_tokens": mean("total_tokens"),
        "mean_duration_ms": mean("duration_ms"),
    }


def write_result_artifacts(
    output_dir: str | Path,
    manifest: dict,
    rows: list[dict],
) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize_results(rows)
    payload = {**manifest, "summary": summary}
    (output_dir / "manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    fieldnames = sorted({key for row in rows for key in row})
    with (output_dir / "runs.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=True)
                    if isinstance(value, (dict, list))
                    else value
                    for key, value in row.items()
                }
            )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report = (
        "# SWE-bench-Live lightweight result\n\n"
        f"- Runs: {summary['runs']}\n"
        f"- Resolved: {summary['resolved']}\n"
        f"- Resolution rate: {summary['resolution_rate']:.2%}\n"
        f"- Fail2Pass passed: {summary['fail2pass_passed']}\n"
        f"- Pass2Pass passed: {summary['pass2pass_passed']}\n"
        f"- Evaluation errors: {summary['evaluation_errors']}\n"
    )
    (output_dir / "report.md").write_text(report, encoding="utf-8")
    return summary

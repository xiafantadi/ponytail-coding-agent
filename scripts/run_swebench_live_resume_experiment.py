"""Run real two-process checkpoint/resume experiments on frozen SWE-bench-Live tasks."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ponytail.config import resolve_provider_config  # noqa: E402
from ponytail.core.session_store import SessionStore  # noqa: E402
from ponytail.evaluation.minimal_change_experiment import (  # noqa: E402
    _build_agent,
    _build_provider_args,
    _file_snapshot,
    _write_patch,
)
from ponytail.evaluation.real_issue import parse_source_args  # noqa: E402
from ponytail.evaluation.swebench_live import (  # noqa: E402
    aggregate_trace_metrics,
    build_official_evaluator_command,
    build_runtime_task,
    enrich_with_official_result,
    load_official_result,
    load_public_tasks,
    official_image_name,
    official_report_path,
    repeated_reads_after_resume,
    run_official_evaluator,
    runtime_prompt,
    select_resume_tasks,
    write_official_predictions,
    write_result_artifacts,
)
from ponytail.testing import ScriptedModelClient  # noqa: E402

RESUME_REQUEST = (
    "Continue the original repository issue from the persisted checkpoint. "
    "Use the existing investigation and workspace changes, finish the smallest correct patch, "
    "run relevant repository tests, and return the final result."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-profile", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--path", default="benchmarks/swebench_live/tasks.json")
    parser.add_argument("--source", action="append", default=[], metavar="INSTANCE_ID=PATH")
    parser.add_argument("--task-count", type=int, default=2)
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--evaluation-timeout", type=int, default=1800)
    parser.add_argument("--interrupt-after", type=int, default=5)
    parser.add_argument("--output-dir")
    parser.add_argument("--work-root")
    parser.add_argument("--run-id")
    parser.add_argument("--standard-runs", default="evidence/swebench-live/standard/runs.csv")
    parser.add_argument("--evaluator-python")
    parser.add_argument("--evaluator-root")
    parser.add_argument("--evaluator-dataset")
    parser.add_argument("--namespace", default="starryzhang")
    parser.add_argument("--child-config", help=argparse.SUPPRESS)
    parser.add_argument("--child-phase", choices=("first", "resume"), help=argparse.SUPPRESS)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.child_config:
        return run_child(args.child_config, args.child_phase)
    _validate_parent_args(args)
    return run_experiment(args)


def run_child(config_path: str | Path, phase: str) -> int:
    config_path = Path(config_path).resolve()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    workspace = Path(data["workspace"])
    result_path = Path(data["result_path"])
    try:
        provider = resolve_provider_config(
            data.get("provider_profile"),
            start=ROOT,
            config_path=data.get("provider_config"),
            model=data.get("model"),
            base_url=data.get("base_url"),
        )
        provider_args = _build_provider_args(
            provider=provider.name,
            model=provider.model,
            config=data.get("provider_config"),
            base_url=data.get("base_url"),
            api_key=None,
            timeout=int(data["timeout"]),
        )
        session = None
        if phase == "resume":
            session = SessionStore(workspace / ".pico" / "sessions").load(
                data["session_id"]
            )
        interruption_hook = None
        if phase == "first":
            interruption_hook = _checkpoint_blocker(int(data["interrupt_after"]))
        agent = _build_agent(
            data["task"],
            workspace,
            data["output_dir"],
            provider_args,
            "minimal_policy",
            int(data["max_steps"]),
            session=session,
            after_tool_checkpoint_hooks=[interruption_hook] if interruption_hook else None,
        )
        resume_state = dict(agent.resume_state)
        _write_json(
            data["control_path"],
            {
                "pid": os.getpid(),
                "phase": phase,
                "session_id": agent.session["id"],
                "session_path": str(agent.session_path),
                "resume_state": resume_state,
                "started_at": _utc_now(),
            },
        )
        started = time.monotonic()
        answer = agent.ask(runtime_prompt(data["task"]) if phase == "first" else RESUME_REQUEST)
        task_state = agent.current_task_state.to_dict()
        _write_json(
            result_path,
            {
                "status": "completed",
                "pid": os.getpid(),
                "phase": phase,
                "session_id": agent.session["id"],
                "resume_state": resume_state,
                "answer_nonempty": bool(str(answer).strip()),
                "task_state": task_state,
                "trace_path": str(agent.run_store.trace_path(agent.current_task_state)),
                "report_path": str(agent.run_store.report_path(agent.current_task_state)),
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "finished_at": _utc_now(),
            },
        )
        return 0
    except Exception as exc:
        _write_json(
            result_path,
            {
                "status": "failed",
                "pid": os.getpid(),
                "phase": phase,
                "error": str(exc),
                "finished_at": _utc_now(),
            },
        )
        return 1


def run_experiment(args) -> int:
    output_dir = Path(args.output_dir).resolve()
    work_root = Path(args.work_root).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    work_root.mkdir(parents=True, exist_ok=True)
    data = load_public_tasks(args.path)
    selected = select_resume_tasks(data["tasks"], args.task_count)
    sources = parse_source_args(args.source)
    missing = [task["instance_id"] for task in selected if task["instance_id"] not in sources]
    if missing:
        raise ValueError(f"missing --source for: {', '.join(missing)}")
    provider = resolve_provider_config(
        args.provider_profile,
        start=ROOT,
        config_path=args.config,
        model=args.model,
        base_url=args.base_url,
    )
    if not provider.api_key:
        raise ValueError(f"provider profile {provider.name!r} has no API key")
    tasks = [
        build_runtime_task(
            task,
            source=sources[task["instance_id"]],
            max_steps=args.max_steps,
            timeout=args.timeout,
            test_image=official_image_name(task["instance_id"], args.namespace),
        )
        for task in selected
    ]
    baselines = _load_continuous_baselines(args.standard_runs)
    manifest = {
        "suite_id": "swebench-live-resume-light-v1",
        "run_id": args.run_id,
        "provider": provider.name,
        "model": provider.model,
        "task_selection": "sha256(instance_id)",
        "task_ids": [task["instance_id"] for task in tasks],
        "interrupt_after_successful_tools": int(args.interrupt_after),
        "max_steps": int(args.max_steps),
        "created_at": _utc_now(),
    }
    write_result_artifacts(output_dir, manifest, [])
    rows = []
    for index, task in enumerate(tasks, start=1):
        try:
            row = run_resume_case(
                task,
                case_root=work_root / f"case-{index:02d}",
                output_dir=output_dir,
                args=args,
                baseline=baselines.get(task["instance_id"], {}),
            )
        except Exception as exc:
            row = {
                "instance_id": task["instance_id"],
                "repo": task["repo"],
                "base_commit": task["base_commit"],
                "status": "failed",
                "runtime_completed": False,
                "resume_triggered": False,
                "resume_completed": False,
                "resolved": False,
                "failure_category": "resume_infrastructure_error",
                "error": str(exc),
            }
        rows.append(row)
        write_resume_artifacts(output_dir, manifest, rows)

    model_name = f"ponycode-resume-{provider.model}"
    predictions = write_official_predictions(
        output_dir / "predictions.json", rows, model_name=model_name
    )
    command = build_official_evaluator_command(
        evaluator_python=args.evaluator_python,
        dataset_path=args.evaluator_dataset,
        predictions_path=predictions,
        instance_ids=[task["instance_id"] for task in tasks],
        run_id=args.run_id,
        namespace=args.namespace,
        timeout=args.evaluation_timeout,
    )
    completed = run_official_evaluator(
        command,
        evaluator_root=args.evaluator_root,
        timeout=args.evaluation_timeout * max(1, len(tasks)) + 300,
    )
    (output_dir / "official-evaluator.txt").write_text(
        f"exit_code={completed.returncode}\n\nSTDOUT\n{completed.stdout}\n\nSTDERR\n{completed.stderr}",
        encoding="utf-8",
    )
    final_rows = []
    for row in rows:
        report = official_report_path(
            args.evaluator_root,
            run_id=args.run_id,
            model_name=model_name,
            instance_id=row["instance_id"],
        )
        official = load_official_result(
            report,
            row["instance_id"],
            patch_nonempty=bool(row.get("patch_nonempty")),
        )
        if completed.returncode != 0 and not official.get("evaluation_error"):
            official["evaluation_error"] = f"official evaluator exited {completed.returncode}"
        enriched = enrich_with_official_result(row, official)
        enriched["resume_resolved"] = bool(enriched.get("resolved"))
        if not enriched.get("per_turn_budget_passed", True):
            enriched["status"] = "failed"
            enriched["failure_category"] = "per_turn_budget_exceeded"
        final_rows.append(enriched)
    summary = write_resume_artifacts(output_dir, manifest, final_rows)
    run_stale_memory_probe(output_dir / "stale-memory-probe")
    print(
        json.dumps(
            {
                "runs": len(final_rows),
                "resume_completed": summary["resume_completed"],
                "resolved": summary["resolved"],
            },
            sort_keys=True,
        )
    )
    return 0


def run_stale_memory_probe(output_dir: str | Path) -> dict:
    """Verify stale file summaries are invalidated before a resumed prompt is built."""
    output_dir = Path(output_dir).resolve()
    workspace = output_dir / "workspace"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    workspace.mkdir(parents=True)
    target = workspace / "target.py"
    target.write_text("MODE = 'alpha'\n", encoding="utf-8")
    task = {
        "allowed_tools": ["read_file"],
        "allowed_change_paths": [],
    }
    first_client = ScriptedModelClient(
        [
            '<tool>{"name":"read_file","args":{"path":"target.py","start":1,"end":5}}</tool>',
            "<final>Checkpoint ready.</final>",
        ]
    )
    first = _build_agent(
        task,
        workspace,
        output_dir,
        None,
        "minimal_policy",
        3,
        model_client=first_client,
    )
    stale_marker = "FILE_SUMMARY_ALPHA_SENTINEL"
    first.ask("Read target.py and create a resumable checkpoint.")
    first.memory.set_file_summary("target.py", stale_marker)
    first.session["memory"] = first.memory.to_dict()
    first.create_checkpoint(
        first.current_task_state,
        "Read target.py and create a resumable checkpoint.",
        trigger="stale_memory_probe",
    )
    session_id = first.session["id"]
    checkpoint_id = first.session["checkpoints"]["current_id"]
    target.write_text("MODE = 'beta'\n", encoding="utf-8")

    resumed_client = ScriptedModelClient(["<final>Stale state handled.</final>"])
    session = first.session_store.load(session_id)
    resumed = _build_agent(
        task,
        workspace,
        output_dir,
        None,
        "minimal_policy",
        3,
        model_client=resumed_client,
        session=session,
    )
    resume_state = dict(resumed.resume_state)
    resumed.ask("Continue after the workspace changed.")
    prompt = resumed_client.prompts[-1]
    summary_removed = "target.py" not in resumed.memory.to_dict()["file_summaries"]
    stale_summary_absent = stale_marker not in prompt
    checks = {
        "same_session": resumed.session["id"] == session_id,
        "checkpoint_loaded": bool(checkpoint_id),
        "partial_stale": resume_state.get("status") == "partial-stale",
        "stale_path_detected": "target.py" in resume_state.get("stale_paths", []),
        "summary_removed": summary_removed,
        "stale_summary_absent_from_prompt": stale_summary_absent,
        "false_stale_accept_count_zero": not (
            resume_state.get("status") == "full-valid" and resume_state.get("stale_paths")
        ),
    }
    result = {
        "status": "passed" if all(checks.values()) else "failed",
        "resume_status": resume_state.get("status", ""),
        "stale_paths": list(resume_state.get("stale_paths", []) or []),
        "stale_summary_invalidations": int(
            resume_state.get("stale_summary_invalidations", 0) or 0
        ),
        "false_stale_accept_count": int(not checks["false_stale_accept_count_zero"]),
        "checks": checks,
    }
    _write_json(output_dir / "result.json", result)
    return result


def run_resume_case(task, *, case_root: Path, output_dir: Path, args, baseline: dict) -> dict:
    _reset_case_root(case_root, Path(args.work_root).resolve())
    workspace = case_root / "workspace"
    shutil.copytree(Path(task["fixture_repo"]), workspace)
    before = _file_snapshot(workspace)
    child_config_path = case_root / "child-config.json"
    phase1_control = case_root / "phase1-control.json"
    phase1_result = case_root / "phase1-result.json"
    phase2_control = case_root / "phase2-control.json"
    phase2_result = case_root / "phase2-result.json"
    child_config = {
        "task": task,
        "workspace": str(workspace),
        "output_dir": str(output_dir),
        "provider_profile": args.provider_profile,
        "provider_config": str(Path(args.config).resolve()) if args.config else None,
        "model": args.model,
        "base_url": args.base_url,
        "timeout": int(args.timeout),
        "max_steps": int(args.max_steps),
        "interrupt_after": int(args.interrupt_after),
        "control_path": str(phase1_control),
        "result_path": str(phase1_result),
    }
    _write_json(child_config_path, child_config)
    process_events = []
    started = time.monotonic()
    phase1 = _spawn_child(child_config_path, "first", case_root)
    control = _wait_for_json(phase1_control, phase1, 30)
    interruption = _wait_for_checkpoint(
        workspace,
        phase1,
        successful_tools=int(args.interrupt_after),
        timeout=int(args.timeout),
    )
    phase1.terminate()
    phase1_exit = _wait_or_kill(phase1, 10)
    interruption.update(
        {
            "event": "experiment_process_terminated",
            "pid": phase1.pid,
            "exit_code": phase1_exit,
            "terminated_at": _utc_now(),
        }
    )
    process_events.append(interruption)
    session = SessionStore(workspace / ".pico" / "sessions").load(control["session_id"])
    checkpoint_id = str(session.get("checkpoints", {}).get("current_id", ""))
    if not checkpoint_id:
        raise RuntimeError("persisted session has no current checkpoint after interruption")

    child_config.update(
        {
            "session_id": control["session_id"],
            "control_path": str(phase2_control),
            "result_path": str(phase2_result),
        }
    )
    _write_json(child_config_path, child_config)
    phase2 = _spawn_child(child_config_path, "resume", case_root)
    resumed_control = _wait_for_json(phase2_control, phase2, 30)
    phase2_exit = _wait_or_kill(phase2, int(args.timeout) + 120)
    process_events.append(
        {
            "event": "experiment_resume_process_finished",
            "pid": phase2.pid,
            "exit_code": phase2_exit,
            "finished_at": _utc_now(),
        }
    )
    _write_jsonl(case_root / "process-events.jsonl", process_events)
    if not phase2_result.is_file():
        raise RuntimeError(f"resume process produced no result; exit_code={phase2_exit}")
    resumed = json.loads(phase2_result.read_text(encoding="utf-8"))
    if resumed.get("status") != "completed":
        raise RuntimeError(f"resume process failed: {resumed.get('error', 'unknown error')}")

    phase1_trace = Path(interruption["trace_path"])
    phase2_trace = Path(resumed["trace_path"])
    metrics = aggregate_trace_metrics([phase1_trace, phase2_trace])
    repeated = repeated_reads_after_resume(phase1_trace, phase2_trace)
    after = _file_snapshot(workspace)
    patch_path = _write_patch(before, after, case_root / "patch.diff")
    changed_paths = sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))
    patch_stats = _patch_stats(patch_path)
    resume_state = dict(resumed.get("resume_state", {}) or resumed_control.get("resume_state", {}) or {})
    stale_paths = list(resume_state.get("stale_paths", []) or [])
    standard_tokens = _int_or_none(baseline.get("total_tokens"))
    standard_tools = _int_or_none(baseline.get("tool_steps"))
    total_tool_steps = int(metrics["tool_steps"])
    phase1_tool_steps = int(interruption["tool_steps"])
    resume_tool_steps = total_tool_steps - phase1_tool_steps
    per_turn_budget_passed = max(phase1_tool_steps, resume_tool_steps) <= int(args.max_steps)
    return {
        "instance_id": task["instance_id"],
        "repo": task["repo"],
        "base_commit": task["base_commit"],
        "status": "pending_official_evaluation",
        "runtime_completed": True,
        "resume_triggered": True,
        "resume_completed": True,
        "resume_resolved": False,
        "failure_category": "",
        "first_process_pid": phase1.pid,
        "resume_process_pid": phase2.pid,
        "distinct_processes": phase1.pid != phase2.pid,
        "session_id": control["session_id"],
        "same_session": control["session_id"] == resumed.get("session_id"),
        "checkpoint_id": checkpoint_id,
        "interrupted_after_successful_tools": interruption["successful_tool_steps"],
        "phase1_tool_steps": phase1_tool_steps,
        "resume_tool_steps": resume_tool_steps,
        "resume_status": str(resume_state.get("status", "")),
        "stale_paths": stale_paths,
        "stale_summary_invalidations": int(resume_state.get("stale_summary_invalidations", 0) or 0),
        "false_stale_accept_count": int(resume_state.get("status") == "full-valid" and bool(stale_paths)),
        "repeated_reads_after_resume": repeated["count"],
        "repeated_read_paths": repeated["paths"],
        "same_file_read_events_after_resume": repeated["same_file_count"],
        "same_file_read_paths_after_resume": repeated["same_file_paths"],
        "attempts": metrics["attempts"],
        "tool_steps": total_tool_steps,
        "input_tokens": metrics["input_tokens"],
        "cached_tokens": metrics["cached_tokens"],
        "output_tokens": metrics["output_tokens"],
        "total_tokens": metrics["total_tokens"],
        "usage_source": metrics["usage_source"],
        "continuous_total_tokens": standard_tokens,
        "continuous_tool_steps": standard_tools,
        "resume_token_delta": metrics["total_tokens"] - standard_tokens if standard_tokens is not None else None,
        "resume_tool_step_delta": total_tool_steps - standard_tools if standard_tools is not None else None,
        "per_turn_budget_passed": per_turn_budget_passed,
        "cumulative_budget_limit": int(args.max_steps) * 2,
        "cumulative_budget_passed": total_tool_steps <= int(args.max_steps) * 2,
        "duration_ms": round((time.monotonic() - started) * 1000, 2),
        "patch_nonempty": bool(patch_path.read_text(encoding="utf-8").strip()),
        "patch_path": str(patch_path),
        "changed_paths": changed_paths,
        "changed_files": len(changed_paths),
        "added_lines": patch_stats["added_lines"],
        "deleted_lines": patch_stats["deleted_lines"],
        "patch_bytes": patch_path.stat().st_size,
        "phase1_trace_path": str(phase1_trace),
        "trace_path": str(phase2_trace),
        "report_path": str(resumed["report_path"]),
        "process_events_path": str(case_root / "process-events.jsonl"),
    }


def write_resume_artifacts(output_dir: Path, manifest: dict, rows: list[dict]) -> dict:
    base = write_result_artifacts(output_dir, manifest, rows)
    summary = {
        **base,
        "resume_triggered": sum(bool(row.get("resume_triggered")) for row in rows),
        "resume_completed": sum(bool(row.get("resume_completed")) for row in rows),
        "resume_resolved": sum(bool(row.get("resume_resolved")) for row in rows),
        "distinct_processes": sum(bool(row.get("distinct_processes")) for row in rows),
        "full_valid_resumes": sum(row.get("resume_status") == "full-valid" for row in rows),
        "stale_summary_invalidations": sum(int(row.get("stale_summary_invalidations", 0) or 0) for row in rows),
        "repeated_reads_after_resume": sum(int(row.get("repeated_reads_after_resume", 0) or 0) for row in rows),
        "false_stale_accept_count": sum(int(row.get("false_stale_accept_count", 0) or 0) for row in rows),
        "cumulative_budget_passed": sum(bool(row.get("cumulative_budget_passed")) for row in rows),
        "per_turn_budget_passed": sum(bool(row.get("per_turn_budget_passed")) for row in rows),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest_payload = {**manifest, "summary": summary}
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "report.md").write_text(
        "\n".join(
            [
                "# SWE-bench-Live cross-process resume result",
                "",
                f"- Runs: {summary['runs']}",
                f"- Resume triggered/completed: {summary['resume_triggered']}/{summary['resume_completed']}",
                f"- Officially resolved after resume: {summary['resume_resolved']}",
                f"- Distinct-process resumes: {summary['distinct_processes']}",
                f"- Full-valid resumes: {summary['full_valid_resumes']}",
                f"- Repeated reads after resume: {summary['repeated_reads_after_resume']}",
                f"- False stale accepts: {summary['false_stale_accept_count']}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return summary


def recompute_resume_artifacts(output_dir: str | Path, max_steps: int = 30) -> dict:
    """Rebuild derived resume fields from a completed runs.csv without model calls."""
    import csv

    output_dir = Path(output_dir)
    with (output_dir / "runs.csv").open(encoding="utf-8", newline="") as handle:
        rows = [
            {key: _parse_csv_value(value) for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest.pop("summary", None)
    normalized = []
    for row in rows:
        phase1_tools = int(row.get("phase1_tool_steps") or row.get("interrupted_after_successful_tools") or 0)
        total_tools = int(row.get("tool_steps") or 0)
        resume_tools = total_tools - phase1_tools
        row.update(
            {
                "phase1_tool_steps": phase1_tools,
                "resume_tool_steps": resume_tools,
                "per_turn_budget_passed": max(phase1_tools, resume_tools) <= int(max_steps),
                "cumulative_budget_limit": int(max_steps) * 2,
                "cumulative_budget_passed": total_tools <= int(max_steps) * 2,
            }
        )
        phase1_trace = Path(str(row.get("phase1_trace_path", "")))
        resumed_trace = Path(str(row.get("trace_path", "")))
        if phase1_trace.is_file() and resumed_trace.is_file():
            repeated = repeated_reads_after_resume(phase1_trace, resumed_trace)
            row.update(
                {
                    "repeated_reads_after_resume": repeated["count"],
                    "repeated_read_paths": repeated["paths"],
                    "same_file_read_events_after_resume": repeated["same_file_count"],
                    "same_file_read_paths_after_resume": repeated["same_file_paths"],
                }
            )
        official = {
            key: row.get(key)
            for key in (
                "resolved",
                "fail2pass_passed",
                "pass2pass_passed",
                "patch_successfully_applied",
                "evaluation_error",
            )
        }
        enriched = enrich_with_official_result(row, official)
        enriched["resume_resolved"] = bool(enriched.get("resolved"))
        if not enriched["per_turn_budget_passed"]:
            enriched["status"] = "failed"
            enriched["failure_category"] = "per_turn_budget_exceeded"
        normalized.append(enriched)
    return write_resume_artifacts(output_dir, manifest, normalized)


def _wait_for_checkpoint(workspace: Path, process, *, successful_tools: int, timeout: int) -> dict:
    deadline = time.monotonic() + int(timeout)
    while time.monotonic() < deadline:
        traces = sorted(
            (workspace / ".pico" / "runs").rglob("trace.jsonl"),
            key=lambda path: path.stat().st_mtime,
        )
        if traces:
            trace_path = traces[-1]
            events = _read_jsonl(trace_path)
            target = _target_checkpoint(events, successful_tools)
            if target:
                return {**target, "trace_path": str(trace_path)}
        if process.poll() is not None:
            raise RuntimeError(f"first process exited before interruption; exit_code={process.returncode}")
        time.sleep(0.05)
    raise TimeoutError(f"checkpoint interruption was not reached within {timeout}s")


def _checkpoint_blocker(successful_tools: int):
    successes = 0

    def block(payload):
        nonlocal successes
        metadata = dict(payload.get("tool_metadata", {}) or {})
        status = str(metadata.get("tool_status", ""))
        if status == "ok" or (not status and not metadata.get("tool_error_code")):
            successes += 1
        if successes >= successful_tools:
            while True:
                time.sleep(1)

    return block


def _target_checkpoint(events: list[dict], successful_tools: int) -> dict | None:
    successes = 0
    total_tools = 0
    target_index = None
    for index, event in enumerate(events):
        if event.get("event") == "tool_executed":
            total_tools += 1
            status = str(event.get("tool_status", ""))
            if status == "ok" or (not status and not event.get("tool_error_code")):
                successes += 1
                if successes == successful_tools:
                    target_index = index
        elif (
            target_index is not None
            and index > target_index
            and event.get("event") == "checkpoint_created"
            and event.get("trigger") == "tool_executed"
        ):
            return {
                "checkpoint_id": str(event.get("checkpoint_id", "")),
                "successful_tool_steps": successes,
                "tool_steps": total_tools,
            }
    return None


def _spawn_child(config_path: Path, phase: str, case_root: Path):
    stdout = (case_root / f"{phase}-stdout.txt").open("w", encoding="utf-8")
    stderr = (case_root / f"{phase}-stderr.txt").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--child-config",
            str(config_path),
            "--child-phase",
            phase,
        ],
        cwd=ROOT,
        stdout=stdout,
        stderr=stderr,
        text=True,
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    )
    stdout.close()
    stderr.close()
    return process


def _wait_for_json(path: Path, process, timeout: int) -> dict:
    deadline = time.monotonic() + int(timeout)
    while time.monotonic() < deadline:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        if process.poll() is not None:
            raise RuntimeError(f"child exited before writing {path.name}; exit_code={process.returncode}")
        time.sleep(0.05)
    raise TimeoutError(f"timed out waiting for {path.name}")


def _wait_or_kill(process, timeout: int) -> int:
    try:
        return process.wait(timeout=int(timeout))
    except subprocess.TimeoutExpired:
        process.kill()
        return process.wait(timeout=10)


def _load_continuous_baselines(path: str | Path) -> dict[str, dict]:
    import csv

    target = Path(path)
    if not target.is_file():
        return {}
    with target.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {
        row["instance_id"]: row
        for row in rows
        if str(row.get("system", "")).lower() == "ponycode"
    }


def _patch_stats(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines()
    return {
        "added_lines": sum(line.startswith("+") and not line.startswith("+++") for line in lines),
        "deleted_lines": sum(line.startswith("-") and not line.startswith("---") for line in lines),
    }


def _reset_case_root(case_root: Path, work_root: Path) -> None:
    resolved = case_root.resolve()
    if resolved.parent != work_root.resolve():
        raise ValueError("case root must be a direct child of work root")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True)


def _write_json(path: str | Path, payload: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, target)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _int_or_none(value):
    if value in (None, ""):
        return None
    return int(float(value))


def _parse_csv_value(value):
    if value in (None, ""):
        return ""
    if value == "True":
        return True
    if value == "False":
        return False
    if value.startswith(("[", "{")):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    try:
        return float(value) if "." in value else int(value)
    except ValueError:
        return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_parent_args(args) -> None:
    required = {
        "output_dir": args.output_dir,
        "work_root": args.work_root,
        "run_id": args.run_id,
        "evaluator_python": args.evaluator_python,
        "evaluator_root": args.evaluator_root,
        "evaluator_dataset": args.evaluator_dataset,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(f"missing required arguments: {', '.join(missing)}")
    if min(args.task_count, args.max_steps, args.timeout, args.interrupt_after) < 1:
        raise ValueError("task count, budgets, timeout, and interrupt threshold must be positive")


if __name__ == "__main__":
    raise SystemExit(main())

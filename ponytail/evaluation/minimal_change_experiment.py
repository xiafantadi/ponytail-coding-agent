"""Controlled experiment planning and execution for minimal-change arms."""

from __future__ import annotations

import csv
import difflib
import json
import random
import shutil
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

from ..core.runtime import Pico, SessionStore
from ..core.run_store import RunStore
from ..core.workspace import WorkspaceContext
from ..features.minimal_policy import MinimalChangePolicy
from ..providers.runtime import build_model_client
from .minimal_change import (
    evaluate_minimal_change_result,
    render_minimal_change_report,
    run_verification_suite,
    summarize_minimal_change_results,
)


EXPERIMENT_SCHEMA_VERSION = 1
EXPERIMENT_ARMS = ("baseline", "short_yagni", "minimal_policy")
YAGNI_NOTICE = (
    "Prefer the smallest correct implementation. Reuse existing code and dependencies "
    "before adding abstractions. Preserve required safety behavior and tests."
)
TASK_EXECUTION_CONTRACT = (
    "This is an implementation task, not a code explanation task. Inspect the repository "
    "with the available tools and read an existing target file before editing it. Modify "
    "only the allowed files with patch_file or write_file when available, rather than "
    "shell text replacement. Run the relevant repository tests after the edit, including "
    "rerunning a test that failed before the edit. Do not return <final> until the required "
    "change has been applied and verified."
)


def _git_sha():
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=5,
        ).stdout.strip()
    except Exception:
        return ""


def select_tasks(tasks, selection):
    tasks = list(tasks)
    if isinstance(selection, int):
        if selection < 1:
            raise ValueError("tasks count must be positive")
        return tasks[:selection]
    values = [item.strip() for item in str(selection or "").split(",") if item.strip()]
    if not values:
        return tasks
    by_id = {task["task_id"]: task for task in tasks}
    missing = [task_id for task_id in values if task_id not in by_id]
    if missing:
        raise ValueError(f"unknown task ids: {', '.join(missing)}")
    return [by_id[task_id] for task_id in values]


def validate_experiment_config(tasks, arms, repetitions, max_steps, timeout):
    arms = tuple(str(arm).strip() for arm in arms if str(arm).strip())
    unknown = sorted(set(arms) - set(EXPERIMENT_ARMS))
    if unknown:
        raise ValueError(f"unknown experiment arms: {', '.join(unknown)}")
    if not arms:
        raise ValueError("at least one experiment arm is required")
    if len(set(arms)) != len(arms):
        raise ValueError("experiment arms must be unique")
    if int(repetitions) < 1 or int(max_steps) < 1 or int(timeout) < 1:
        raise ValueError("repetitions, max_steps, and timeout must be positive")
    if not tasks:
        raise ValueError("at least one task is required")
    invalid = [task["task_id"] for task in tasks if task.get("status") != "valid"]
    if invalid:
        raise ValueError(f"invalid tasks cannot enter experiment: {', '.join(invalid)}")
    return arms


def build_experiment_plan(tasks, arms, repetitions=1, seed=0):
    """Create and deterministically shuffle one entry per planned run."""
    entries = [
        {
            "task_id": task["task_id"],
            "arm": arm,
            "repetition": repetition,
            "run_key": f"{task['task_id']}__{arm}__r{repetition}",
        }
        for task in tasks
        for arm in arms
        for repetition in range(1, int(repetitions) + 1)
    ]
    random.Random(int(seed)).shuffle(entries)
    for index, entry in enumerate(entries, start=1):
        entry["plan_index"] = index
    return entries


def prompt_for_arm(task, arm):
    allowed_paths = ", ".join(str(path) for path in task.get("allowed_change_paths", []))
    scope_notice = (
        f"Allowed change files: {allowed_paths}."
        if allowed_paths
        else "Follow the task's declared change scope."
    )
    prompt = f"{task['prompt']}\n\n{TASK_EXECUTION_CONTRACT} {scope_notice}"
    if arm == "short_yagni":
        return prompt + "\n\n" + YAGNI_NOTICE
    return prompt


def _file_snapshot(root):
    snapshot = {}
    root = Path(root)
    ignored = {".pico", ".pytest_cache", "__pycache__"}
    for path in root.rglob("*"):
        if not path.is_file() or ignored.intersection(path.relative_to(root).parts):
            continue
        snapshot[path.relative_to(root).as_posix()] = path.read_bytes()
    return snapshot


def _write_patch(before, after, path):
    lines = []
    for name in sorted(set(before) | set(after)):
        if before.get(name) == after.get(name):
            continue
        old = _normalized_diff_lines(before.get(name, b""))
        new = _normalized_diff_lines(after.get(name, b""))
        lines.extend(
            difflib.unified_diff(old, new, fromfile=f"a/{name}", tofile=f"b/{name}")
        )
    path.write_text("".join(lines), encoding="utf-8")
    return path


def _normalized_diff_lines(content):
    text = content.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n").splitlines(True)


def _build_provider_args(*, provider, model, config, base_url, api_key, timeout):
    return SimpleNamespace(
        provider=provider,
        model=model,
        config=config,
        base_url=base_url,
        api_key=api_key,
        cwd=".",
        vision_provider=None,
        temperature=0.0,
        openai_timeout=int(timeout),
    )


def _build_agent(task, workspace, output_root, provider_args, arm, max_steps):
    client = build_model_client(provider_args)
    session_root = workspace / ".pico" / "sessions"
    run_store_root = workspace / ".pico" / "runs"
    agent = Pico(
        model_client=client,
        workspace=WorkspaceContext.build(workspace, repo_root_override=workspace),
        session_store=SessionStore(session_root),
        run_store=RunStore(run_store_root),
        approval_policy="auto",
        max_steps=max_steps,
        max_new_tokens=8192,
        auto_dream=False,
        allowed_tools=task["allowed_tools"],
        write_scope=task["allowed_change_paths"],
        final_readiness_mode="warn",
    )
    # Experiment runs must not inherit user or project Skill files.
    agent.skills = {}
    policy_mode = "enforce" if arm == "minimal_policy" else "off"
    agent.session["minimal_policy"] = MinimalChangePolicy.from_mode(policy_mode).to_dict()
    agent.session_store.save(agent.session)
    return agent


def run_one(task, entry, *, output_dir, provider_args, max_steps, timeout):
    run_root = Path(output_dir) / "runs" / entry["run_key"]
    workspace = run_root / "workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    source = Path(task["fixture_repo"])
    shutil.copytree(source, workspace, dirs_exist_ok=True)
    before = _file_snapshot(workspace)
    started = time.monotonic()
    row = dict(entry)
    row.update({"status": "failed", "failure_category": "infrastructure_error"})
    try:
        agent = _build_agent(task, workspace, output_dir, provider_args, entry["arm"], max_steps)
        answer = agent.ask(prompt_for_arm(task, entry["arm"]))
        after = _file_snapshot(workspace)
        patch_path = _write_patch(before, after, run_root / "patch.diff")
        verifier_dir = run_root / "verifier"
        fail2pass = run_verification_suite(task["failing_tests"], cwd=workspace, timeout=timeout, artifact_dir=verifier_dir, label="fail2pass")
        pass2pass = run_verification_suite(task["regression_tests"], cwd=workspace, timeout=timeout, artifact_dir=verifier_dir, label="pass2pass")
        holdout = run_verification_suite([task["holdout_verifier"]], cwd=workspace, timeout=timeout, artifact_dir=verifier_dir, label="holdout")
        task_state = agent.current_task_state.to_dict()
        report_path = agent.run_store.report_path(agent.current_task_state)
        trace_path = agent.run_store.trace_path(agent.current_task_state)
        usage = dict(getattr(agent, "last_completion_metadata", {}) or {}) or None
        result = evaluate_minimal_change_result(
            task,
            fail2pass=fail2pass,
            pass2pass=pass2pass,
            holdout_verifier=holdout,
            within_budget=task_state["tool_steps"] <= int(max_steps),
            patch_applied=bool(task_state.get("changed_paths")),
            usage_present=usage is not None,
            usage_required=True,
            artifact_paths={"patch": str(patch_path), "trace": str(trace_path), "report": str(report_path)},
            usage=usage,
        )
        row.update(result)
        row.update(
            {
                "model_answer_nonempty": bool(str(answer).strip()),
                "tool_steps": task_state["tool_steps"],
                "attempts": task_state["attempts"],
                "changed_paths": task_state["changed_paths"],
                "runtime_run_id": task_state["run_id"],
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "model": getattr(agent.model_client, "model", ""),
                "provider": getattr(provider_args, "provider", "")
                or getattr(agent.model_client, "provider", ""),
                "added_lines": task_state.get("added_lines"),
                "deleted_lines": task_state.get("deleted_lines"),
                "changed_files": len(task_state.get("changed_paths", []) or []),
                "dependencies_added_count": (
                    len(task_state.get("dependencies_added", []) or [])
                    if task_state.get("dependencies_added") is not None
                    else None
                ),
            }
        )
    except Exception as exc:
        row.update({"error": str(exc), "duration_ms": round((time.monotonic() - started) * 1000, 2)})
    return row


def write_experiment_artifacts(output_dir, manifest, rows):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize_minimal_change_results(rows)
    manifest = dict(manifest)
    manifest["rows"] = rows
    manifest["summary"] = summary
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    fieldnames = sorted({key for row in rows for key in row} | {"run_key", "status", "failure_category"})
    with (output_dir / "runs.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=True) if isinstance(value, (dict, list)) else value for key, value in row.items()})
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "report.md").write_text(render_minimal_change_report(summary, manifest), encoding="utf-8")
    return manifest


def build_manifest(tasks, arms, repetitions, seed, max_steps, timeout, provider_profile, model):
    plan = build_experiment_plan(tasks, arms, repetitions=repetitions, seed=seed)
    return {
        "schema_version": EXPERIMENT_SCHEMA_VERSION,
        "git_sha": _git_sha(),
        "provider_profile": provider_profile or "",
        "model": model or "",
        "seed": int(seed),
        "max_steps": int(max_steps),
        "timeout": int(timeout),
        "arms": list(arms),
        "repetitions": int(repetitions),
        "task_ids": [task["task_id"] for task in tasks],
        "plan": plan,
    }

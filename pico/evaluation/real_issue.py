"""Thin task adapter for real historical repository issues."""

from __future__ import annotations

import json
from pathlib import Path


REQUIRED_REAL_ISSUE_KEYS = {
    "task_id",
    "issue_url",
    "base_commit",
    "request",
    "allowed_paths",
    "fail2pass",
    "pass2pass",
    "timeout_seconds",
}


def load_real_issue_tasks(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("unsupported real-issue schema_version")
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("real-issue suite must contain tasks")
    seen = set()
    for task in tasks:
        missing = sorted(REQUIRED_REAL_ISSUE_KEYS - set(task))
        if missing:
            raise ValueError(f"real-issue task is missing keys: {', '.join(missing)}")
        task_id = str(task["task_id"]).strip()
        if not task_id or task_id in seen:
            raise ValueError(f"invalid or duplicate task_id: {task_id}")
        seen.add(task_id)
        if not str(task["issue_url"]).startswith("https://github.com/"):
            raise ValueError(f"task {task_id} must reference a GitHub source")
        commit = str(task["base_commit"]).lower()
        if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
            raise ValueError(f"task {task_id} must use a full commit SHA")
        if not str(task["request"]).strip():
            raise ValueError(f"task {task_id} request must not be empty")
        for field in ("allowed_paths", "fail2pass", "pass2pass"):
            values = task[field]
            if not isinstance(values, list) or not values or not all(
                isinstance(value, str) and value.strip() for value in values
            ):
                raise ValueError(f"task {task_id} {field} must be a non-empty string list")
        timeout = task["timeout_seconds"]
        if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
            raise ValueError(f"task {task_id} timeout_seconds must be a positive integer")
    return data


def parse_source_args(values: list[str]) -> dict[str, Path]:
    sources = {}
    for value in values:
        task_id, separator, raw_path = str(value).partition("=")
        if not separator or not task_id.strip() or not raw_path.strip():
            raise ValueError("--source must use task_id=path")
        path = Path(raw_path).resolve()
        if not path.is_dir():
            raise ValueError(f"source directory does not exist: {path}")
        sources[task_id.strip()] = path
    return sources


def build_runtime_task(
    task: dict,
    *,
    source: str | Path,
    verification_python: str | Path,
    verifier_root: str | Path,
) -> dict:
    source = Path(source).resolve()
    verifier_root = Path(verifier_root).resolve()
    verification_python = Path(verification_python).resolve()
    if not verification_python.is_file():
        raise ValueError(f"verification Python does not exist: {verification_python}")
    verifier = verifier_root / task["fail2pass"][0]
    if not verifier.is_file():
        raise ValueError(f"real-issue verifier does not exist: {verifier}")

    regression_commands = [_pytest_command(verification_python, node) for node in task["pass2pass"]]
    visible_tests = " ".join(str(node) for node in task["pass2pass"])
    prompt = (
        f"{task['request']}\n\n"
        "Inspect the existing implementation and tests before editing. Add focused regression "
        "coverage when useful, then run the relevant tests after the code change. The local "
        f"test interpreter is {verification_python}; set PYTHONPATH=src before running it. "
        "Nearby regression nodes are "
        f"{visible_tests}. Do not inspect online issue discussions or upstream pull requests."
    )
    return {
        "task_id": task["task_id"],
        "category": "real_issue",
        "fixture_repo": str(source),
        "fixture_revision": task["base_commit"],
        "prompt": prompt,
        "allowed_tools": ["read_file", "patch_file", "run_shell", "search", "list_files"],
        "step_budget": 20,
        "timeout_seconds": int(task["timeout_seconds"]),
        "failing_tests": [_pytest_command(verification_python, verifier)],
        "regression_tests": regression_commands,
        "holdout_verifier": _pytest_command(verification_python, verifier),
        "allowed_change_paths": list(task["allowed_paths"]),
        "forbidden_change_paths": ["pyproject.toml", "uv.lock"],
        "expected_behavior": task["request"],
        "overbuild_opportunity": "Fix the reported behavior without unrelated refactoring.",
        "issue_url": task["issue_url"],
        "base_commit": task["base_commit"],
        "reference_pr_url": task.get("reference_pr_url", ""),
        "status": "valid",
    }


def _pytest_command(python: Path, target: str | Path) -> list[str]:
    script = (
        "$env:PYTHONPATH=(Join-Path (Get-Location) 'src'); "
        f"& '{python}' -m pytest -q '{target}'"
    )
    return ["powershell.exe", "-NoProfile", "-Command", script]


def enrich_real_issue_row(row: dict, task: dict) -> dict:
    row = dict(row)
    row.update(
        {
            "issue_url": task["issue_url"],
            "base_commit": task["base_commit"],
            "reference_pr_url": task.get("reference_pr_url", ""),
        }
    )
    report_path = row.get("report_path")
    if report_path and Path(report_path).is_file():
        report = json.loads(Path(report_path).read_text(encoding="utf-8"))
        task_state = dict(report.get("task_state", {}) or {})
        summaries = dict(task_state.get("evidence_summaries", {}) or {})
        audit = dict(summaries.get("minimality_audit", {}) or {})
        readiness = dict(summaries.get("final_readiness_summary", {}) or {})
        row["scope_passed"] = audit.get("scope_status") == "passed"
        row["out_of_scope_paths"] = list(audit.get("out_of_scope_paths", []) or [])
        row["invalid_final_blocked_count"] = int(readiness.get("block_count", 0) or 0)
    else:
        row.setdefault("scope_passed", False)
        row.setdefault("out_of_scope_paths", [])
        row.setdefault("invalid_final_blocked_count", 0)

    patch_path = row.get("patch_path")
    if patch_path and Path(patch_path).is_file():
        added, deleted = patch_line_stats(Path(patch_path))
        row["added_lines"] = added
        row["deleted_lines"] = deleted
    return row


def patch_line_stats(path: Path) -> tuple[int, int]:
    added = 0
    deleted = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            deleted += 1
    return added, deleted

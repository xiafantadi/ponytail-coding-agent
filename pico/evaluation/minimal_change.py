"""Validation for the isolated minimal-change task contract.

This module only validates task definitions and their unmodified fixtures. It
does not run an agent or replace the existing harness evaluator.
"""

from __future__ import annotations

import hashlib
import csv
import json
import statistics
import shutil
import subprocess
from pathlib import Path

from .verifier import build_verifier_argv, run_verifier


MINIMAL_CHANGE_SCHEMA_VERSION = 1
MINIMAL_CHANGE_STATUS = "valid"
INVALID_TASK_STATUS = "invalid_task"
_TRANSIENT_FIXTURE_DIRS = {".git", ".pico", ".pytest_cache", "__pycache__"}
FAILURE_CATEGORIES = (
    "invalid_task",
    "model_error",
    "tool_error",
    "permission_denied",
    "budget_exceeded",
    "timeout",
    "patch_not_applied",
    "fail2pass_failed",
    "pass2pass_regression",
    "holdout_verifier_failed",
    "scope_violation",
    "missing_usage",
    "infrastructure_error",
)

REQUIRED_TASK_KEYS = (
    "task_id",
    "category",
    "fixture_repo",
    "fixture_revision",
    "prompt",
    "allowed_tools",
    "step_budget",
    "timeout_seconds",
    "failing_tests",
    "regression_tests",
    "holdout_verifier",
    "allowed_change_paths",
    "forbidden_change_paths",
    "expected_behavior",
    "overbuild_opportunity",
)

def _repo_root(repo_root: str | Path | None, task_path: Path | None = None) -> Path:
    if repo_root is not None:
        return Path(repo_root).resolve()
    return Path.cwd().resolve()


def _non_empty_text(value, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _positive_integer(value, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _command_args(command, field_name: str) -> list[str]:
    if not isinstance(command, (str, list, tuple)):
        raise ValueError(f"{field_name} must be a command string or argv list")
    try:
        args = build_verifier_argv(command)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} is invalid: {exc}") from exc
    if not args:
        raise ValueError(f"{field_name} must not be empty")
    executable = Path(args[0])
    if executable.parent != Path("."):
        if not executable.is_file():
            raise ValueError(f"{field_name} executable does not exist: {args[0]}")
    elif shutil.which(args[0]) is None:
        raise ValueError(f"{field_name} executable is not available: {args[0]}")
    return args


def _command_list(value, field_name: str) -> list[str | list[str]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list")
    normalized = []
    for index, command in enumerate(value):
        _command_args(command, f"{field_name}[{index}]")
        normalized.append(command if isinstance(command, str) else [str(item) for item in command])
    return normalized


def _path_list(value, field_name: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ValueError(f"{field_name} must be a list")
    normalized = []
    for path in value:
        path_text = _non_empty_text(path, f"{field_name} entry")
        path_text = path_text.replace("\\", "/").lstrip("./")
        original_path = _non_empty_text(path, f"{field_name} entry").replace("\\", "/")
        if (
            not path_text
            or path_text == "."
            or original_path.startswith("/")
            or original_path == ".."
            or original_path.startswith("../")
            or Path(original_path).is_absolute()
        ):
            raise ValueError(f"{field_name} contains an invalid relative path: {path}")
        normalized.append(path_text)
    return normalized


def fixture_snapshot_id(fixture_repo: str | Path) -> str:
    """Return a stable content id for one fixture directory."""
    root = Path(fixture_repo).resolve()
    if not root.is_dir():
        raise ValueError(f"fixture repo does not exist: {fixture_repo}")
    digest = hashlib.sha256()
    files = (
        item
        for item in root.rglob("*")
        if item.is_file()
        and not _TRANSIENT_FIXTURE_DIRS.intersection(item.relative_to(root).parts)
    )
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        # Git may materialize text fixtures with CRLF on Windows. Treat the
        # checkout representation as equivalent to the frozen LF content.
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def validate_minimal_change_task(task, *, repo_root: str | Path | None = None) -> dict:
    """Validate schema and static command/path contracts for one task."""
    if not isinstance(task, dict):
        raise ValueError("minimal-change task must be a mapping")

    missing = [key for key in REQUIRED_TASK_KEYS if key not in task]
    if missing:
        raise ValueError(f"minimal-change task is missing required keys: {', '.join(missing)}")

    task_id = _non_empty_text(task["task_id"], "task_id")
    category = _non_empty_text(task["category"], "category")
    fixture_repo = _non_empty_text(task["fixture_repo"], "fixture_repo")
    fixture_root = _repo_root(repo_root) / fixture_repo
    if not fixture_root.is_dir():
        raise ValueError(f"minimal-change task {task_id} fixture repo does not exist: {fixture_repo}")

    fixture_revision = _non_empty_text(task["fixture_revision"], "fixture_revision")
    prompt = _non_empty_text(task["prompt"], "prompt")
    allowed_tools = _path_list(task["allowed_tools"], "allowed_tools", allow_empty=False)
    step_budget = _positive_integer(task["step_budget"], "step_budget")
    timeout_seconds = _positive_integer(task["timeout_seconds"], "timeout_seconds")
    failing_tests = _command_list(task["failing_tests"], "failing_tests")
    regression_tests = _command_list(task["regression_tests"], "regression_tests")
    holdout_verifier = task["holdout_verifier"]
    _command_args(holdout_verifier, "holdout_verifier")
    allowed_change_paths = _path_list(task["allowed_change_paths"], "allowed_change_paths")
    forbidden_change_paths = _path_list(task["forbidden_change_paths"], "forbidden_change_paths")
    overlap = sorted(set(allowed_change_paths) & set(forbidden_change_paths))
    if overlap:
        raise ValueError(f"allowed_change_paths and forbidden_change_paths overlap: {', '.join(overlap)}")
    expected_behavior = _non_empty_text(task["expected_behavior"], "expected_behavior")
    overbuild_opportunity = _non_empty_text(task["overbuild_opportunity"], "overbuild_opportunity")

    normalized = dict(task)
    normalized.update(
        {
            "task_id": task_id,
            "category": category,
            "fixture_repo": fixture_repo,
            "fixture_revision": fixture_revision,
            "prompt": prompt,
            "allowed_tools": allowed_tools,
            "step_budget": step_budget,
            "timeout_seconds": timeout_seconds,
            "failing_tests": failing_tests,
            "regression_tests": regression_tests,
            "holdout_verifier": holdout_verifier if isinstance(holdout_verifier, str) else [str(item) for item in holdout_verifier],
            "allowed_change_paths": allowed_change_paths,
            "forbidden_change_paths": forbidden_change_paths,
            "expected_behavior": expected_behavior,
            "overbuild_opportunity": overbuild_opportunity,
        }
    )
    if "target_files" in normalized:
        normalized["target_files"] = _path_list(normalized["target_files"], "target_files")
    return normalized


def validate_minimal_change_suite(data, *, repo_root: str | Path | None = None) -> dict:
    """Validate the top-level schema and all task definitions."""
    if not isinstance(data, dict):
        raise ValueError("minimal-change benchmark must be a mapping")
    if data.get("schema_version") != MINIMAL_CHANGE_SCHEMA_VERSION:
        raise ValueError("unsupported minimal-change benchmark schema_version")
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("minimal-change benchmark tasks must be a non-empty list")

    normalized_tasks = []
    seen_ids = set()
    for task in tasks:
        normalized = validate_minimal_change_task(task, repo_root=repo_root)
        if normalized["task_id"] in seen_ids:
            raise ValueError(f"duplicate minimal-change task id: {normalized['task_id']}")
        seen_ids.add(normalized["task_id"])
        normalized_tasks.append(normalized)
    normalized_data = dict(data)
    normalized_data["schema_version"] = MINIMAL_CHANGE_SCHEMA_VERSION
    normalized_data["tasks"] = normalized_tasks
    return normalized_data


def validate_preconditions(task, *, repo_root: str | Path | None = None) -> dict:
    """Run only the unmodified-fixture checks required by the task contract."""
    normalized = validate_minimal_change_task(task, repo_root=repo_root)
    fixture_root = _repo_root(repo_root) / normalized["fixture_repo"]
    errors = []
    expected_revision = normalized["fixture_revision"]
    actual_revision = fixture_snapshot_id(fixture_root)
    if expected_revision.startswith("sha256:") and expected_revision != actual_revision:
        errors.append("fixture_revision does not match the fixture content")

    checks = {"failing_tests": [], "regression_tests": []}
    timeout = normalized["timeout_seconds"]
    for field_name, expected_failure in (("failing_tests", True), ("regression_tests", False)):
        for command in normalized[field_name]:
            try:
                result = run_verifier(command, cwd=fixture_root, timeout=timeout)
                passed = result.returncode == 0
                expected = (not passed) if expected_failure else passed
                checks[field_name].append(
                    {
                        "command": command,
                        "returncode": result.returncode,
                        "expected_state": "failed" if expected_failure else "passed",
                        "matches_contract": expected,
                    }
                )
                if not expected:
                    errors.append(f"{field_name} precondition has unexpected exit code: {result.returncode}")
            except (OSError, TimeoutError, subprocess.TimeoutExpired, ValueError) as exc:
                checks[field_name].append(
                    {"command": command, "error": str(exc), "matches_contract": False}
                )
                errors.append(f"{field_name} could not run: {exc}")

    return {
        "status": INVALID_TASK_STATUS if errors else MINIMAL_CHANGE_STATUS,
        "task_id": normalized["task_id"],
        "fixture_repo": normalized["fixture_repo"],
        "fixture_revision": expected_revision,
        "actual_fixture_revision": actual_revision,
        "checks": checks,
        "errors": errors,
    }


def load_minimal_change_tasks(path="benchmarks/minimal_change/tasks.json", *, repo_root: str | Path | None = None) -> dict:
    """Load a suite and attach precondition status to every task."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    root = _repo_root(repo_root)
    normalized = validate_minimal_change_suite(data, repo_root=root)
    for task in normalized["tasks"]:
        task["preconditions"] = validate_preconditions(task, repo_root=root)
        task["status"] = task["preconditions"]["status"]
    return normalized


def task_for_model(task: dict) -> dict:
    """Return only the task contract that may be passed to a model."""
    private_keys = {
        "fixture_revision",
        "failing_tests",
        "regression_tests",
        "holdout_verifier",
        "target_files",
        "overbuild_opportunity",
        "preconditions",
        "status",
    }
    return {key: value for key, value in task.items() if key not in private_keys}


def run_verification_suite(commands, *, cwd, timeout=30, artifact_dir=None, label="check"):
    """Run each command independently and retain its raw evidence."""
    results = []
    artifact_dir = Path(artifact_dir) if artifact_dir is not None else None
    if artifact_dir is not None:
        artifact_dir.mkdir(parents=True, exist_ok=True)

    for index, command in enumerate(commands):
        stdout = ""
        stderr = ""
        returncode = None
        error = None
        try:
            completed = run_verifier(command, cwd=cwd, timeout=timeout)
            returncode = completed.returncode
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
        except subprocess.TimeoutExpired as exc:
            error = str(exc)
        except (OSError, ValueError) as exc:
            error = str(exc)

        item = {
            "command": command,
            "returncode": returncode,
            "passed": returncode == 0,
            "stdout": stdout,
            "stderr": stderr,
        }
        if error:
            item["error"] = error
        if artifact_dir is not None:
            stdout_path = artifact_dir / f"{label}-{index}-stdout.txt"
            stderr_path = artifact_dir / f"{label}-{index}-stderr.txt"
            stdout_path.write_text(stdout, encoding="utf-8")
            stderr_path.write_text(stderr or error or "", encoding="utf-8")
            item["stdout_path"] = str(stdout_path)
            item["stderr_path"] = str(stderr_path)
        results.append(item)

    passed_count = sum(1 for item in results if item["passed"])
    return {
        "passed": passed_count == len(results) and bool(results),
        "passed_count": passed_count,
        "failed_count": len(results) - passed_count,
        "total": len(results),
        "results": results,
    }


def evaluate_minimal_change_result(
    task,
    *,
    fail2pass,
    pass2pass,
    holdout_verifier,
    task_status="valid",
    within_budget=True,
    patch_applied=True,
    scope_violation=False,
    usage_present=True,
    usage_required=False,
    runtime_failure=None,
    artifact_paths=None,
    usage=None,
):
    """Build a result row from independent verification evidence."""
    failure_category = None
    if task_status != MINIMAL_CHANGE_STATUS:
        failure_category = INVALID_TASK_STATUS
    elif runtime_failure in FAILURE_CATEGORIES:
        failure_category = runtime_failure
    elif scope_violation:
        failure_category = "scope_violation"
    elif not within_budget:
        failure_category = "budget_exceeded"
    elif not patch_applied:
        failure_category = "patch_not_applied"
    elif not fail2pass["passed"]:
        failure_category = "fail2pass_failed"
    elif not pass2pass["passed"]:
        failure_category = "pass2pass_regression"
    elif not holdout_verifier["passed"]:
        failure_category = "holdout_verifier_failed"
    elif usage_required and not usage_present:
        failure_category = "missing_usage"

    holdout_row = (holdout_verifier.get("results") or [{}])[0]
    artifact_paths = dict(artifact_paths or {})
    return {
        "task_id": task["task_id"],
        "status": "pass" if failure_category is None else "fail",
        "passed": failure_category is None,
        "fail2pass_passed": fail2pass["passed"],
        "fail2pass_total": fail2pass["total"],
        "fail2pass_count": fail2pass["passed_count"],
        "pass2pass_passed": pass2pass["passed"],
        "pass2pass_total": pass2pass["total"],
        "pass2pass_count": pass2pass["passed_count"],
        "holdout_verifier_passed": holdout_verifier["passed"],
        "verifier_exit_code": holdout_row.get("returncode"),
        "verifier_stdout_path": holdout_row.get("stdout_path"),
        "verifier_stderr_path": holdout_row.get("stderr_path"),
        "failure_category": failure_category,
        "patch_path": artifact_paths.get("patch"),
        "trace_path": artifact_paths.get("trace"),
        "report_path": artifact_paths.get("report"),
        "usage": usage,
    }


def summarize_minimal_change_results(rows):
    """Aggregate result rows without dropping failed tasks."""
    rows = list(rows)
    total = len(rows)
    passed = sum(1 for row in rows if row.get("passed") or row.get("status") == "pass")
    failure_category_counts = {}
    for row in rows:
        category = row.get("failure_category")
        if category:
            failure_category_counts[category] = failure_category_counts.get(category, 0) + 1

    def rate(count):
        return count / total if total else 0.0

    fail2pass = sum(1 for row in rows if row.get("fail2pass_passed") is True)
    pass2pass = sum(1 for row in rows if row.get("pass2pass_passed") is True)
    holdout = sum(1 for row in rows if row.get("holdout_verifier_passed") is True)
    summary = {
        "total_tasks": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": rate(passed),
        "fail2pass_passed": fail2pass,
        "fail2pass_pass_rate": rate(fail2pass),
        "pass2pass_passed": pass2pass,
        "pass2pass_pass_rate": rate(pass2pass),
        "holdout_verifier_passed": holdout,
        "holdout_verifier_pass_rate": rate(holdout),
        "failure_category_counts": dict(sorted(failure_category_counts.items())),
    }
    summary["metrics"] = {
        name: _numeric_stats([_number(row.get(name)) for row in rows])
        for name in (
            "attempts",
            "tool_steps",
            "duration_ms",
            "added_lines",
            "deleted_lines",
            "changed_files",
            "dependencies_added_count",
        )
    }
    summary["usage"] = _usage_summary(rows)
    summary["by_arm"] = {
        arm: _summarize_arm(group)
        for arm, group in sorted(_group_rows(rows, "arm").items())
    }
    summary["paired_deltas"] = _paired_deltas(rows)
    verified_passes = passed
    total_tokens = summary["usage"]["total_tokens"]["sum"]
    summary["efficiency"] = {
        "tokens_per_verified_pass": (
            total_tokens / verified_passes if verified_passes and total_tokens is not None else None
        ),
        "tokens_per_verified_pass_reason": (
            "no_verified_passes" if not verified_passes else "available"
        ),
        "cost_per_verified_pass": None,
        "cost_per_verified_pass_reason": "cost_not_recorded",
    }
    return summary


def load_minimal_change_csv(path):
    """Load runner CSV rows into the same shape used by the live aggregator."""
    rows = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            for key in ("passed", "fail2pass_passed", "pass2pass_passed", "holdout_verifier_passed"):
                row[key] = _boolean(row.get(key))
            if row.get("usage"):
                row["usage"] = json.loads(row["usage"])
            rows.append(row)
    return rows


def recompute_minimal_change_summary(path):
    """Recompute summary data from a runner CSV without trusting summary.json."""
    return summarize_minimal_change_results(load_minimal_change_csv(path))


def _boolean(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() == "true"


def _number(value):
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _numeric_stats(values):
    values = [value for value in values if value is not None]
    if not values:
        return {"count": 0, "mean": None, "median": None, "sum": None}
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "sum": sum(values),
    }


def _usage_summary(rows):
    values = []
    for row in rows:
        usage = row.get("usage")
        if isinstance(usage, str):
            try:
                usage = json.loads(usage)
            except json.JSONDecodeError:
                usage = None
        if isinstance(usage, dict):
            values.append(usage)
    return {
        "runs_with_usage": len(values),
        "input_tokens": _numeric_stats([_number(item.get("input_tokens")) for item in values]),
        "output_tokens": _numeric_stats([_number(item.get("output_tokens")) for item in values]),
        "total_tokens": _numeric_stats([_number(item.get("total_tokens")) for item in values]),
        "cached_tokens": _numeric_stats([_number(item.get("cached_tokens")) for item in values]),
    }


def _group_rows(rows, key):
    groups = {}
    for row in rows:
        groups.setdefault(str(row.get(key) or "unknown"), []).append(row)
    return groups


def _summarize_arm(rows):
    total = len(rows)
    passed = sum(1 for row in rows if _boolean(row.get("passed")) or row.get("status") == "pass")
    return {
        "total_runs": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": passed / total if total else 0.0,
        "fail2pass_passed": sum(1 for row in rows if _boolean(row.get("fail2pass_passed"))),
        "pass2pass_passed": sum(1 for row in rows if _boolean(row.get("pass2pass_passed"))),
        "holdout_verifier_passed": sum(1 for row in rows if _boolean(row.get("holdout_verifier_passed"))),
        "failure_category_counts": dict(sorted(_failure_counts(rows).items())),
    }


def _failure_counts(rows):
    counts = {}
    for row in rows:
        category = row.get("failure_category")
        if category:
            counts[category] = counts.get(category, 0) + 1
    return counts


def _paired_deltas(rows):
    groups = {}
    for row in rows:
        key = (str(row.get("task_id", "")), str(row.get("repetition", 1)))
        groups.setdefault(key, []).append(row)
    result = {}
    for arm in sorted({str(row.get("arm")) for row in rows if row.get("arm") and row.get("arm") != "baseline"}):
        deltas = {
            "tool_steps": [],
            "attempts": [],
            "total_tokens": [],
            "added_lines": [],
            "changed_files": [],
        }
        for task_rows in groups.values():
            baseline = next((row for row in task_rows if row.get("arm") == "baseline"), None)
            treatment = next((row for row in task_rows if row.get("arm") == arm), None)
            if not baseline or not treatment:
                continue
            for metric in ("tool_steps", "attempts", "added_lines", "changed_files"):
                before, after = _number(baseline.get(metric)), _number(treatment.get(metric))
                if before is not None and after is not None:
                    deltas[metric].append(after - before)
            before_usage = _usage_dict(baseline)
            after_usage = _usage_dict(treatment)
            before, after = _number(before_usage.get("total_tokens")), _number(after_usage.get("total_tokens"))
            if before is not None and after is not None:
                deltas["total_tokens"].append(after - before)
        result[arm] = {metric: _numeric_stats(values) for metric, values in deltas.items()}
    return result


def _usage_dict(row):
    usage = row.get("usage")
    if isinstance(usage, str):
        try:
            usage = json.loads(usage)
        except json.JSONDecodeError:
            return {}
    return usage if isinstance(usage, dict) else {}


def render_minimal_change_report(summary, metadata=None):
    """Render a concise Markdown report from an aggregated summary."""
    metadata = dict(metadata or {})
    total = int(summary.get("total_tasks", 0) or 0)
    passed = int(summary.get("passed", 0) or 0)
    lines = [
        "# Minimal-Change Experiment Report",
        "",
        f"- Provider profile: `{metadata.get('provider_profile') or 'not recorded'}`",
        f"- Model: `{metadata.get('model') or 'not recorded'}`",
        f"- Runs: {total}",
        "",
        "## Outcome",
        "",
        "| Metric | Passed | Total | Rate |",
        "|---|---:|---:|---:|",
        f"| Task | {passed} | {total} | {_percent(passed, total)} |",
        f"| Fail2Pass | {summary.get('fail2pass_passed', 0)} | {total} | {_percent(summary.get('fail2pass_passed', 0), total)} |",
        f"| Pass2Pass | {summary.get('pass2pass_passed', 0)} | {total} | {_percent(summary.get('pass2pass_passed', 0), total)} |",
        f"| Holdout verifier | {summary.get('holdout_verifier_passed', 0)} | {total} | {_percent(summary.get('holdout_verifier_passed', 0), total)} |",
        "",
        "## By Arm",
        "",
        "| Arm | Passed | Total | Pass rate | Failures |",
        "|---|---:|---:|---:|---|",
    ]
    for arm, values in sorted((summary.get("by_arm") or {}).items()):
        failures = ", ".join(
            f"{key}={value}" for key, value in sorted(values.get("failure_category_counts", {}).items())
        ) or "none"
        lines.append(
            f"| `{arm}` | {values.get('passed', 0)} | {values.get('total_runs', 0)} | "
            f"{_percent(values.get('passed', 0), values.get('total_runs', 0))} | {failures} |"
        )
    lines.extend(["", "## Usage and Efficiency", ""])
    usage = summary.get("usage", {})
    for name in ("input_tokens", "output_tokens", "total_tokens"):
        values = usage.get(name, {})
        lines.append(
            f"- {name}: sum={values.get('sum')}, mean={values.get('mean')}, "
            f"median={values.get('median')}, samples={values.get('count', 0)}"
        )
    lines.extend(["", "## Change Metrics", ""])
    for name in ("added_lines", "deleted_lines", "changed_files", "dependencies_added_count"):
        values = (summary.get("metrics") or {}).get(name, {})
        lines.append(
            f"- {name}: sum={values.get('sum')}, median={values.get('median')}, "
            f"samples={values.get('count', 0)}"
        )
    efficiency = summary.get("efficiency", {})
    lines.extend(
        [
            f"- tokens_per_verified_pass: {efficiency.get('tokens_per_verified_pass')} "
            f"({efficiency.get('tokens_per_verified_pass_reason')})",
            f"- cost_per_verified_pass: {efficiency.get('cost_per_verified_pass')} "
            f"({efficiency.get('cost_per_verified_pass_reason')})",
            "",
            "## Paired Deltas",
            "",
        ]
    )
    for arm, metrics in sorted((summary.get("paired_deltas") or {}).items()):
        lines.append(f"- `{arm}` versus `baseline`:")
        for metric, values in sorted(metrics.items()):
            lines.append(f"  - {metric}: mean={values.get('mean')}, samples={values.get('count', 0)}")
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- Failed runs remain in all denominators and failure categories.",
            "- Cost and LOC metrics are null when the runner does not record them.",
            "- This local task suite is not an official SWE-bench result.",
            "",
        ]
    )
    return "\n".join(lines)


def _percent(passed, total):
    return "null" if not total else f"{100 * passed / total:.2f}%"

"""Build a sanitized, recomputable evidence package for real-Issue runs."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import statistics
from collections import Counter
from pathlib import Path


PUBLIC_FIELDS = (
    "run_key",
    "task_id",
    "issue_url",
    "base_commit",
    "model",
    "provider",
    "status",
    "passed",
    "failure_category",
    "fail2pass_passed",
    "pass2pass_passed",
    "holdout_verifier_passed",
    "scope_passed",
    "attempts",
    "tool_steps",
    "changed_files",
    "added_lines",
    "deleted_lines",
    "duration_ms",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "invalid_final_blocked_count",
)


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def load_public_rows(inputs: list[str | Path]) -> list[dict]:
    source_rows = []
    for root in inputs:
        manifest = json.loads((Path(root) / "manifest.json").read_text(encoding="utf-8"))
        source_rows.extend(manifest.get("rows", []))

    key_counts = Counter(str(source.get("run_key")) for source in source_rows)
    key_occurrences = Counter()
    rows = []
    for source in source_rows:
        usage = source.get("usage") if isinstance(source.get("usage"), dict) else {}
        row = {field: source.get(field) for field in PUBLIC_FIELDS}
        original_key = str(source.get("run_key"))
        if key_counts[original_key] > 1:
            key_occurrences[original_key] += 1
            row["run_key"] = f"{original_key}__rerun{key_occurrences[original_key]}"
        for field in ("input_tokens", "output_tokens", "total_tokens"):
            row[field] = usage.get(field)
        rows.append(row)
    return rows


def summarize(rows: list[dict]) -> dict:
    tasks = sorted({row["task_id"] for row in rows})
    solved = sorted(
        task_id
        for task_id in tasks
        if any(row.get("passed") for row in rows if row["task_id"] == task_id)
    )
    successful = [row for row in rows if row.get("passed")]
    failure_counts = Counter(
        row.get("failure_category") for row in rows if row.get("failure_category")
    )

    def metric(name, selected=rows):
        values = [_number(row.get(name)) for row in selected]
        values = [value for value in values if value is not None]
        return {
            "count": len(values),
            "mean": statistics.mean(values) if values else None,
            "sum": sum(values) if values else None,
        }

    return {
        "run_count": len(rows),
        "passed_runs": len(successful),
        "run_pass_rate": len(successful) / len(rows) if rows else 0.0,
        "task_count": len(tasks),
        "solved_tasks": len(solved),
        "task_solve_rate": len(solved) / len(tasks) if tasks else 0.0,
        "solved_task_ids": solved,
        "fail2pass_passed_runs": sum(bool(row.get("fail2pass_passed")) for row in rows),
        "pass2pass_passed_runs": sum(bool(row.get("pass2pass_passed")) for row in rows),
        "holdout_passed_runs": sum(bool(row.get("holdout_verifier_passed")) for row in rows),
        "scope_passed_runs": sum(bool(row.get("scope_passed")) for row in rows),
        "runs_with_usage": sum(_number(row.get("total_tokens")) is not None for row in rows),
        "failure_category_counts": dict(sorted(failure_counts.items())),
        "all_runs": {
            name: metric(name)
            for name in ("attempts", "tool_steps", "duration_ms", "total_tokens")
        },
        "successful_runs": {
            name: metric(name, successful)
            for name in (
                "attempts",
                "tool_steps",
                "changed_files",
                "added_lines",
                "deleted_lines",
                "duration_ms",
                "total_tokens",
            )
        },
    }


def _case_name(task_id: str) -> str:
    for number in ("3994", "4144", "4190"):
        if number in task_id:
            return number
    return task_id.replace("/", "-")


def _copy_public_patch(source: str | Path, destination: str | Path) -> None:
    lines = Path(source).read_text(encoding="utf-8", errors="replace").splitlines()
    sanitized = [line[0] if line[:1] in {"+", "-"} and not line[1:].strip() else line for line in lines]
    Path(destination).write_text("\n".join(sanitized) + "\n", encoding="utf-8")


def package(inputs, tasks_path, output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    cases_dir = output / "cases"
    if cases_dir.exists():
        shutil.rmtree(cases_dir)
    rows = load_public_rows(inputs)
    summary = summarize(rows)
    tasks = json.loads(Path(tasks_path).read_text(encoding="utf-8"))

    (output / "tasks.json").write_text(
        json.dumps(tasks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (output / "runs.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PUBLIC_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    input_rows = []
    for root in inputs:
        manifest = json.loads((Path(root) / "manifest.json").read_text(encoding="utf-8"))
        input_rows.extend((Path(root), row) for row in manifest.get("rows", []))
    source_pairs = [
        (root, source, public)
        for (root, source), public in zip(input_rows, rows, strict=True)
    ]
    for task_id in sorted({row["task_id"] for row in rows}):
        candidates = [item for item in source_pairs if item[1]["task_id"] == task_id]
        root, selected, public_result = next(
            (item for item in candidates if item[1].get("passed")), candidates[-1]
        )
        case_dir = output / "cases" / f"issue-{_case_name(task_id)}"
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "result.json").write_text(
            json.dumps(public_result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        patch_path = selected.get("patch_path")
        if patch_path and Path(patch_path).is_file() and Path(patch_path).stat().st_size:
            _copy_public_patch(patch_path, case_dir / "patch.diff")
        failure_category = public_result.get("failure_category") or ""
        failure_line = f"failure_category: {failure_category}" if failure_category else "failure_category:"
        test_summary = (
            f"task_id: {task_id}\n"
            f"status: {public_result['status']}\n"
            f"Fail2Pass: {public_result['fail2pass_passed']}\n"
            f"Pass2Pass: {public_result['pass2pass_passed']}\n"
            f"holdout: {public_result['holdout_verifier_passed']}\n"
            f"scope: {public_result['scope_passed']}\n"
            f"{failure_line}\n"
        )
        (case_dir / "test-summary.txt").write_text(test_summary, encoding="utf-8")

    (output / "README.md").write_text(render_readme(summary), encoding="utf-8")
    return summary


def render_readme(summary):
    success = summary["successful_runs"]
    return f"""# Real AI Infrastructure Issue Evidence

This package records a small, real-model evaluation against historical defects
from `openai/openai-agents-python`. The model received the defect description
and the repository at a fixed pre-fix commit. It did not receive upstream patch
content. External tests, not the model's final answer, determined success.

## Results

- Tasks evaluated: {summary['task_count']}
- Tasks solved at least once: {summary['solved_tasks']}/{summary['task_count']}
- Real-model runs: {summary['passed_runs']}/{summary['run_count']} passed
- Runs with Provider usage: {summary['runs_with_usage']}/{summary['run_count']}
- Successful-run mean tool steps: {success['tool_steps']['mean']}
- Successful-run mean total tokens: {success['total_tokens']['mean']}
- Successful-run mean changed files: {success['changed_files']['mean']}
- Successful-run mean patch lines: {(success['added_lines']['mean'] or 0) + (success['deleted_lines']['mean'] or 0)}

Successful runs passed Fail2Pass, nearby Pass2Pass tests, and the configured
write-scope check. Failed runs remain in `runs.csv`.

## Cases

- [Issue #3994](cases/issue-3994/): empty streamed input rejected before model invocation.
- [Issue #4144](cases/issue-4144/): streamed handoff duplicated as `tool_called`; retained as a failed investigation case.
- [PR #4190](cases/issue-4190/): empty session persistence created an unnecessary remote conversation.

## Limitations

- This is a five-run local evaluation, not official SWE-bench.
- The task set contains two GitHub Issues and one merged upstream PR defect.
- One model and one Provider route were used.
- `holdout_verifier_passed` records a second execution of the target external
  verifier; it is not counted as a separate hidden-test result.
- The evaluation establishes case-level repair evidence, not a general coding success rate.
"""


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--tasks", default="benchmarks/real_issues/tasks.json")
    parser.add_argument("--output-dir", default="evidence/real-issues")
    args = parser.parse_args(argv)
    summary = package(args.input, args.tasks, args.output_dir)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

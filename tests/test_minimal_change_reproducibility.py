import csv
import json

from pico.evaluation.minimal_change import (
    recompute_minimal_change_summary,
    render_minimal_change_report,
)


def test_recompute_entrypoint_reads_runner_csv_without_summary_json(tmp_path):
    path = tmp_path / "runs.csv"
    row = {
        "arm": "baseline",
        "task_id": "task-a",
        "status": "fail",
        "passed": "False",
        "fail2pass_passed": "False",
        "pass2pass_passed": "True",
        "holdout_verifier_passed": "False",
        "failure_category": "patch_not_applied",
        "tool_steps": "2",
        "attempts": "3",
        "usage": json.dumps({"input_tokens": 10, "output_tokens": 4, "total_tokens": 14}),
    }
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=row)
        writer.writeheader()
        writer.writerow(row)

    summary = recompute_minimal_change_summary(path)

    assert summary["total_tasks"] == 1
    assert summary["failed"] == 1
    assert summary["usage"]["total_tokens"]["sum"] == 14.0
    assert summary["efficiency"]["tokens_per_verified_pass"] is None


def test_report_is_rendered_from_summary_and_keeps_failure_limits_explicit():
    summary = {
        "total_tasks": 1,
        "passed": 0,
        "fail2pass_passed": 0,
        "pass2pass_passed": 1,
        "holdout_verifier_passed": 0,
        "by_arm": {},
        "usage": {name: {"sum": None, "mean": None, "median": None, "count": 0} for name in ("input_tokens", "output_tokens", "total_tokens")},
        "efficiency": {
            "tokens_per_verified_pass": None,
            "tokens_per_verified_pass_reason": "no_verified_passes",
            "cost_per_verified_pass": None,
            "cost_per_verified_pass_reason": "cost_not_recorded",
        },
        "paired_deltas": {},
    }

    report = render_minimal_change_report(summary, {"provider_profile": "openai", "model": "gpt-5.4"})

    assert "Fail2Pass" in report
    assert "no_verified_passes" in report
    assert "not an official SWE-bench result" in report

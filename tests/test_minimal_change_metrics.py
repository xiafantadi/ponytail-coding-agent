import shutil
from pathlib import Path

from pico.evaluation.minimal_change import (
    evaluate_minimal_change_result,
    load_minimal_change_tasks,
    run_verification_suite,
    summarize_minimal_change_results,
)


def _task(task_id):
    return next(
        task for task in load_minimal_change_tasks()["tasks"] if task["task_id"] == task_id
    )


def _fixture_copy(tmp_path, task):
    source = Path(task["fixture_repo"])
    target = tmp_path / source.name
    shutil.copytree(source, target)
    return target


def _checks(task, fixture, artifact_dir):
    fail2pass = run_verification_suite(
        task["failing_tests"], cwd=fixture, artifact_dir=artifact_dir, label="fail2pass"
    )
    pass2pass = run_verification_suite(
        task["regression_tests"], cwd=fixture, artifact_dir=artifact_dir, label="pass2pass"
    )
    holdout = run_verification_suite(
        [task["holdout_verifier"]], cwd=fixture, artifact_dir=artifact_dir, label="holdout"
    )
    return fail2pass, pass2pass, holdout


def test_valid_patch_passes_fail2pass_pass2pass_and_holdout(tmp_path):
    task = _task("single-file-sum-boundary")
    fixture = _fixture_copy(tmp_path, task)
    (fixture / "app.py").write_text(
        "def total(values):\n    return sum(values)\n", encoding="utf-8"
    )

    fail2pass, pass2pass, holdout = _checks(task, fixture, tmp_path / "artifacts")
    result = evaluate_minimal_change_result(
        task, fail2pass=fail2pass, pass2pass=pass2pass, holdout_verifier=holdout
    )

    assert result["status"] == "pass"
    assert result["fail2pass_passed"] is True
    assert result["fail2pass_total"] == 1
    assert result["pass2pass_total"] == 2
    assert result["holdout_verifier_passed"] is True
    assert result["failure_category"] is None
    assert Path(result["verifier_stdout_path"]).exists()


def test_hardcoded_patch_is_rejected_by_pass2pass(tmp_path):
    task = _task("single-file-sum-boundary")
    fixture = _fixture_copy(tmp_path, task)
    (fixture / "app.py").write_text(
        "def total(values):\n    return 10\n", encoding="utf-8"
    )

    fail2pass, pass2pass, holdout = _checks(task, fixture, tmp_path / "artifacts")
    result = evaluate_minimal_change_result(
        task, fail2pass=fail2pass, pass2pass=pass2pass, holdout_verifier=holdout
    )

    assert fail2pass["passed"] is True
    assert pass2pass["passed"] is False
    assert result["status"] == "fail"
    assert result["failure_category"] == "pass2pass_regression"


def test_failed_result_retains_artifact_references_and_usage():
    task = _task("single-file-sum-boundary")
    evidence = {"passed": False, "passed_count": 0, "total": 1, "results": [{"returncode": 1}]}
    result = evaluate_minimal_change_result(
        task,
        fail2pass=evidence,
        pass2pass=evidence,
        holdout_verifier=evidence,
        artifact_paths={
            "patch": "artifacts/patch.diff",
            "trace": "run/trace.jsonl",
            "report": "run/report.json",
        },
        usage={"input_tokens": 120, "output_tokens": 8},
    )

    assert result["failure_category"] == "fail2pass_failed"
    assert result["patch_path"] == "artifacts/patch.diff"
    assert result["trace_path"] == "run/trace.jsonl"
    assert result["report_path"] == "run/report.json"
    assert result["usage"]["input_tokens"] == 120


def test_failure_categories_override_model_completion():
    task = _task("single-file-sum-boundary")
    evidence = {"passed": True, "passed_count": 1, "total": 1, "results": [{"returncode": 0}]}

    result = evaluate_minimal_change_result(
        task,
        fail2pass=evidence,
        pass2pass=evidence,
        holdout_verifier=evidence,
        scope_violation=True,
    )

    assert result["status"] == "fail"
    assert result["failure_category"] == "scope_violation"


def test_summary_counts_rows_and_keeps_failure_categories():
    rows = [
        {
            "status": "pass",
            "passed": True,
            "fail2pass_passed": True,
            "pass2pass_passed": True,
            "holdout_verifier_passed": True,
        },
        {
            "status": "fail",
            "passed": False,
            "fail2pass_passed": True,
            "pass2pass_passed": False,
            "holdout_verifier_passed": True,
            "failure_category": "pass2pass_regression",
        },
        {
            "status": "fail",
            "passed": False,
            "fail2pass_passed": False,
            "pass2pass_passed": True,
            "holdout_verifier_passed": False,
            "failure_category": "fail2pass_failed",
        },
    ]

    summary = summarize_minimal_change_results(rows)

    assert summary["total_tasks"] == 3
    assert summary["passed"] == 1
    assert summary["failed"] == 2
    assert summary["pass_rate"] == 1 / 3
    assert summary["fail2pass_passed"] == 2
    assert summary["pass2pass_passed"] == 2
    assert summary["failure_category_counts"] == {
        "fail2pass_failed": 1,
        "pass2pass_regression": 1,
    }

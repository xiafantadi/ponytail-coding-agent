import json
import csv

from scripts.package_real_issue_evidence import (
    _copy_public_patch,
    load_public_rows,
    package,
    summarize,
)


def _manifest(path, *, passed):
    row = {
        "run_key": "task__minimal_policy__r1",
        "task_id": "task",
        "issue_url": "https://github.com/example/repo/issues/1",
        "base_commit": "a" * 40,
        "status": "pass" if passed else "fail",
        "passed": passed,
        "failure_category": None if passed else "patch_not_applied",
        "fail2pass_passed": passed,
        "pass2pass_passed": True,
        "holdout_verifier_passed": passed,
        "scope_passed": True,
        "attempts": 2,
        "tool_steps": 3,
        "changed_files": 1 if passed else 0,
        "added_lines": 1 if passed else 0,
        "deleted_lines": 0,
        "duration_ms": 100,
        "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
    }
    (path / "manifest.json").write_text(json.dumps({"rows": [row]}), encoding="utf-8")
    return row


def test_summary_keeps_failed_runs(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    _manifest(first, passed=False)
    _manifest(second, passed=True)

    rows = load_public_rows([first, second])
    summary = summarize(rows)

    assert len({row["run_key"] for row in rows}) == 2
    assert rows[0]["run_key"].endswith("__rerun1")
    assert rows[1]["run_key"].endswith("__rerun2")
    assert summary["run_count"] == 2
    assert summary["passed_runs"] == 1
    assert summary["solved_tasks"] == 1
    assert summary["failure_category_counts"] == {"patch_not_applied": 1}


def test_package_writes_recomputable_public_files(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _manifest(source, passed=False)
    tasks = tmp_path / "tasks.json"
    tasks.write_text(
        json.dumps({"schema_version": 1, "repository_url": "https://example.com", "tasks": []}),
        encoding="utf-8",
    )
    output = tmp_path / "evidence"

    result = package([source], tasks, output)

    assert result["run_count"] == 1
    assert (output / "runs.csv").is_file()
    assert json.loads((output / "summary.json").read_text(encoding="utf-8")) == result
    readme = (output / "README.md").read_text(encoding="utf-8")
    assert "not official SWE-bench" in readme
    assert "not counted as a separate hidden-test result" in readme


def test_package_selects_successful_rerun_for_case_evidence(tmp_path):
    failed = tmp_path / "failed"
    passed = tmp_path / "passed"
    failed.mkdir()
    passed.mkdir()
    _manifest(failed, passed=False)
    _manifest(passed, passed=True)
    tasks = tmp_path / "tasks.json"
    tasks.write_text(
        json.dumps({"schema_version": 1, "repository_url": "https://example.com", "tasks": []}),
        encoding="utf-8",
    )
    output = tmp_path / "evidence"

    package([failed, passed], tasks, output)

    with (output / "runs.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result = json.loads((output / "cases" / "issue-task" / "result.json").read_text())
    assert len({row["run_key"] for row in rows}) == 2
    assert result["passed"] is True
    assert result["run_key"].endswith("__rerun2")


def test_public_patch_removes_whitespace_from_changed_blank_lines(tmp_path):
    source = tmp_path / "source.diff"
    output = tmp_path / "public.diff"
    source.write_text("@@ -1 +1 @@\n-   \n+ \n", encoding="utf-8")

    _copy_public_patch(source, output)

    assert output.read_text(encoding="utf-8") == "@@ -1 +1 @@\n-\n+\n"

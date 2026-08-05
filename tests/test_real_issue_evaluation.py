import json

import pytest

from ponytail.evaluation.real_issue import (
    build_runtime_task,
    enrich_real_issue_row,
    load_real_issue_tasks,
    parse_source_args,
    patch_line_stats,
)


def _task():
    return {
        "task_id": "issue-1",
        "issue_url": "https://github.com/example/repo/issues/1",
        "base_commit": "a" * 40,
        "reference_pr_url": "https://github.com/example/repo/pull/2",
        "request": "Fix the bug.",
        "allowed_paths": ["src/", "tests/"],
        "fail2pass": ["issue_test.py"],
        "pass2pass": ["tests/test_ok.py::test_ok"],
        "timeout_seconds": 30,
    }


def test_load_real_issue_tasks_validates_schema(tmp_path):
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps({"schema_version": 1, "tasks": [_task()]}), encoding="utf-8")
    assert load_real_issue_tasks(path)["tasks"][0]["task_id"] == "issue-1"

    data = {"schema_version": 1, "tasks": [{**_task(), "base_commit": "short"}]}
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="full commit SHA"):
        load_real_issue_tasks(path)

    data = {"schema_version": 1, "tasks": [{key: value for key, value in _task().items() if key != "fail2pass"}]}
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="missing keys: fail2pass"):
        load_real_issue_tasks(path)

    data = {"schema_version": 1, "tasks": [{**_task(), "pass2pass": []}]}
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="pass2pass must be a non-empty string list"):
        load_real_issue_tasks(path)


def test_parse_source_args_requires_existing_directory(tmp_path):
    assert parse_source_args([f"issue-1={tmp_path}"])["issue-1"] == tmp_path.resolve()
    with pytest.raises(ValueError, match="does not exist"):
        parse_source_args([f"issue-1={tmp_path / 'missing'}"])


def test_build_runtime_task_reuses_external_pytest(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    verifier_root = tmp_path / "verifiers"
    verifier_root.mkdir()
    (verifier_root / "issue_test.py").write_text("def test_x(): pass\n", encoding="utf-8")
    scripts = tmp_path / "venv" / "Scripts"
    scripts.mkdir(parents=True)
    python = scripts / "python.exe"
    pytest_exe = scripts / "pytest.exe"
    python.write_text("", encoding="utf-8")
    pytest_exe.write_text("", encoding="utf-8")

    result = build_runtime_task(
        _task(), source=source, verification_python=python, verifier_root=verifier_root
    )
    assert result["fixture_repo"] == str(source.resolve())
    assert result["failing_tests"][0][0] == "powershell.exe"
    assert str(python.resolve()) in result["failing_tests"][0][-1]
    assert str(pytest_exe.resolve()) not in result["failing_tests"][0][-1]
    assert result["status"] == "valid"


def test_patch_line_stats_and_report_enrichment(tmp_path):
    patch = tmp_path / "patch.diff"
    patch.write_text(
        "--- a/app.py\n+++ b/app.py\n@@ -1 +1,2 @@\n-old\n+new\n+more\n",
        encoding="utf-8",
    )
    assert patch_line_stats(patch) == (2, 1)
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "task_state": {
                    "evidence_summaries": {
                        "minimality_audit": {
                            "scope_status": "passed",
                            "out_of_scope_paths": [],
                        },
                        "final_readiness_summary": {"block_count": 2},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    row = enrich_real_issue_row(
        {"patch_path": str(patch), "report_path": str(report)}, _task()
    )
    assert row["scope_passed"] is True
    assert row["invalid_final_blocked_count"] == 2
    assert (row["added_lines"], row["deleted_lines"]) == (2, 1)

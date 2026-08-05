import json
import shutil
import sys
from collections import Counter
from pathlib import Path

import pytest

from pico.evaluation.minimal_change import (
    INVALID_TASK_STATUS,
    fixture_snapshot_id,
    load_minimal_change_tasks,
    task_for_model,
    validate_minimal_change_suite,
    validate_minimal_change_task,
    validate_preconditions,
)


FIXTURE = Path("tests/fixtures/bench_repo_patch")


def _command(expression):
    return [sys.executable, "-c", expression]


def _task(fixture_repo=FIXTURE):
    fixture_repo = Path(fixture_repo)
    return {
        "task_id": "replace-placeholder",
        "category": "minimal-bug-fix",
        "fixture_repo": str(fixture_repo),
        "fixture_revision": fixture_snapshot_id(fixture_repo) if fixture_repo.is_dir() else "working-tree",
        "prompt": "Replace the placeholder value with delta while preserving the other values.",
        "allowed_tools": ["read_file", "patch_file", "run_shell"],
        "step_budget": 8,
        "timeout_seconds": 10,
        "failing_tests": [
            _command("from pathlib import Path; assert 'delta' in Path('sample.txt').read_text()")
        ],
        "regression_tests": [
            _command("from pathlib import Path; text=Path('sample.txt').read_text(); assert all(value in text for value in ('alpha', 'beta', 'gamma'))")
        ],
        "holdout_verifier": _command("from pathlib import Path; assert 'delta' in Path('sample.txt').read_text()"),
        "allowed_change_paths": ["sample.txt"],
        "forbidden_change_paths": ["README.md"],
        "expected_behavior": "sample.txt contains delta and retains alpha, beta, and gamma.",
        "overbuild_opportunity": "The task does not require a new helper, dependency, or documentation change.",
        "target_files": ["sample.txt"],
    }


def test_schema_rejects_each_missing_required_field():
    task = _task()
    for key in tuple(task):
        if key == "target_files":
            continue
        incomplete = dict(task)
        incomplete.pop(key)
        with pytest.raises(ValueError, match="missing required keys"):
            validate_minimal_change_task(incomplete)


def test_suite_rejects_duplicate_task_ids():
    task = _task()
    with pytest.raises(ValueError, match="duplicate"):
        validate_minimal_change_suite(
            {"schema_version": 1, "tasks": [task, dict(task)]}
        )


def test_schema_rejects_missing_fixture_and_invalid_verifier():
    task = _task(fixture_repo="tests/fixtures/does-not-exist")
    with pytest.raises(ValueError, match="fixture repo"):
        validate_minimal_change_task(task)

    task = _task()
    task["holdout_verifier"] = []
    with pytest.raises(ValueError, match="holdout_verifier"):
        validate_minimal_change_task(task)


def test_schema_rejects_bad_test_types_and_path_overlap():
    task = _task()
    task["failing_tests"] = "python -c pass"
    with pytest.raises(ValueError, match="failing_tests"):
        validate_minimal_change_task(task)

    task = _task()
    task["allowed_change_paths"] = ["README.md"]
    with pytest.raises(ValueError, match="overlap"):
        validate_minimal_change_task(task)


def test_valid_task_loads_and_target_files_are_not_model_contract():
    task = _task()
    normalized = validate_minimal_change_task(task)
    model_task = task_for_model(normalized)

    assert normalized["task_id"] == "replace-placeholder"
    assert model_task["prompt"] == task["prompt"]
    assert "target_files" not in model_task
    assert "holdout_verifier" not in model_task
    assert "failing_tests" not in model_task


def test_preconditions_mark_task_invalid_when_baseline_contract_is_wrong(tmp_path):
    fixture = tmp_path / "bench_repo_patch"
    shutil.copytree(FIXTURE, fixture)
    task = _task(fixture)
    task["failing_tests"] = [_command("raise SystemExit(0)")]

    result = validate_preconditions(task, repo_root=tmp_path)

    assert result["status"] == INVALID_TASK_STATUS
    assert result["checks"]["failing_tests"][0]["matches_contract"] is False
    assert result["errors"]


def test_load_attaches_invalid_task_status_without_entering_experiment(tmp_path):
    fixture = tmp_path / "bench_repo_patch"
    shutil.copytree(FIXTURE, fixture)
    task = _task(fixture)
    task["regression_tests"] = [_command("raise SystemExit(1)")]
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps({"schema_version": 1, "tasks": [task]}), encoding="utf-8")

    loaded = load_minimal_change_tasks(path, repo_root=tmp_path)

    assert loaded["tasks"][0]["status"] == INVALID_TASK_STATUS
    assert loaded["tasks"][0]["preconditions"]["checks"]["regression_tests"][0]["matches_contract"] is False


def test_fixture_snapshot_is_stable_and_source_is_unchanged(tmp_path):
    fixture = tmp_path / "bench_repo_patch"
    shutil.copytree(FIXTURE, fixture)
    before = fixture_snapshot_id(fixture)
    task = _task(fixture)
    result = validate_preconditions(task, repo_root=tmp_path)

    assert result["status"] == "valid"
    assert result["actual_fixture_revision"] == before
    assert fixture_snapshot_id(fixture) == before


def test_fixture_snapshot_normalizes_checkout_line_endings(tmp_path):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    source = fixture / "app.py"
    source.write_bytes(b"first\nsecond\n")
    lf_snapshot = fixture_snapshot_id(fixture)

    source.write_bytes(b"first\r\nsecond\r\n")

    assert fixture_snapshot_id(fixture) == lf_snapshot


def test_default_minimal_change_suite_has_balanced_behavioral_tasks():
    loaded = load_minimal_change_tasks()
    tasks = loaded["tasks"]

    assert len(tasks) == 18
    assert Counter(task["category"] for task in tasks) == {
        "overbuild_trap": 6,
        "bug_fix": 6,
        "security": 6,
    }
    assert all(task["status"] == "valid" for task in tasks)
    assert all(
        "tests/test_behavior.py" in " ".join(map(str, task["failing_tests"]))
        for task in tasks
    )
    assert all(task["target_files"] for task in tasks)


def test_default_tasks_use_behavioral_verifiers_and_not_file_presence_checks():
    loaded = load_minimal_change_tasks()

    for task in loaded["tasks"]:
        commands = [task["holdout_verifier"]]
        commands.extend(task["failing_tests"])
        commands.extend(task["regression_tests"])
        command_text = " ".join(
            command if isinstance(command, str) else " ".join(command)
            for command in commands
        )
        assert "exists()" not in command_text
        assert "is_file()" not in command_text
        assert "test_behavior.py" in command_text

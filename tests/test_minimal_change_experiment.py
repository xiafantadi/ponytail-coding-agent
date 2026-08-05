import pytest

from pico.evaluation.minimal_change_experiment import (
    EXPERIMENT_ARMS,
    TASK_EXECUTION_CONTRACT,
    YAGNI_NOTICE,
    build_experiment_plan,
    build_manifest,
    prompt_for_arm,
    select_tasks,
    validate_experiment_config,
    write_experiment_artifacts,
)
from pico.evaluation.minimal_change import recompute_minimal_change_summary


def _tasks():
    return [
        {"task_id": "task-a", "prompt": "Fix A", "status": "valid"},
        {"task_id": "task-b", "prompt": "Fix B", "status": "valid"},
        {"task_id": "task-c", "prompt": "Fix C", "status": "valid"},
    ]


def test_experiment_plan_is_deterministic_and_has_one_entry_per_arm():
    tasks = _tasks()
    arms = validate_experiment_config(tasks, EXPERIMENT_ARMS, 1, 20, 300)

    first = build_experiment_plan(tasks, arms, repetitions=1, seed=7)
    second = build_experiment_plan(tasks, arms, repetitions=1, seed=7)

    assert first == second
    assert len(first) == 9
    assert len({entry["run_key"] for entry in first}) == 9
    assert {entry["arm"] for entry in first} == set(EXPERIMENT_ARMS)


def test_arm_prompt_isolation():
    task = _tasks()[0]

    baseline = prompt_for_arm(task, "baseline")
    assert baseline.startswith("Fix A\n\n")
    assert TASK_EXECUTION_CONTRACT in baseline
    assert YAGNI_NOTICE in prompt_for_arm(task, "short_yagni")
    assert TASK_EXECUTION_CONTRACT in prompt_for_arm(task, "minimal_policy")


def test_manifest_records_fixed_experiment_contract():
    manifest = build_manifest(_tasks(), EXPERIMENT_ARMS, 1, 3, 20, 300, "openai", "model-x")

    assert manifest["seed"] == 3
    assert manifest["max_steps"] == 20
    assert manifest["timeout"] == 300
    assert len(manifest["plan"]) == 9
    assert manifest["provider_profile"] == "openai"


def test_invalid_task_cannot_enter_experiment():
    tasks = _tasks()
    tasks[0]["status"] = "invalid_task"

    with pytest.raises(ValueError, match="invalid tasks"):
        validate_experiment_config(tasks, EXPERIMENT_ARMS, 1, 20, 300)


def test_select_tasks_supports_count_and_explicit_ids():
    tasks = _tasks()

    assert [task["task_id"] for task in select_tasks(tasks, 2)] == ["task-a", "task-b"]
    assert [task["task_id"] for task in select_tasks(tasks, "task-c,task-a")] == ["task-c", "task-a"]


def test_written_summary_is_reproducible_from_runs_csv(tmp_path):
    rows = [
        {
            "run_key": "task-a__baseline__r1",
            "arm": "baseline",
            "task_id": "task-a",
            "status": "fail",
            "passed": False,
            "fail2pass_passed": False,
            "pass2pass_passed": True,
            "holdout_verifier_passed": False,
            "failure_category": "patch_not_applied",
            "tool_steps": 1,
            "attempts": 2,
            "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        }
    ]
    manifest = {"schema_version": 1, "plan": [{"run_key": rows[0]["run_key"]}]}

    write_experiment_artifacts(tmp_path, manifest, rows)

    import json

    written = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    recomputed = recompute_minimal_change_summary(tmp_path / "runs.csv")
    assert written == recomputed
    assert (tmp_path / "report.md").exists()

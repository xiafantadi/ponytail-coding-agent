import pytest

from pico.evaluation.minimal_change_experiment import (
    EXPERIMENT_ARMS,
    YAGNI_NOTICE,
    build_experiment_plan,
    build_manifest,
    prompt_for_arm,
    select_tasks,
    validate_experiment_config,
)


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

    assert prompt_for_arm(task, "baseline") == "Fix A"
    assert YAGNI_NOTICE in prompt_for_arm(task, "short_yagni")
    assert prompt_for_arm(task, "minimal_policy") == "Fix A"


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

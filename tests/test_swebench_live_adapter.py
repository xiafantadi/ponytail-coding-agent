import json

import pytest

from ponytail.testing import ScriptedModelClient
from scripts.run_swebench_live_experiment import build_parser, parse_task_selection
from ponytail.evaluation.swebench_live import (
    MODEL_VISIBLE_FIELDS,
    aggregate_trace_metrics,
    build_official_evaluator_command,
    build_runtime_task,
    enrich_with_official_result,
    load_official_result,
    load_public_tasks,
    official_image_name,
    project_model_task,
    run_runtime_task,
    repeated_reads_after_resume,
    select_resume_tasks,
    summarize_results,
    write_official_predictions,
)


def _task():
    return {
        "instance_id": "owner__repo-1",
        "repo": "owner/repo",
        "base_commit": "a" * 40,
        "problem_statement": "Fix the parser without unrelated changes.",
    }


def test_experiment_runner_defaults_to_all_tasks():
    args = build_parser().parse_args(
        [
            "--output-dir",
            "output",
            "--run-id",
            "run-1",
            "--evaluator-python",
            "python",
            "--evaluator-root",
            "evaluator",
            "--evaluator-dataset",
            "dataset.json",
        ]
    )
    assert args.tasks == "all"
    assert parse_task_selection(args.tasks) == ""
    assert parse_task_selection("2") == 2


def test_resume_tasks_are_selected_by_instance_hash_not_outcome():
    tasks = [
        {"instance_id": "amoffat__sh-744"},
        {"instance_id": "cyclotruc__gitingest-94"},
        {"instance_id": "dynaconf__dynaconf-1241"},
        {"instance_id": "run-llama__llama_deploy-384"},
    ]

    selected = select_resume_tasks(tasks, 2)

    assert [task["instance_id"] for task in selected] == [
        "cyclotruc__gitingest-94",
        "run-llama__llama_deploy-384",
    ]


def test_resume_trace_metrics_aggregate_usage_and_repeated_reads(tmp_path):
    first = tmp_path / "first.jsonl"
    resumed = tmp_path / "resumed.jsonl"
    first.write_text(
        "\n".join(
            [
                json.dumps({"event": "model_requested"}),
                json.dumps(
                    {
                        "event": "model_parsed",
                        "completion_metadata": {
                            "provider_protocol": "openai",
                            "provider_model": "test-model",
                            "input_tokens": 100,
                            "cached_tokens": 10,
                            "output_tokens": 5,
                        },
                    }
                ),
                json.dumps(
                    {
                        "event": "tool_executed",
                        "name": "read_file",
                        "args": {"path": "src/app.py"},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    resumed.write_text(
        "\n".join(
            [
                json.dumps({"event": "model_requested"}),
                json.dumps(
                    {
                        "event": "model_parsed",
                        "completion_metadata": {
                            "provider_protocol": "openai",
                            "provider_model": "test-model",
                            "input_tokens": 80,
                            "cached_tokens": 20,
                            "output_tokens": 7,
                        },
                    }
                ),
                json.dumps(
                    {
                        "event": "tool_executed",
                        "name": "read_file",
                        "args": {"path": "src/app.py"},
                    }
                ),
                json.dumps({"event": "tool_executed", "name": "search", "args": {}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    metrics = aggregate_trace_metrics([first, resumed])

    assert metrics == {
        "attempts": 2,
        "tool_steps": 3,
        "read_paths": ["src/app.py", "src/app.py"],
        "input_tokens": 180,
        "cached_tokens": 30,
        "output_tokens": 12,
        "total_tokens": 192,
        "usage_source": "actual",
    }
    assert repeated_reads_after_resume(first, resumed) == {
        "count": 1,
        "paths": ["src/app.py"],
        "same_file_count": 1,
        "same_file_paths": ["src/app.py"],
    }


def test_project_model_task_strips_evaluator_only_fields():
    projected = project_model_task(
        {
            **_task(),
            "patch": "secret gold patch",
            "test_patch": "secret hidden tests",
            "FAIL_TO_PASS": ["hidden::test"],
            "PASS_TO_PASS": ["regression::test"],
        }
    )
    assert tuple(projected) == MODEL_VISIBLE_FIELDS
    assert "secret" not in json.dumps(projected)


def test_load_public_tasks_rejects_hidden_or_unknown_fields(tmp_path):
    path = tmp_path / "tasks.json"
    path.write_text(
        json.dumps({"schema_version": 1, "tasks": [{**_task(), "test_patch": "hidden"}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="evaluator-only"):
        load_public_tasks(path)

    path.write_text(
        json.dumps({"schema_version": 1, "tasks": [{**_task(), "hint": "target.py"}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unsupported fields: hint"):
        load_public_tasks(path)


def test_runtime_task_contains_no_hidden_verifier_data(tmp_path):
    image = official_image_name("owner__repo-1", "example")
    runtime = build_runtime_task(_task(), source=tmp_path, test_image=image)
    serialized = json.dumps(runtime)
    assert runtime["allowed_change_paths"] == []
    assert image in runtime["prompt"]
    assert "%CD%:/testbed" in runtime["prompt"]
    assert "FAIL_TO_PASS" not in serialized
    assert "PASS_TO_PASS" not in serialized
    assert "gold" not in serialized
    assert "hidden" not in serialized


def test_prediction_and_official_report_mapping(tmp_path):
    patch = tmp_path / "patch.diff"
    patch.write_text("--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new\n", encoding="utf-8")
    predictions = write_official_predictions(
        tmp_path / "predictions.json",
        [{"instance_id": "owner__repo-1", "patch_path": str(patch)}],
        model_name="PonyCode/test",
    )
    payload = json.loads(predictions.read_text(encoding="utf-8"))
    assert set(payload[0]) == {"instance_id", "model_name_or_path", "model_patch"}

    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "owner__repo-1": {
                    "resolved": True,
                    "patch_successfully_applied": True,
                    "tests_status": {
                        "FAIL_TO_PASS": {"success": ["test_fix"], "failure": []},
                        "PASS_TO_PASS": {"success": ["test_old"], "failure": []},
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    result = load_official_result(report, "owner__repo-1")
    row = enrich_with_official_result(
        {"runtime_completed": True, "patch_nonempty": True}, result
    )
    assert row["status"] == "passed"
    assert row["resolved"] is True

    empty = load_official_result(
        tmp_path / "missing-report.json",
        "owner__repo-1",
        patch_nonempty=False,
    )
    assert empty["resolved"] is False
    assert empty["evaluation_error"] == ""


def test_official_command_and_summary_are_deterministic(tmp_path):
    python = tmp_path / "python.exe"
    dataset = tmp_path / "dataset.json"
    predictions = tmp_path / "predictions.json"
    command = build_official_evaluator_command(
        evaluator_python=python,
        dataset_path=dataset,
        predictions_path=predictions,
        instance_ids=["owner__repo-1"],
        run_id="light-run",
        namespace="starryzhang",
        timeout=90,
    )
    assert command[:3] == [str(python.resolve()), "-m", "swebench.harness.run_evaluation"]
    assert "gold" not in command
    assert command[command.index("--max_workers") + 1] == "1"

    summary = summarize_results(
        [
            {
                "resolved": True,
                "runtime_completed": True,
                "fail2pass_passed": True,
                "pass2pass_passed": True,
                "patch_nonempty": True,
                "attempts": 2,
                "tool_steps": 3,
                "total_tokens": 100,
                "duration_ms": 50,
            }
        ]
    )
    assert summary["resolution_rate"] == 1.0
    assert summary["mean_tool_steps"] == 3.0


def test_frozen_public_tasks_are_leak_safe():
    data = load_public_tasks("benchmarks/swebench_live/tasks.json")
    assert len(data["tasks"]) == 4


def test_scripted_runtime_produces_patch_and_run_evidence(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    task = build_runtime_task(_task(), source=source, max_steps=6)
    class UsageScriptedModelClient(ScriptedModelClient):
        def complete(self, prompt, max_new_tokens, **kwargs):
            output = super().complete(prompt, max_new_tokens, **kwargs)
            call = len(self.prompts)
            self.last_completion_metadata = {
                "provider_protocol": "scripted",
                "provider_model": "scripted-model",
                "input_tokens": call * 10,
                "cached_tokens": call,
                "output_tokens": call,
                "total_tokens": call * 11,
            }
            return output

    client = UsageScriptedModelClient(
        [
            '<tool>{"name":"read_file","args":{"path":"app.py","start":1,"end":20}}</tool>',
            '<tool>{"name":"patch_file","args":{"path":"app.py","old_text":"VALUE = 1","new_text":"VALUE = 2"}}</tool>',
            '<tool>{"name":"run_shell","args":{"command":"python -c \\\"from pathlib import Path; assert \'VALUE = 2\' in Path(\'app.py\').read_text()\\\"","timeout":20}}</tool>',
            "<final>Implemented and verified the fix.</final>",
        ]
    )
    row = run_runtime_task(
        task,
        {"task_id": task["task_id"], "run_key": "scripted-smoke"},
        output_dir=tmp_path / "output",
        max_steps=6,
        model_client=client,
    )
    assert row["runtime_completed"] is True
    assert row["patch_nonempty"] is True
    assert "VALUE = 2" in (tmp_path / "output/runs/scripted-smoke/patch.diff").read_text(
        encoding="utf-8"
    )
    assert row["changed_paths"] == ["app.py"]
    assert row["usage_source"] == "actual"
    assert row["input_tokens"] == 100
    assert row["cached_tokens"] == 10
    assert row["output_tokens"] == 10
    assert row["total_tokens"] == 110
    assert row["report_path"]
    assert row["trace_path"]

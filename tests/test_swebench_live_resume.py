from scripts.run_swebench_live_resume_experiment import (
    _target_checkpoint,
    run_stale_memory_probe,
)


def test_target_checkpoint_waits_for_fifth_successful_tool_checkpoint():
    events = []
    for index in range(1, 6):
        events.extend(
            [
                {
                    "event": "tool_executed",
                    "name": "read_file",
                    "tool_status": "ok",
                },
                {
                    "event": "checkpoint_created",
                    "checkpoint_id": f"ckpt_{index}",
                    "trigger": "tool_executed",
                },
            ]
        )

    assert _target_checkpoint(events[:-1], 5) is None
    assert _target_checkpoint(events, 5) == {
        "checkpoint_id": "ckpt_5",
        "successful_tool_steps": 5,
        "tool_steps": 5,
    }


def test_stale_memory_probe_invalidates_summary_before_resume_prompt(tmp_path):
    result = run_stale_memory_probe(tmp_path / "probe")

    assert result["status"] == "passed"
    assert result["resume_status"] == "partial-stale"
    assert result["stale_summary_invalidations"] == 1
    assert result["false_stale_accept_count"] == 0
    assert result["checks"]["stale_summary_absent_from_prompt"] is True

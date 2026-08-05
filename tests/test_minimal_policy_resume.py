import json

from ponytail import Pico, SessionStore, WorkspaceContext
from ponytail.cli import handle_repl_command
from ponytail.core.task_state import TaskState
from ponytail.testing import ScriptedModelClient


def build_agent(tmp_path, outputs=None, *, session_store=None, **kwargs):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return Pico(
        model_client=ScriptedModelClient(outputs or ["<final>ok</final>"]),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=session_store or SessionStore(tmp_path / ".pico" / "sessions"),
        approval_policy=kwargs.pop("approval_policy", "auto"),
        **kwargs,
    )


def resume_agent(agent, outputs=None, **kwargs):
    return Pico.from_session(
        model_client=ScriptedModelClient(outputs or ["<final>resumed</final>"]),
        workspace=WorkspaceContext.build(agent.root),
        session_store=agent.session_store,
        session_id=agent.session["id"],
        approval_policy=kwargs.pop("approval_policy", "auto"),
        **kwargs,
    )


def create_checkpoint(agent, goal="Continue the task"):
    task_state = TaskState.create(task_id="task_policy_resume", user_request=goal)
    return agent.create_checkpoint(task_state, goal, trigger="test")


def read_trace(agent):
    return [
        json.loads(line)
        for line in agent.run_store.trace_path(agent.current_task_state).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_policy_session_and_checkpoint_round_trip_from_disk(tmp_path):
    agent = build_agent(tmp_path)
    handle_repl_command(agent, "/minimal enforce")
    before_prompt, before_metadata = agent._build_prompt_and_metadata("inspect README")
    checkpoint = create_checkpoint(agent)

    persisted = json.loads(agent.session_path.read_text(encoding="utf-8"))
    persisted_policy = persisted["minimal_policy"]
    assert persisted_policy["mode"] == "enforce"
    assert persisted_policy["policy_version"] == "minimal-policy-v1"
    assert persisted_policy["activation_source"] == "cli"
    assert persisted_policy["updated_at"]
    assert checkpoint["minimal_policy"] == {
        "mode": "enforce",
        "effective_mode": "enforce",
        "policy_version": "minimal-policy-v1",
        "rule_hash": persisted_policy["rule_hash"],
        "compatibility_status": "compatible",
    }

    resumed = resume_agent(agent)
    after_prompt, after_metadata = resumed._build_prompt_and_metadata("inspect README")

    assert resumed.session["minimal_policy"] == persisted_policy
    assert "Minimal change policy:" in before_prompt
    assert "Minimal change policy:" in after_prompt
    assert after_metadata["prefix_hash"] == before_metadata["prefix_hash"]
    assert after_metadata["prompt_cache_key"] == before_metadata["prompt_cache_key"]
    assert after_metadata["minimal_policy"]["activation_source"] == "cli"


def test_resume_keeps_policy_but_invalidates_stale_file_summary(tmp_path):
    file_path = tmp_path / "service.py"
    file_path.write_text("VALUE = 'old'\n", encoding="utf-8")
    agent = build_agent(tmp_path)
    handle_repl_command(agent, "/minimal enforce")
    agent.memory.set_file_summary("service.py", "service.py still contains old behavior")
    agent.memory.remember_file("service.py")
    create_checkpoint(agent, "Update service behavior")
    file_path.write_text("VALUE = 'new'\n", encoding="utf-8")

    resumed = resume_agent(agent)
    prompt, metadata = resumed._build_prompt_and_metadata("Continue safely")

    assert resumed.session["minimal_policy"]["mode"] == "enforce"
    assert metadata["resume_status"] == "partial-stale"
    assert metadata["stale_paths"] == ["service.py"]
    assert "service.py still contains old behavior" not in prompt
    assert "Minimal change policy:" in prompt
    assert "Current user request:\nContinue safely" in prompt


def test_workspace_mismatch_retains_observe_policy_and_reports_resume_version(tmp_path):
    agent = build_agent(tmp_path)
    handle_repl_command(agent, "/minimal observe")
    checkpoint = create_checkpoint(agent)

    resumed = resume_agent(agent, approval_policy="never")
    assert resumed.ask("Summarize the restored runtime state") == "resumed"

    assert resumed.last_prompt_metadata["resume_status"] == "workspace-mismatch"
    assert resumed.last_prompt_metadata["minimal_policy"]["mode"] == "observe"
    assert resumed.last_prompt_metadata["minimal_policy"]["effective_mode"] == "observe"
    assert resumed.last_prompt_metadata["minimal_policy"]["policy_version"] == "minimal-policy-v1"
    assert checkpoint["minimal_policy"]["mode"] == "observe"

    report = json.loads(
        resumed.run_store.report_path(resumed.current_task_state).read_text(encoding="utf-8")
    )
    assert report["minimal_policy_resume"]["policy_version"] == "minimal-policy-v1"
    assert report["minimal_policy_resume"]["checkpoint_match"] is True
    prompt_event = next(event for event in read_trace(resumed) if event["event"] == "prompt_built")
    assert prompt_event["prompt_metadata"]["minimal_policy"]["policy_version"] == "minimal-policy-v1"


def test_unknown_future_policy_version_falls_back_without_silent_rule_reuse(tmp_path):
    agent = build_agent(tmp_path)
    agent.session["minimal_policy"] = {
        "mode": "enforce",
        "policy_version": "minimal-policy-v999",
        "activation_source": "config",
        "updated_at": "2026-08-04T16:00:00+08:00",
        "rule_hash": "future-rule-hash",
        "observations": [],
    }
    checkpoint = create_checkpoint(agent)

    resumed = resume_agent(agent)
    prompt, metadata = resumed._build_prompt_and_metadata("Inspect compatibility")

    assert resumed.session["minimal_policy"]["mode"] == "enforce"
    assert resumed.session["minimal_policy"]["policy_version"] == "minimal-policy-v999"
    assert metadata["minimal_policy"]["effective_mode"] == "off"
    assert metadata["minimal_policy"]["compatibility_status"] == "unsupported-version"
    assert metadata["minimal_policy"]["compatibility_notice"]
    assert checkpoint["minimal_policy"]["rule_hash"] == "future-rule-hash"
    assert "Minimal change policy:" not in prompt
    assert "Current user request:\nInspect compatibility" in prompt

    assert resumed.ask("Report policy compatibility") == "resumed"
    report = json.loads(
        resumed.run_store.report_path(resumed.current_task_state).read_text(encoding="utf-8")
    )
    assert report["minimal_policy_resume"]["compatibility_status"] == "unsupported-version"
    prompt_event = next(event for event in read_trace(resumed) if event["event"] == "prompt_built")
    assert (
        prompt_event["prompt_metadata"]["minimal_policy"]["compatibility_status"]
        == "unsupported-version"
    )

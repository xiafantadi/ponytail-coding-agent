import json

from pico import Pico, SessionStore, WorkspaceContext
from pico.cli import handle_repl_command
from pico.testing import ScriptedModelClient


def build_agent(tmp_path, outputs=None, session=None):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return Pico(
        model_client=ScriptedModelClient(outputs or ["<final>reviewed</final>"]),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".pico" / "sessions"),
        approval_policy="auto",
        session=session,
    )


def test_minimal_status_and_mode_switch_do_not_call_model(tmp_path):
    agent = build_agent(tmp_path)

    handled, should_exit, status = handle_repl_command(agent, "/minimal")
    assert handled is True
    assert should_exit is False
    assert "minimal policy: off" in status
    assert "prompt rules: disabled" in status

    _, _, switched = handle_repl_command(agent, "/minimal enforce")
    assert "minimal policy: enforce" in switched
    assert "prompt rules: enabled" in switched
    assert agent.model_client.prompts == []


def test_minimal_mode_switch_is_persisted_and_emits_structured_event(tmp_path):
    agent = build_agent(tmp_path)

    handled, _, output = handle_repl_command(agent, "/minimal observe")

    assert handled is True
    assert "minimal policy: observe" in output
    persisted = json.loads(agent.session_path.read_text(encoding="utf-8"))
    assert persisted["minimal_policy"]["mode"] == "observe"
    events = [
        json.loads(line)
        for line in agent.session_event_bus.path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    changed = next(event for event in events if event["event"] == "minimal_policy_changed")
    assert changed["mode"] == "observe"
    assert changed["previous_mode"] == "off"
    assert changed["policy_version"] == "minimal-policy-v1"


def test_minimal_invalid_mode_keeps_previous_state(tmp_path):
    agent = build_agent(tmp_path)
    handle_repl_command(agent, "/minimal enforce")

    _, _, output = handle_repl_command(agent, "/minimal unknown")

    assert "off, observe, enforce" in output
    assert "minimal policy: enforce" in handle_repl_command(agent, "/minimal")[2]


def test_minimal_mode_survives_new_runtime_from_saved_session(tmp_path):
    first = build_agent(tmp_path)
    handle_repl_command(first, "/minimal enforce")
    saved = json.loads(first.session_path.read_text(encoding="utf-8"))

    second = build_agent(tmp_path, session=saved)

    assert "minimal policy: enforce" in handle_repl_command(second, "/minimal")[2]
    assert second.model_client.prompts == []


def test_minimal_review_uses_existing_skill_runtime_and_read_only_tool_profile(tmp_path):
    agent = build_agent(tmp_path, ["<final>reviewed</final>"])

    handled, should_exit, output = handle_repl_command(agent, "/minimal-review duplicated helper")

    assert handled is True
    assert should_exit is False
    assert output == "reviewed"
    assert "Skill: minimal-review" in agent.model_client.prompts[-1]
    assert "run_shell" in agent.model_client.prompts[-1]
    events = agent.session_event_bus.path.read_text(encoding="utf-8")
    assert '"event": "skill_invoked"' in events


def test_skills_command_lists_minimal_review(tmp_path):
    agent = build_agent(tmp_path)

    _, _, output = handle_repl_command(agent, "/skills")

    assert "minimal-review" in output


def test_policy_mode_changes_rebuild_stable_prefix_and_cache_identity(tmp_path):
    agent = build_agent(tmp_path)

    off_prompt, off_metadata = agent._build_prompt_and_metadata("inspect README")
    off_hash = off_metadata["prefix_hash"]
    handle_repl_command(agent, "/minimal observe")
    observe_prompt, observe_metadata = agent._build_prompt_and_metadata("inspect README")
    handle_repl_command(agent, "/minimal enforce")
    enforce_prompt, enforce_metadata = agent._build_prompt_and_metadata("inspect README")

    assert len(observe_prompt) == len(off_prompt)
    assert off_hash != observe_metadata["prefix_hash"]
    assert observe_metadata["minimal_policy"]["mode"] == "observe"
    assert observe_metadata["minimal_policy"]["rule_chars"] == 0
    assert "Minimal change policy:" in enforce_prompt
    assert "Current user request:\ninspect README" in enforce_prompt
    assert enforce_metadata["minimal_policy"]["mode"] == "enforce"
    assert enforce_metadata["minimal_policy"]["prompt_rules_injected"] is True
    assert enforce_metadata["minimal_policy"]["rule_chars"] > 0
    assert observe_metadata["prefix_hash"] != enforce_metadata["prefix_hash"]


def test_enforce_rules_survive_prefix_section_tail_clipping(tmp_path):
    agent = build_agent(tmp_path)
    handle_repl_command(agent, "/minimal enforce")
    agent.context_manager.total_budget = 6000
    agent.context_manager.section_budgets = {
        "prefix": 4000,
        "memory": 1200,
        "skills": 600,
        "relevant_memory": 1000,
        "history": 6000,
    }
    agent.session["history"] = [
        {"role": "user", "content": "history " + ("x" * 12000)},
        {"role": "assistant", "content": "answer " + ("y" * 12000)},
    ]

    prompt, metadata = agent._build_prompt_and_metadata("keep the request")

    assert "Minimal change policy:" in prompt
    assert "Current user request:\nkeep the request" in prompt
    assert metadata["minimal_policy"]["prompt_rules_injected"] is True


def test_policy_evidence_is_consistent_across_task_state_trace_and_report(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            '<tool name="write_file" path="notes.txt"><content>hello\n</content></tool>',
            "<final>Done.</final>",
        ],
    )
    handle_repl_command(agent, "/minimal enforce")

    assert agent.ask("Create notes.txt") == "Done."

    task_state = json.loads(
        agent.run_store.task_state_path(agent.current_task_state).read_text(encoding="utf-8")
    )
    report = json.loads(
        agent.run_store.report_path(agent.current_task_state).read_text(encoding="utf-8")
    )
    trace = [
        json.loads(line)
        for line in agent.run_store.trace_path(agent.current_task_state).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    policy = task_state["minimality_metrics"]

    assert task_state["minimal_policy_mode"] == "enforce"
    assert task_state["minimal_policy_version"] == "minimal-policy-v1"
    assert task_state["minimal_policy_hash"] == policy["minimal_policy_hash"]
    assert report["minimality_metrics"] == policy
    assert report["task_state"]["minimal_policy_hash"] == policy["minimal_policy_hash"]
    assert policy["minimal_policy_prompt_chars"] > 0
    assert policy["changed_files"] == 1
    assert policy["tool_steps"] == 1
    assert policy["attempts"] == 2
    assert policy["added_lines"] is None
    assert policy["dependencies_added"] is None

    applied = next(event for event in trace if event["event"] == "minimal_policy_applied")
    audited = next(event for event in trace if event["event"] == "minimality_audit_completed")
    for event in (applied, audited):
        assert event["run_id"] == agent.current_task_state.run_id
        assert event["created_at"]
        assert event["minimal_policy_mode"] == "enforce"
        assert event["minimal_policy_version"] == "minimal-policy-v1"
        assert event["minimal_policy_hash"] == policy["minimal_policy_hash"]


def test_policy_evidence_preserves_null_for_unavailable_provider_usage(tmp_path):
    agent = build_agent(tmp_path, ["<final>Done.</final>"])

    assert agent.ask("Inspect the repository") == "Done."

    report = json.loads(
        agent.run_store.report_path(agent.current_task_state).read_text(encoding="utf-8")
    )
    metrics = report["minimality_metrics"]

    assert metrics["minimal_policy_mode"] == "off"
    assert metrics["input_tokens"] is None
    assert metrics["cached_input_tokens"] is None
    assert metrics["output_tokens"] is None
    assert metrics["reasoning_tokens"] is None

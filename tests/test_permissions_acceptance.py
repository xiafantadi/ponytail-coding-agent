import json
from unittest.mock import patch

from pico.testing import ScriptedModelClient
from pico import OpenAICompatibleModelClient, Pico, SessionStore, WorkspaceContext
from pico.cli import handle_repl_command
from pico.core.permissions import PermissionDecision
from pico.core.tool_repetition import is_repeated_tool_call
from pico.features.sandbox.config import SandboxConfig


def build_agent(tmp_path, outputs=None, **kwargs):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    workspace = WorkspaceContext.build(tmp_path)
    store = SessionStore(tmp_path / ".pico" / "sessions")
    approval_policy = kwargs.pop("approval_policy", "auto")
    return Pico(
        model_client=ScriptedModelClient(outputs or []),
        workspace=workspace,
        session_store=store,
        approval_policy=approval_policy,
        **kwargs,
    )


def read_session_events(agent):
    return [
        json.loads(line)
        for line in agent.session_event_bus.path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]


def test_permission_checker_is_the_single_default_tool_gate(tmp_path):
    agent = build_agent(tmp_path, approval_policy="never")

    read_decision = agent.permission_checker.check(
        agent.tools["read_file"], {"path": "README.md"}
    )
    shell_decision = agent.permission_checker.check(
        agent.tools["run_shell"], {"command": "echo hi", "timeout": 20}
    )

    assert read_decision == PermissionDecision.allow("read_only")
    assert shell_decision == PermissionDecision.deny(
        "approval_denied", security_event_type="approval_denied"
    )

    result = agent.run_tool("run_shell", {"command": "echo hi", "timeout": 20})

    assert result == "error: approval denied for run_shell"
    assert agent._last_tool_result_metadata["tool_error_code"] == "approval_denied"
    assert any(
        event["event"] == "permission_decision"
        and event["tool_name"] == "run_shell"
        and event["decision"] == "deny"
        and event["reason"] == "approval_denied"
        for event in read_session_events(agent)
    )


def test_native_provider_tool_call_still_passes_through_permission_gate(tmp_path):
    captured = {}
    responses = [
        {
            "output": [
                {
                    "type": "function_call",
                    "name": "run_shell",
                    "arguments": '{"command":"echo blocked","timeout":20}',
                }
            ]
        },
        {"output_text": "<final>The command was denied.</final>"},
    ]

    class FakeResponse:
        headers = {"Content-Type": "application/json"}

        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(self.body).encode("utf-8")

    def fake_urlopen(request, timeout):
        del timeout
        captured.setdefault("requests", []).append(
            json.loads(request.data.decode("utf-8"))
        )
        return FakeResponse(responses.pop(0))

    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    client = OpenAICompatibleModelClient(
        model="gpt-test",
        base_url="https://example.test/v1",
        api_key="sk-test",
        temperature=None,
        timeout=30,
    )
    agent = Pico(
        model_client=client,
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".pico" / "sessions"),
        approval_policy="never",
    )

    with patch("urllib.request.urlopen", fake_urlopen):
        answer = agent.ask("Inspect permission behavior and report the result.")

    assert answer == "The command was denied."
    first_request = captured["requests"][0]
    read_file_spec = next(
        item for item in first_request["tools"] if item["name"] == "read_file"
    )
    assert first_request["tool_choice"] == "auto"
    assert read_file_spec["parameters"]["required"] == ["path"]
    assert read_file_spec["parameters"]["properties"]["path"]["type"] == "string"
    assert any(
        item.get("role") == "tool"
        and item.get("name") == "run_shell"
        and "approval denied" in item.get("content", "")
        for item in agent.session["history"]
    )
    assert any(
        event["event"] == "permission_decision"
        and event["tool_name"] == "run_shell"
        and event["decision"] == "deny"
        for event in read_session_events(agent)
    )


def test_run_shell_required_sandbox_fails_closed_after_permission(tmp_path):
    agent = build_agent(
        tmp_path,
        [],
        approval_policy="auto",
        sandbox_config=SandboxConfig(mode="required", backend="bubblewrap"),
    )
    agent.sandbox_runner.which = lambda name: None

    result = agent.run_tool("run_shell", {"command": "echo hi", "timeout": 20})

    assert "sandbox required but unavailable" in result
    assert agent._last_tool_result_metadata["tool_error_code"] == "tool_failed"


def test_run_shell_best_effort_sandbox_degrades_and_keeps_permission_gate(tmp_path):
    agent = build_agent(
        tmp_path,
        [],
        approval_policy="auto",
        sandbox_config=SandboxConfig(mode="best_effort", backend="bubblewrap"),
    )
    agent.sandbox_runner.which = lambda name: None

    result = agent.run_tool("run_shell", {"command": "echo hi", "timeout": 20})

    assert "exit_code: 0" in result
    assert "hi" in result
    assert any(
        event["event"] == "sandbox_unavailable" for event in read_session_events(agent)
    )


def test_shell_verification_can_repeat_after_a_distinct_workspace_change():
    test_args = {"command": "python -m pytest -q", "timeout": 20}
    history = [
        {"role": "user", "content": "fix the bug"},
        {"role": "tool", "name": "run_shell", "args": test_args, "workspace_changed": False},
        {"role": "tool", "name": "run_shell", "args": test_args, "workspace_changed": False},
        {
            "role": "tool",
            "name": "patch_file",
            "args": {"path": "app.py", "old_text": "bad", "new_text": "good"},
            "workspace_changed": True,
        },
    ]

    assert is_repeated_tool_call(history, "run_shell", test_args) is False


def test_repeated_shell_mutation_does_not_reset_its_own_guard():
    edit_args = {"command": "python rewrite.py", "timeout": 20}
    history = [
        {"role": "user", "content": "fix the bug"},
        {"role": "tool", "name": "run_shell", "args": edit_args, "workspace_changed": True},
        {"role": "tool", "name": "run_shell", "args": edit_args, "workspace_changed": True},
    ]

    assert is_repeated_tool_call(history, "run_shell", edit_args) is True


def test_plan_mode_switches_tool_profile_and_allows_only_active_plan_file(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            '<tool name="write_file" path=".pico/plans/v3-plan.md"><content># Plan\n- Gate 1\n</content></tool>',
            "<final>Plan ready.</final>",
        ],
        max_steps=3,
    )

    assert agent.active_tool_profile.name == "default"

    plan_path = agent.enter_plan_mode("v3")

    assert plan_path == ".pico/plans/v3-plan.md"
    assert agent.active_tool_profile.name == "plan"
    assert "run_shell" not in agent.active_tool_profile.allowed_tools

    rejected = agent.run_tool(
        "write_file", {"path": "src.py", "content": "print('no')\n"}
    )
    assert (
        rejected
        == "error: plan mode can only write the active plan artifact (.pico/plans/v3-plan.md)"
    )
    assert not (tmp_path / "src.py").exists()

    answer = agent.ask("draft the plan")

    assert answer == "Plan ready."
    assert agent.active_tool_profile.name == "default"
    assert (
        (tmp_path / ".pico" / "plans" / "v3-plan.md")
        .read_text(encoding="utf-8")
        .startswith("# Plan")
    )
    events = read_session_events(agent)
    assert any(
        event["event"] == "permission_decision"
        and event["tool_name"] == "write_file"
        and event["decision"] == "deny"
        and event["reason"] == "plan_mode_path_mismatch"
        for event in events
    )
    assert any(
        event["event"] == "permission_decision"
        and event["tool_name"] == "write_file"
        and event["decision"] == "allow"
        and event["reason"] == "plan_artifact_write"
        for event in events
    )


def test_repeated_plan_mode_denial_is_blocked_before_hitting_step_limit(tmp_path):
    bad_call = '<tool name="write_file" path="src.py"><content>print("no")\n</content></tool>'
    agent = build_agent(
        tmp_path,
        [
            bad_call,
            bad_call,
            bad_call,
            '<tool name="write_file" path=".pico/plans/repeat-plan.md"><content># Plan\n- Retry stopped.\n</content></tool>',
            "<final>Plan ready.</final>",
        ],
        max_steps=6,
    )
    agent.enter_plan_mode("repeat")

    assert agent.ask("verify repeated plan-mode denial handling") == "Plan ready."
    assert not (tmp_path / "src.py").exists()

    trace = [
        json.loads(line)
        for line in (agent.current_run_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    write_events = [
        event
        for event in trace
        if event["event"] == "tool_executed" and event.get("name") == "write_file"
    ]

    assert [event.get("tool_error_code") for event in write_events[:3]] == [
        "plan_mode_path_mismatch",
        "repeated_identical_call",
        "repeated_identical_call",
    ]
    assert write_events[3]["status"] == "ok"


def test_plan_mode_does_not_allow_retargeting_active_plan_with_enter_tool(tmp_path):
    agent = build_agent(tmp_path)

    agent.enter_plan_mode("original")

    rejected = agent.run_tool(
        "enter_plan_mode", {"topic": "retarget", "path": "src.py"}
    )

    assert "plan mode" in rejected
    assert agent.plan_mode.plan_path == ".pico/plans/original-plan.md"


def test_plan_mode_rejects_arbitrary_workspace_plan_path(tmp_path):
    agent = build_agent(tmp_path)

    rejected = agent.run_tool(
        "enter_plan_mode", {"topic": "retarget", "path": "src/auth.py"}
    )

    assert "plan path must stay under .pico/plans/" in rejected
    assert agent.runtime_mode == "default"


def test_repl_plan_command_reports_bad_plan_path_without_crashing(tmp_path):
    agent = build_agent(tmp_path)

    handled, should_exit, output = handle_repl_command(
        agent, "/plan auth .pico/plans/../escape.md"
    )

    assert handled is True
    assert should_exit is False
    assert output == "error: plan path must stay under .pico/plans/"
    assert agent.runtime_mode == "default"

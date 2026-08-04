from pico import Pico, SessionStore, WorkspaceContext
from pico.cli import handle_repl_command
from pico.testing import ScriptedModelClient


def build_agent(tmp_path):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return Pico(
        model_client=ScriptedModelClient(["<final>ok</final>"]),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".pico" / "sessions"),
        approval_policy="auto",
    )


def test_policy_modes_have_expected_prompt_and_cache_contract(tmp_path):
    agent = build_agent(tmp_path)
    off_prompt, off_metadata = agent._build_prompt_and_metadata("inspect README")

    handle_repl_command(agent, "/minimal observe")
    observe_prompt, observe_metadata = agent._build_prompt_and_metadata("inspect README")

    handle_repl_command(agent, "/minimal enforce")
    enforce_prompt, enforce_metadata = agent._build_prompt_and_metadata("inspect README")

    assert len(observe_prompt) == len(off_prompt)
    assert off_metadata["prefix_hash"] != observe_metadata["prefix_hash"]
    assert observe_metadata["minimal_policy"]["rule_chars"] == 0
    assert "Minimal change policy:" in enforce_prompt
    assert enforce_metadata["minimal_policy"]["mode"] == "enforce"
    assert enforce_metadata["minimal_policy"]["rule_chars"] > 0
    assert enforce_metadata["minimal_policy"]["rule_hash"]
    assert observe_metadata["prefix_hash"] != enforce_metadata["prefix_hash"]


def test_current_request_survives_enforce_prefix_and_context_clipping(tmp_path):
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

    prompt, metadata = agent._build_prompt_and_metadata("keep this current request")

    assert "Minimal change policy:" in prompt
    assert "Current user request:\nkeep this current request" in prompt
    assert metadata["minimal_policy"]["prompt_rules_injected"] is True

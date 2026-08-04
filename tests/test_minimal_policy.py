import pytest

from pico.features.minimal_policy import (
    MINIMAL_POLICY_VERSION,
    MinimalChangePolicy,
    PolicyMode,
)


def test_default_policy_is_off_and_does_not_enter_prompt():
    policy = MinimalChangePolicy()

    assert policy.mode is PolicyMode.OFF
    assert policy.prompt_text() == ""


def test_policy_parses_all_supported_modes():
    assert MinimalChangePolicy.from_mode("off").mode is PolicyMode.OFF
    assert MinimalChangePolicy.from_mode("observe").mode is PolicyMode.OBSERVE
    assert MinimalChangePolicy.from_mode("enforce").mode is PolicyMode.ENFORCE


def test_invalid_mode_is_rejected_without_mutating_existing_policy():
    policy = MinimalChangePolicy.from_mode("observe")

    with pytest.raises(ValueError, match="off, observe, enforce"):
        policy.set_mode("invalid")

    assert policy.mode is PolicyMode.OBSERVE


def test_enforce_prompt_contains_decision_ladder_and_safety_retention_items():
    policy = MinimalChangePolicy.from_mode("enforce")
    prompt = policy.prompt_text()

    assert "reuse repository code" in prompt
    assert "standard library" in prompt
    assert "platform-native capability" in prompt
    assert "input validation" in prompt
    assert "permission controls" in prompt
    assert "non-trivial logic tests" in prompt


def test_observe_records_opportunities_without_entering_prompt():
    policy = MinimalChangePolicy.from_mode("observe")

    recorded = policy.observe(["duplicate helper", "new dependency", "duplicate helper"])

    assert recorded == ("duplicate helper", "new dependency")
    assert policy.prompt_text() == ""
    assert policy.to_dict()["observations"] == ["duplicate helper", "new dependency"]


def test_policy_serializes_and_restores_all_state():
    policy = MinimalChangePolicy.from_mode("observe")
    policy.observe(["unnecessary abstraction"])

    restored = MinimalChangePolicy.from_dict(policy.to_dict())

    assert restored.to_dict() == policy.to_dict()
    assert restored.mode is PolicyMode.OBSERVE


def test_rule_hash_is_stable_for_the_same_version():
    first = MinimalChangePolicy.from_mode("enforce")
    second = MinimalChangePolicy.from_dict(first.to_dict())

    assert first.policy_version == MINIMAL_POLICY_VERSION
    assert first.rule_hash == second.rule_hash
    assert len(first.prompt_text()) <= 800


def test_policy_observe_does_not_change_rule_hash():
    policy = MinimalChangePolicy.from_mode("observe")
    before = policy.rule_hash

    policy.observe(["extra file"])

    assert policy.rule_hash == before

"""Reduce trace events into TaskState evidence summaries.

This module is the bridge from append-only trace facts to compact report-ready
state. It does not re-read trace files; runtime consumers call it as events are
emitted during a run.
"""

from .final_readiness import reduce_final_readiness_summary
from .governance import reduce_governance_summary
from .context_budget_summary import (
    context_budget_summary,
    update_from_orchestrator,
)
from .turn_transitions import reduce_transition_summary
from .verification import reduce_verification_signal


def update_evidence_summaries(summaries, event, changed_paths=None):
    summaries = dict(summaries or {})
    if event.get("event") == "loop_transition":
        summaries["transition_summary"] = reduce_transition_summary(
            summaries.get("transition_summary", {}), event
        )
    elif event.get("event") == "prompt_built":
        summaries["context_budget_summary"] = context_budget_summary(
            event.get("prompt_metadata", {})
        )
    elif event.get("event") == "context_orchestrator_decision":
        summaries["context_budget_summary"] = update_from_orchestrator(
            summaries.get("context_budget_summary", {}), event
        )
    elif event.get("event") == "governance_decision":
        summaries["governance_summary"] = reduce_governance_summary(
            summaries.get("governance_summary", {}), event
        )
    elif event.get("event") == "tool_executed":
        summaries["verification_signal"] = reduce_verification_signal(
            summaries.get("verification_signal", {}), event, changed_paths or []
        )
    elif event.get("event") == "final_readiness_decision":
        summaries["final_readiness_summary"] = reduce_final_readiness_summary(
            summaries.get("final_readiness_summary", {}), event
        )
    elif event.get("event") in {"prompt_built", "minimal_policy_applied"}:
        summaries["minimal_policy"] = dict(
            event.get("minimal_policy")
            or event.get("prompt_metadata", {}).get("minimal_policy", {})
            or {}
        )
    elif event.get("event") == "minimality_audit_completed":
        summaries["minimality_metrics"] = dict(event.get("minimality_metrics", {}) or {})
        summaries["minimality_audit"] = dict(event.get("minimality_audit", {}) or {})
    return summaries


def build_minimality_metrics(task_state, policy_metadata, completion_metadata, duration_ms):
    policy = dict(policy_metadata or {})
    usage = dict(completion_metadata or {})
    verification = dict(task_state.evidence_summaries.get("verification_signal", {}) or {})
    return {
        "minimal_policy_mode": policy.get("mode"),
        "minimal_policy_version": policy.get("policy_version"),
        "minimal_policy_hash": policy.get("rule_hash"),
        "minimal_policy_prompt_chars": policy.get("rule_chars"),
        "changed_files": len(task_state.changed_paths),
        "added_lines": None,
        "deleted_lines": None,
        "dependencies_added": None,
        "input_tokens": usage.get("input_tokens"),
        "cached_input_tokens": usage.get("cached_input_tokens", usage.get("cached_tokens")),
        "output_tokens": usage.get("output_tokens"),
        "reasoning_tokens": usage.get("reasoning_tokens"),
        "tool_steps": task_state.tool_steps,
        "attempts": task_state.attempts,
        "duration_ms": duration_ms,
        "verification_status": verification.get("state", "unknown"),
    }

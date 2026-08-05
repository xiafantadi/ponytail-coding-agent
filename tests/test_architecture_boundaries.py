"""Architecture budget tests for runtime module boundaries."""

from pathlib import Path


def test_core_modules_stay_below_entropy_budget():
    root = Path(__file__).resolve().parents[1]
    budgets = {
        "ponytail/core/runtime.py": 950,
        "ponytail/core/before_final_hooks.py": 140,
        "ponytail/core/evidence_summaries.py": 90,
        "ponytail/core/final_readiness.py": 120,
        "ponytail/core/final_readiness_artifacts.py": 160,
        "ponytail/core/final_readiness_context.py": 60,
        "ponytail/core/final_readiness_reasons.py": 60,
        "ponytail/core/final_readiness_tools.py": 100,
        "ponytail/core/task_intent.py": 60,
        "ponytail/core/governance.py": 80,
        "ponytail/core/runtime_events.py": 90,
        "ponytail/core/runtime_consumers.py": 90,
        "ponytail/core/artifacts.py": 130,
        "ponytail/core/task_state.py": 140,
        "ponytail/core/todo_ledger.py": 120,
        "ponytail/core/worker_manager.py": 220,
        "ponytail/core/context_manager.py": 420,
        "ponytail/core/context_budget_summary.py": 130,
        "ponytail/core/context_handoff.py": 240,
        "ponytail/core/context_orchestrator.py": 210,
        "ponytail/core/context_pressure.py": 140,
        "ponytail/core/context_report.py": 140,
        "ponytail/core/context_retention.py": 90,
        "ponytail/core/context_replacements.py": 160,
        "ponytail/core/context_sections.py": 170,
        "ponytail/core/context_usage.py": 130,
        "ponytail/core/compact.py": 250,
        "ponytail/core/compact_summary.py": 130,
        "ponytail/core/completion_governance.py": 240,
        "ponytail/core/engine.py": 470,
        "ponytail/core/model_errors.py": 100,
        "ponytail/core/model_router.py": 40,
        "ponytail/core/permissions.py": 140,
        "ponytail/core/tool_policy.py": 90,
        "ponytail/core/plan_mode.py": 140,
        "ponytail/core/tool_executor.py": 181,
        "ponytail/core/tool_profiles.py": 80,
        "ponytail/core/tool_result_artifacts.py": 60,
        "ponytail/core/turn_transitions.py": 90,
        "ponytail/core/verification.py": 80,
        "ponytail/core/turn_history.py": 280,
        "ponytail/core/media_history.py": 20,
        "ponytail/features/skills.py": 220,
        "ponytail/features/skills_bundled.py": 120,
        "ponytail/features/skills_runtime.py": 140,
        "ponytail/tools/registry.py": 360,
        "ponytail/tools/todos.py": 80,
        "ponytail/tools/agents.py": 90,
    }

    for relative_path, max_lines in budgets.items():
        line_count = len((root / relative_path).read_text(encoding="utf-8").splitlines())
        assert line_count <= max_lines, f"{relative_path} has {line_count} lines, budget is {max_lines}"

"""Validate the minimal-change task suite before an experiment."""

from __future__ import annotations

import argparse
import json
from collections import Counter

from pico.evaluation.minimal_change import load_minimal_change_tasks


EXPECTED_CATEGORY_COUNTS = {
    "overbuild_trap": 6,
    "bug_fix": 6,
    "security": 6,
}


def validate_suite(path="benchmarks/minimal_change/tasks.json"):
    data = load_minimal_change_tasks(path)
    tasks = data["tasks"]
    counts = Counter(task["category"] for task in tasks)
    invalid_tasks = [task["task_id"] for task in tasks if task["status"] != "valid"]
    errors = []
    if len(tasks) != 18:
        errors.append(f"expected 18 tasks, got {len(tasks)}")
    if counts != EXPECTED_CATEGORY_COUNTS:
        errors.append(f"unexpected category counts: {dict(counts)}")
    if invalid_tasks:
        errors.append(f"invalid tasks: {', '.join(invalid_tasks)}")
    return {
        "status": "valid" if not errors else "invalid",
        "task_count": len(tasks),
        "category_counts": dict(sorted(counts.items())),
        "invalid_tasks": invalid_tasks,
        "errors": errors,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--path", default="benchmarks/minimal_change/tasks.json")
    args = parser.parse_args(argv)
    if not args.validate_only:
        parser.error("only --validate-only is supported in Step 8")
    result = validate_suite(args.path)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0 if result["status"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())

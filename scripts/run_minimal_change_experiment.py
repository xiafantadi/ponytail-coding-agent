"""Validate the minimal-change task suite before an experiment."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ponytail.config import resolve_provider_config  # noqa: E402
from ponytail.evaluation.minimal_change import load_minimal_change_tasks  # noqa: E402
from ponytail.evaluation.minimal_change_experiment import (  # noqa: E402
    EXPERIMENT_ARMS,
    _build_provider_args,
    build_manifest,
    run_one,
    select_tasks,
    validate_experiment_config,
    write_experiment_artifacts,
)


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


def build_arg_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-profile", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--tasks", default="all")
    parser.add_argument("--arms", default=",".join(EXPERIMENT_ARMS))
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--output-dir", default="artifacts/minimal-change/experiment")
    parser.add_argument("--config", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--resume-manifest", default=None)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--path", default="benchmarks/minimal_change/tasks.json")
    return parser


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    if not args.validate_only:
        return run_experiment(args)
    result = validate_suite(args.path)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0 if result["status"] == "valid" else 1


def run_experiment(args):
    data = load_minimal_change_tasks(args.path)
    selection = int(args.tasks) if str(args.tasks).isdigit() else args.tasks
    tasks = select_tasks(data["tasks"], selection)
    arms = validate_experiment_config(
        tasks,
        [item.strip() for item in args.arms.split(",")],
        args.repetitions,
        args.max_steps,
        args.timeout,
    )
    config = resolve_provider_config(
        args.provider_profile,
        start=ROOT,
        config_path=args.config,
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
    )
    if not config.api_key:
        print(
            f"provider profile {config.name!r} has no API key; configure the environment or --config",
            file=sys.stderr,
        )
        return 2

    manifest = build_manifest(
        tasks,
        arms,
        args.repetitions,
        args.seed,
        args.max_steps,
        args.timeout,
        config.name,
        config.model,
    )
    prior_rows = []
    if args.resume_manifest:
        prior = json.loads(Path(args.resume_manifest).read_text(encoding="utf-8"))
        prior_rows = list(prior.get("rows", []))
    completed = {row.get("run_key") for row in prior_rows if row.get("run_key")}
    rows = list(prior_rows)
    provider_args = _build_provider_args(
        provider=config.name,
        model=args.model,
        config=args.config,
        base_url=args.base_url,
        api_key=args.api_key,
        timeout=args.timeout,
    )
    by_id = {task["task_id"]: task for task in tasks}
    for entry in manifest["plan"]:
        if entry["run_key"] in completed:
            continue
        rows.append(
            run_one(
                by_id[entry["task_id"]],
                entry,
                output_dir=args.output_dir,
                provider_args=provider_args,
                max_steps=args.max_steps,
                timeout=args.timeout,
            )
        )
        write_experiment_artifacts(args.output_dir, manifest, rows)
    write_experiment_artifacts(args.output_dir, manifest, rows)
    print(json.dumps({"status": "completed", "runs": len(rows)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Run a small real-Issue experiment through the existing Pico runtime."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pico.config import resolve_provider_config  # noqa: E402
from pico.evaluation.minimal_change_experiment import (  # noqa: E402
    _build_provider_args,
    build_manifest,
    run_one,
    select_tasks,
    write_experiment_artifacts,
)
from pico.evaluation.real_issue import (  # noqa: E402
    build_runtime_task,
    enrich_real_issue_row,
    load_real_issue_tasks,
    parse_source_args,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-profile", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--tasks", default="all")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--config", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--path", default="benchmarks/real_issues/tasks.json")
    parser.add_argument("--verification-python", required=True)
    parser.add_argument("--source", action="append", default=[], metavar="TASK_ID=PATH")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    data = load_real_issue_tasks(args.path)
    selection = int(args.tasks) if str(args.tasks).isdigit() else args.tasks
    selected = select_tasks(data["tasks"], selection)
    sources = parse_source_args(args.source)
    missing = [task["task_id"] for task in selected if task["task_id"] not in sources]
    if missing:
        raise ValueError(f"missing --source for: {', '.join(missing)}")

    verifier_root = ROOT / "benchmarks" / "real_issues" / "verifiers"
    runtime_tasks = [
        build_runtime_task(
            task,
            source=sources[task["task_id"]],
            verification_python=args.verification_python,
            verifier_root=verifier_root,
        )
        for task in selected
    ]
    config = resolve_provider_config(
        args.provider_profile,
        start=ROOT,
        config_path=args.config,
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
    )
    if not config.api_key:
        print(f"provider profile {config.name!r} has no API key", file=sys.stderr)
        return 2

    manifest = build_manifest(
        runtime_tasks,
        ["minimal_policy"],
        args.repetitions,
        args.seed,
        args.max_steps,
        args.timeout,
        config.name,
        config.model,
    )
    manifest.update(
        {
            "suite_id": "real-ai-infrastructure-issues-v1",
            "repository_url": data["repository_url"],
            "issue_urls": [task["issue_url"] for task in selected],
        }
    )
    provider_args = _build_provider_args(
        provider=config.name,
        model=args.model,
        config=args.config,
        base_url=args.base_url,
        api_key=args.api_key,
        timeout=args.timeout,
    )
    by_id = {task["task_id"]: task for task in runtime_tasks}
    rows = []
    for entry in manifest["plan"]:
        task = by_id[entry["task_id"]]
        row = run_one(
            task,
            entry,
            output_dir=args.output_dir,
            provider_args=provider_args,
            max_steps=args.max_steps,
            timeout=args.timeout,
        )
        rows.append(enrich_real_issue_row(row, task))
        write_experiment_artifacts(args.output_dir, manifest, rows)
    print(json.dumps({"runs": len(rows), "status": "completed"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

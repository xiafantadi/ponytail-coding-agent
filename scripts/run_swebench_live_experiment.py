"""Run the frozen PonyCode SWE-bench-Live subset and official evaluator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ponytail.config import resolve_provider_config  # noqa: E402
from ponytail.evaluation.minimal_change_experiment import (  # noqa: E402
    _build_provider_args,
    build_manifest,
    select_tasks,
)
from ponytail.evaluation.real_issue import parse_source_args  # noqa: E402
from ponytail.evaluation.swebench_live import (  # noqa: E402
    build_official_evaluator_command,
    build_runtime_task,
    enrich_with_official_result,
    load_official_result,
    load_public_tasks,
    official_image_name,
    official_report_path,
    run_official_evaluator,
    run_runtime_task,
    write_official_predictions,
    write_result_artifacts,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-profile", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--tasks", default="all")
    parser.add_argument("--seed", type=int, default=20260808)
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--evaluation-timeout", type=int, default=1800)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--config", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--path", default="benchmarks/swebench_live/tasks.json")
    parser.add_argument("--source", action="append", default=[], metavar="INSTANCE_ID=PATH")
    parser.add_argument("--evaluator-python", required=True)
    parser.add_argument("--evaluator-root", required=True)
    parser.add_argument("--evaluator-dataset", required=True)
    parser.add_argument("--namespace", default="starryzhang")
    return parser


def parse_task_selection(value: str):
    value = str(value).strip()
    if value.lower() == "all":
        return ""
    return int(value) if value.isdigit() else value


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    data = load_public_tasks(args.path)
    selection = parse_task_selection(args.tasks)
    selected = select_tasks(
        [{"task_id": task["instance_id"], **task} for task in data["tasks"]],
        selection,
    )
    sources = parse_source_args(args.source)
    missing = [task["instance_id"] for task in selected if task["instance_id"] not in sources]
    if missing:
        raise ValueError(f"missing --source for: {', '.join(missing)}")
    runtime_tasks = [
        build_runtime_task(
            task,
            source=sources[task["instance_id"]],
            max_steps=args.max_steps,
            timeout=args.timeout,
            test_image=official_image_name(task["instance_id"], args.namespace),
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
    provider_args = _build_provider_args(
        provider=config.name,
        model=args.model,
        config=args.config,
        base_url=args.base_url,
        api_key=args.api_key,
        timeout=args.timeout,
    )
    manifest = build_manifest(
        runtime_tasks,
        ["minimal_policy"],
        1,
        args.seed,
        args.max_steps,
        args.timeout,
        config.name,
        config.model,
    )
    manifest.update(
        {
            "suite_id": "swebench-live-light-v1",
            "dataset_path": str(Path(args.evaluator_dataset).resolve()),
            "official_run_id": args.run_id,
        }
    )
    by_id = {task["task_id"]: task for task in runtime_tasks}
    rows = []
    for entry in manifest["plan"]:
        rows.append(
            run_runtime_task(
                by_id[entry["task_id"]],
                entry,
                output_dir=args.output_dir,
                provider_args=provider_args,
                max_steps=args.max_steps,
            )
        )
        write_result_artifacts(args.output_dir, manifest, rows)

    model_name = f"ponycode-{config.model}"
    predictions_path = write_official_predictions(
        Path(args.output_dir) / "predictions.json",
        rows,
        model_name=model_name,
    )
    command = build_official_evaluator_command(
        evaluator_python=args.evaluator_python,
        dataset_path=args.evaluator_dataset,
        predictions_path=predictions_path,
        instance_ids=[task["instance_id"] for task in selected],
        run_id=args.run_id,
        namespace=args.namespace,
        timeout=args.evaluation_timeout,
    )
    completed = run_official_evaluator(
        command,
        evaluator_root=args.evaluator_root,
        timeout=args.evaluation_timeout * max(1, len(selected)) + 300,
    )
    (Path(args.output_dir) / "official-evaluator.txt").write_text(
        f"exit_code={completed.returncode}\n\nSTDOUT\n{completed.stdout}\n\nSTDERR\n{completed.stderr}",
        encoding="utf-8",
    )
    final_rows = []
    for row in rows:
        report = official_report_path(
            args.evaluator_root,
            run_id=args.run_id,
            model_name=model_name,
            instance_id=row["instance_id"],
        )
        result = load_official_result(
            report,
            row["instance_id"],
            patch_nonempty=bool(row.get("patch_nonempty")),
        )
        if completed.returncode != 0 and not result.get("evaluation_error"):
            result["evaluation_error"] = f"official evaluator exited {completed.returncode}"
        final_rows.append(enrich_with_official_result(row, result))
    summary = write_result_artifacts(args.output_dir, manifest, final_rows)
    print(json.dumps({"runs": len(final_rows), "resolved": summary["resolved"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Run a pinned mini-SWE-agent baseline on the frozen public task subset."""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import subprocess
import time
import tomllib
from pathlib import Path


MODEL_VISIBLE_FIELDS = {
    "instance_id",
    "repo",
    "base_commit",
    "problem_statement",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-config", required=True)
    parser.add_argument("--tasks", default="benchmarks/swebench_live/tasks.json")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--namespace", default="starryzhang")
    parser.add_argument("--task-ids", default="")
    return parser


def load_public_tasks(path: str | Path, task_ids: str = "") -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("public task file must contain tasks")
    selected_ids = {value.strip() for value in task_ids.split(",") if value.strip()}
    selected = []
    for task in tasks:
        extra = set(task) - MODEL_VISIBLE_FIELDS
        if extra:
            raise ValueError(f"model-visible task contains unsupported fields: {sorted(extra)}")
        if not MODEL_VISIBLE_FIELDS.issubset(task):
            raise ValueError("model-visible task is missing required fields")
        if not selected_ids or task["instance_id"] in selected_ids:
            selected.append({key: str(task[key]) for key in MODEL_VISIBLE_FIELDS})
    found = {task["instance_id"] for task in selected}
    if missing := sorted(selected_ids - found):
        raise ValueError(f"unknown task ids: {', '.join(missing)}")
    return selected


def load_provider(path: str | Path) -> dict:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    profile_name = data.get("provider", "openai")
    profile = data.get("providers", {}).get(profile_name, {})
    required = ("api_key", "base_url")
    if any(not str(profile.get(key, "")).strip() for key in required):
        raise ValueError(f"provider profile {profile_name!r} is incomplete")
    return {"name": profile_name, **profile}


def official_image_name(instance_id: str, namespace: str) -> str:
    image_id = instance_id.replace("__", "_1776_").lower()
    return f"{namespace}/sweb.eval.x86_64.{image_id}:latest"


def build_streaming_model_class():
    import litellm
    from minisweagent.models.litellm_model import LitellmModel
    from minisweagent.models.utils.actions_toolcall import BASH_TOOL

    class StreamingLitellmModel(LitellmModel):
        """Aggregate a required SSE stream back into mini-SWE-agent's response contract."""

        def _query(self, messages: list[dict[str, str]], **kwargs):
            request_kwargs = self.config.model_kwargs | kwargs
            request_kwargs.pop("stream", None)
            request_kwargs.pop("stream_options", None)
            chunks = list(
                litellm.completion(
                    model=self.config.model_name,
                    messages=messages,
                    tools=[BASH_TOOL],
                    stream=True,
                    stream_options={"include_usage": True},
                    **request_kwargs,
                )
            )
            response = litellm.stream_chunk_builder(chunks)
            if response is None:
                raise RuntimeError("stream did not produce a complete model response")
            return response

    return StreamingLitellmModel


def trajectory_metrics(data: dict) -> dict:
    prompt_tokens = 0
    completion_tokens = 0
    cached_tokens = 0
    tool_steps = 0
    for message in data.get("messages", []):
        extra = message.get("extra", {}) or {}
        tool_steps += len(extra.get("actions", []) or [])
        response = extra.get("response", {}) or {}
        usage = response.get("usage", {}) or {}
        prompt_tokens += int(usage.get("prompt_tokens") or 0)
        completion_tokens += int(usage.get("completion_tokens") or 0)
        prompt_details = usage.get("prompt_tokens_details", {}) or {}
        cached_tokens += int(prompt_details.get("cached_tokens") or 0)
    return {
        "attempts": int(data.get("info", {}).get("model_stats", {}).get("api_calls") or 0),
        "tool_steps": tool_steps,
        "input_tokens": prompt_tokens,
        "output_tokens": completion_tokens,
        "cached_tokens": cached_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


def patch_metrics(patch: str) -> dict:
    lines = patch.splitlines()
    return {
        "patch_nonempty": bool(patch.strip()),
        "patch_bytes": len(patch.encode("utf-8")),
        "changed_files": sum(line.startswith("--- a/") for line in lines),
        "added_lines": sum(line.startswith("+") and not line.startswith("+++") for line in lines),
        "deleted_lines": sum(line.startswith("-") and not line.startswith("---") for line in lines),
    }


def write_artifacts(output_dir: Path, manifest: dict, rows: list[dict], predictions: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "preds.json").write_text(
        json.dumps(predictions, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    fields = sorted({key for row in rows for key in row})
    with (output_dir / "runs.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    def mean(field: str):
        values = [float(row[field]) for row in rows if row.get(field) is not None]
        return round(statistics.mean(values), 2) if values else None

    summary = {
        "runs": len(rows),
        "runtime_completed": sum(row.get("runtime_completed", False) for row in rows),
        "submitted": sum(row.get("patch_nonempty", False) for row in rows),
        "mean_attempts": mean("attempts"),
        "mean_tool_steps": mean("tool_steps"),
        "mean_total_tokens": mean("total_tokens"),
        "mean_duration_ms": mean("duration_ms"),
    }
    manifest = {**manifest, "runtime_summary": summary}
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def run(args) -> int:
    from minisweagent.agents.default import DefaultAgent
    from minisweagent.config import get_config_from_spec
    from minisweagent.environments.docker import DockerEnvironment

    tasks = load_public_tasks(args.tasks, args.task_ids)
    provider = load_provider(args.provider_config)
    os.environ["OPENAI_API_KEY"] = str(provider["api_key"])
    os.environ["MSWEA_COST_TRACKING"] = "ignore_errors"
    base = get_config_from_spec("swebench.yaml")
    model_class = build_streaming_model_class()
    output_dir = Path(args.output_dir).resolve()
    predictions = {}
    rows = []

    for task in tasks:
        instance_id = task["instance_id"]
        trajectory_path = output_dir / "trajectories" / instance_id / "trajectory.json"
        image = official_image_name(instance_id, args.namespace)
        started = time.monotonic()
        row = {
            "instance_id": instance_id,
            "repo": task["repo"],
            "runtime_completed": False,
            "exit_status": "InfrastructureError",
        }
        patch = ""
        agent = None
        environment = None
        try:
            environment_config = dict(base["environment"])
            environment_config.pop("environment_class", None)
            environment = DockerEnvironment(
                **environment_config,
                image=image,
                run_args=["--rm", "--network", "none"],
            )
            model = model_class(
                model_name=f"openai/{args.model}",
                model_kwargs={
                    "api_base": provider["base_url"],
                    "temperature": 0,
                    "timeout": args.timeout,
                },
                cost_tracking="ignore_errors",
                observation_template=base["model"]["observation_template"],
                format_error_template=base["model"]["format_error_template"],
            )
            agent_config = dict(base["agent"])
            agent_config.update(
                {
                    "step_limit": args.max_steps,
                    "cost_limit": 0,
                    "wall_time_limit_seconds": args.timeout,
                    "output_path": trajectory_path,
                }
            )
            agent = DefaultAgent(model, environment, **agent_config)
            result = agent.run(task["problem_statement"])
            patch = str(result.get("submission") or "")
            row.update(
                {
                    "runtime_completed": True,
                    "exit_status": str(result.get("exit_status") or ""),
                }
            )
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            if agent is not None:
                trajectory = agent.save(
                    trajectory_path,
                    {"info": {"instance_id": instance_id}},
                )
                row.update(trajectory_metrics(trajectory))
            if environment is not None:
                container_id = environment.container_id
                if container_id:
                    subprocess.run(
                        ["docker", "rm", "-f", container_id],
                        capture_output=True,
                        text=True,
                        timeout=60,
                        check=False,
                    )
                    environment.container_id = None
        row.update(patch_metrics(patch))
        row["duration_ms"] = round((time.monotonic() - started) * 1000, 2)
        row["trajectory_path"] = str(trajectory_path)
        rows.append(row)
        predictions[instance_id] = {
            "model_name_or_path": f"mini-swe-agent-{args.model}",
            "instance_id": instance_id,
            "model_patch": patch,
        }
        write_artifacts(
            output_dir,
            {
                "baseline": "mini-SWE-agent",
                "model": args.model,
                "max_steps": args.max_steps,
                "timeout": args.timeout,
                "task_ids": [item["instance_id"] for item in tasks],
            },
            rows,
            predictions,
        )
        print(json.dumps({"instance_id": instance_id, **row}, sort_keys=True))
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_steps < 1 or args.timeout < 1:
        raise ValueError("max-steps and timeout must be positive")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())

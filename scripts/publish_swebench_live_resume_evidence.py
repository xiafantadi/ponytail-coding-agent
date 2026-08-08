"""Publish sanitized, recomputable cross-process resume evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_swebench_live_resume_experiment import (  # noqa: E402
    _parse_csv_value,
    write_resume_artifacts,
)

PRIVATE_ROW_FIELDS = {
    "patch_path",
    "phase1_trace_path",
    "trace_path",
    "report_path",
    "process_events_path",
    "session_id",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", required=True)
    parser.add_argument("--output-dir", default="evidence/swebench-live/resume")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    summary = publish_resume_evidence(args.raw_dir, args.output_dir)
    print(json.dumps({"runs": summary["runs"], "resolved": summary["resolved"]}, sort_keys=True))
    return 0


def publish_resume_evidence(raw_dir: str | Path, output_dir: str | Path) -> dict:
    raw_dir = Path(raw_dir).resolve()
    output_dir = Path(output_dir).resolve()
    _validate_output_dir(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_rows = _load_rows(raw_dir / "runs.csv")
    manifest = json.loads((raw_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest.pop("summary", None)
    manifest.update(_implementation_manifest())
    public_rows = []
    for raw in raw_rows:
        public = {key: value for key, value in raw.items() if key not in PRIVATE_ROW_FIELDS}
        public["system"] = "PonyCode"
        public_rows.append(public)
        _write_case(output_dir / "cases" / raw["instance_id"], raw)
    summary = write_resume_artifacts(output_dir, manifest, public_rows)
    probe_source = raw_dir / "stale-memory-probe" / "result.json"
    if probe_source.is_file():
        probe_dir = output_dir / "stale-memory-probe"
        probe_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(probe_source, probe_dir / "result.json")
    (output_dir / "report.md").write_text(
        _render_report(public_rows, summary), encoding="utf-8"
    )
    return summary


def _write_case(case_dir: Path, raw: dict) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    patch_source = Path(str(raw.get("patch_path", "")))
    patch = patch_source.read_text(encoding="utf-8") if patch_source.is_file() else ""
    (case_dir / "patch.diff").write_text(patch, encoding="utf-8")
    public = {key: value for key, value in raw.items() if key not in PRIVATE_ROW_FIELDS}
    (case_dir / "result.json").write_text(
        json.dumps(public, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (case_dir / "test-summary.txt").write_text(
        "\n".join(
            [
                f"instance_id={raw['instance_id']}",
                f"resolved={raw.get('resolved', False)}",
                f"patch_applied={raw.get('patch_successfully_applied', False)}",
                f"fail2pass_passed={raw.get('fail2pass_passed', False)}",
                f"pass2pass_passed={raw.get('pass2pass_passed', False)}",
                f"failure_category={raw.get('failure_category', '')}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    phase1_trace = Path(str(raw.get("phase1_trace_path", "")))
    phase2_trace = Path(str(raw.get("trace_path", "")))
    trace_summary = {
        "phase1": _trace_summary(phase1_trace),
        "resumed": _trace_summary(phase2_trace),
        "resume_status": raw.get("resume_status", ""),
        "same_session": bool(raw.get("same_session")),
        "distinct_processes": bool(raw.get("distinct_processes")),
    }
    (case_dir / "trace-summary.json").write_text(
        json.dumps(trace_summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    process_source = Path(str(raw.get("process_events_path", "")))
    process_events = []
    if process_source.is_file():
        for event in _read_jsonl(process_source):
            event.pop("trace_path", None)
            process_events.append(event)
    (case_dir / "process-events.jsonl").write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in process_events),
        encoding="utf-8",
    )


def _trace_summary(path: Path) -> dict:
    if not path.is_file():
        return {}
    events = _read_jsonl(path)
    event_counts = Counter(str(event.get("event", "")) for event in events)
    tool_counts = Counter(
        str(event.get("name", ""))
        for event in events
        if event.get("event") == "tool_executed"
    )
    checkpoints = [
        str(event.get("checkpoint_id", ""))
        for event in events
        if event.get("event") == "checkpoint_created"
    ]
    return {
        "event_counts": dict(sorted(event_counts.items())),
        "tool_counts": dict(sorted(tool_counts.items())),
        "checkpoint_count": len(checkpoints),
        "model_request_count": int(event_counts.get("model_requested", 0)),
        "model_parsed_count": int(event_counts.get("model_parsed", 0)),
        "tool_step_count": int(event_counts.get("tool_executed", 0)),
    }


def _render_report(rows: list[dict], summary: dict) -> str:
    continuous_tokens = sum(int(row.get("continuous_total_tokens") or 0) for row in rows)
    resume_tokens = sum(int(row.get("total_tokens") or 0) for row in rows)
    continuous_tools = sum(int(row.get("continuous_tool_steps") or 0) for row in rows)
    resume_tools = sum(int(row.get("tool_steps") or 0) for row in rows)
    lines = [
        "# Cross-process Checkpoint / Resume experiment",
        "",
        "## Protocol",
        "",
        "- Cases: two tasks selected by SHA-256 ordering of the four frozen instance IDs; agent outcomes were not used.",
        "- Interruption: the controller terminated process 1 after the fifth successful tool event and its checkpoint were persisted.",
        "- Resume: process 2 loaded the same Session and workspace, then continued with the same model and Runtime configuration.",
        "- Budget: each turn retained the 30-step Runtime ceiling; cumulative cost is reported separately from the continuous one-turn runs.",
        "- Verification: the official hidden Fail2Pass / Pass2Pass evaluator ran only after the resumed process ended.",
        "",
        "## Results",
        "",
        "| Instance | Processes | Resume status | Official result | Exact repeated reads |",
        "| --- | ---: | --- | --- | ---: |",
    ]
    for row in rows:
        outcome = "Resolved" if row.get("resolved") else str(row.get("failure_category") or "Unresolved")
        lines.append(
            f"| `{row['instance_id']}` | 2 | `{row.get('resume_status', '')}` | {outcome} | "
            f"{int(row.get('repeated_reads_after_resume') or 0)} |"
        )
    lines.extend(
        [
            "",
            f"- Cross-process resume triggered and completed: {summary['resume_completed']}/{summary['runs']}.",
            f"- Full-valid checkpoint decisions: {summary['full_valid_resumes']}/{summary['runs']}.",
            f"- Officially resolved after resume: {summary['resume_resolved']}/{summary['runs']}.",
            f"- Per-turn budget respected: {summary['per_turn_budget_passed']}/{summary['runs']}.",
            f"- False stale accepts: {summary['false_stale_accept_count']}.",
            "",
            "## Cost and limitations",
            "",
            f"The selected continuous runs used {continuous_tokens:,} tokens and {continuous_tools} tool steps. "
            f"The two-process runs used {resume_tokens:,} tokens and {resume_tools} tool steps, "
            f"a delta of {resume_tokens - continuous_tokens:+,} tokens and {resume_tools - continuous_tools:+} tool steps.",
            "",
            "The experiment supports a checkpoint continuity and recovery-correctness claim, not an efficiency claim. "
            "The resolved case still issued repeated exact read requests after resume; this limitation is retained in `runs.csv`.",
            "",
            "The separate deterministic stale-memory probe changed a summarized file between sessions. "
            "It produced `partial-stale`, invalidated one summary, excluded its unique stale marker from the resumed prompt, and recorded zero false stale accepts.",
            "",
            "This is a two-task mechanism experiment on a frozen lightweight subset, not a full SWE-bench-Live leaderboard result.",
        ]
    )
    return "\n".join(lines) + "\n"


def _implementation_manifest() -> dict:
    files = [
        ROOT / "ponytail" / "core" / "engine_helpers.py",
        ROOT / "ponytail" / "core" / "runtime.py",
        ROOT / "ponytail" / "evaluation" / "swebench_live.py",
        ROOT / "scripts" / "run_swebench_live_resume_experiment.py",
    ]
    return {
        "implementation_files": {
            path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in files
        },
        "dataset_snapshot": "a637bd46829f3132e12938c8a0ca93173a977b8e",
    }


def _load_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [
            {key: _parse_csv_value(value) for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _validate_output_dir(path: Path) -> None:
    allowed_root = (ROOT / "evidence" / "swebench-live").resolve()
    if path.parent != allowed_root or path.name != "resume":
        raise ValueError("public resume evidence must be written to evidence/swebench-live/resume")


if __name__ == "__main__":
    raise SystemExit(main())

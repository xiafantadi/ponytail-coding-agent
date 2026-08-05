"""Build a sanitized public evidence package from local experiment artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

TRACE_EVENTS = {
    "model_parsed",
    "tool_executed",
    "final_readiness_decision",
    "minimality_audit_completed",
    "run_finished",
}
SENSITIVE_KEYS = {"api_key", "base_url", "provider_base_url", "provider_endpoint"}


def package_evidence(source_dir, output_dir, samples=(), repo_root=None):
    source_dir = Path(source_dir)
    output_dir = Path(output_dir)
    repo_root = Path(repo_root or Path.cwd()).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = _read_json(source_dir / "manifest.json")
    rows = _read_csv(source_dir / "runs.csv")
    sensitive_values = _collect_sensitive_values(manifest)
    for row in rows:
        sensitive_values.update(_collect_sensitive_values(_parse_usage(row)))

    _write_json(output_dir / "manifest.json", _sanitize(manifest, repo_root))
    _write_runs(output_dir / "runs.csv", rows, repo_root)
    _write_json(
        output_dir / "summary.json",
        _sanitize(_read_json(source_dir / "summary.json"), repo_root),
    )
    report = (source_dir / "report.md").read_text(encoding="utf-8")
    (output_dir / "report.md").write_text(
        _sanitize_text(report, repo_root, sensitive_values), encoding="utf-8"
    )

    rows_by_key = {str(row.get("run_key")): row for row in manifest.get("rows", [])}
    for label, run_key in samples:
        if run_key not in rows_by_key:
            raise ValueError(f"unknown sample run: {run_key}")
        _write_sample(
            output_dir / "sample-runs" / label,
            rows_by_key[run_key],
            repo_root,
            sensitive_values,
        )

    _assert_sanitized(output_dir, repo_root, sensitive_values)


def _write_sample(output_dir, row, repo_root, sensitive_values):
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "result.json", _sanitize(row, repo_root))
    patch = _resolve_ref(row["patch_path"], repo_root).read_text(
        encoding="utf-8", errors="replace"
    )
    (output_dir / "patch.diff").write_text(
        _sanitize_text(patch, repo_root, sensitive_values), encoding="utf-8"
    )
    trace_events = []
    for line in _resolve_ref(row["trace_path"], repo_root).read_text(
        encoding="utf-8"
    ).splitlines():
        event = json.loads(line)
        if event.get("event") in TRACE_EVENTS:
            trace_events.append(_sanitize(event, repo_root))
    with (output_dir / "trace-excerpt.jsonl").open("w", encoding="utf-8") as handle:
        for event in trace_events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    report = _read_json(_resolve_ref(row["report_path"], repo_root))
    _write_json(output_dir / "report.json", _sanitize(report, repo_root))


def _write_runs(path, rows, repo_root):
    if not rows:
        raise ValueError("runs.csv must not be empty")
    fieldnames = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            cleaned = _sanitize(dict(row), repo_root)
            usage = _parse_usage(row)
            if usage:
                cleaned["usage"] = json.dumps(
                    _sanitize(usage, repo_root), ensure_ascii=False, sort_keys=True
                )
            writer.writerow(cleaned)


def _sanitize(value, repo_root):
    if isinstance(value, dict):
        return {
            key: (
                "<redacted>"
                if str(key).lower() in SENSITIVE_KEYS
                else _sanitize(item, repo_root)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(item, repo_root) for item in value]
    if isinstance(value, str):
        return _sanitize_text(value, repo_root, set())
    return value


def _sanitize_text(text, repo_root, sensitive_values):
    text = str(text)
    for value in sensitive_values:
        if value:
            text = text.replace(value, "<redacted>")
    for root in {str(repo_root), repo_root.as_posix()}:
        text = text.replace(root, "<repo>")
    text = re.sub(r"(?i)[a-z]:[\\/]+users[\\/]+[^\\/\s]+", "<user>", text)
    return re.sub(r"\bsk-[A-Za-z0-9_-]{16,}\b", "<redacted>", text)


def _collect_sensitive_values(value):
    values = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS and isinstance(item, str):
                values.add(item)
            values.update(_collect_sensitive_values(item))
    elif isinstance(value, list):
        for item in value:
            values.update(_collect_sensitive_values(item))
    return values


def _assert_sanitized(output_dir, repo_root, sensitive_values):
    forbidden = {str(repo_root), repo_root.as_posix(), *sensitive_values}
    for path in output_dir.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(value and value in text for value in forbidden):
            raise ValueError(f"sensitive value remains in {path}")
        if re.search(r"\bsk-[A-Za-z0-9_-]{16,}\b", text):
            raise ValueError(f"API key pattern remains in {path}")


def _parse_usage(row):
    usage = row.get("usage", {})
    if isinstance(usage, str):
        try:
            usage = json.loads(usage)
        except json.JSONDecodeError:
            return {}
    return usage if isinstance(usage, dict) else {}


def _resolve_ref(value, repo_root):
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_json(path, value):
    Path(path).write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sample(value):
    label, separator, run_key = str(value).partition("=")
    if not separator or not re.fullmatch(r"[a-z0-9-]+", label) or not run_key:
        raise argparse.ArgumentTypeError("sample must be LABEL=RUN_KEY")
    return label, run_key


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--sample", action="append", default=[], type=_sample)
    args = parser.parse_args(argv)
    package_evidence(args.source_dir, args.output_dir, args.sample)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

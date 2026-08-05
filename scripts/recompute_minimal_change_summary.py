"""Recompute a minimal-change summary from its immutable runs CSV."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ponytail.evaluation.minimal_change import (
    recompute_minimal_change_summary,
    render_minimal_change_report,
)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("runs_csv", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    summary = recompute_minimal_change_summary(args.runs_csv)
    payload = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    if args.report:
        metadata = {}
        if args.manifest:
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            metadata = {
                "provider_profile": manifest.get("provider_profile"),
                "model": manifest.get("model"),
            }
        args.report.write_text(
            render_minimal_change_report(summary, metadata), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

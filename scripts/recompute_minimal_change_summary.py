"""Recompute a minimal-change summary from its immutable runs CSV."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pico.evaluation.minimal_change import recompute_minimal_change_summary


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("runs_csv", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    summary = recompute_minimal_change_summary(args.runs_csv)
    payload = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

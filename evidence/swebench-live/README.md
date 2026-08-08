# SWE-bench-Live lightweight evidence

This directory contains a fixed, recomputable four-task evaluation of PonyCode on the
SWE-bench-Live `lite` split. It is a job-search-sized local experiment, not a claim about
the full SWE-bench-Live leaderboard.

## Evidence layers

- `preflight/`: official gold-patch environment validation. All four frozen tasks resolved.
- `standard/`: one Pass@1 run per task for PonyCode and pinned mini-SWE-agent 2.4.6,
  followed by the same official Fail2Pass and Pass2Pass evaluation.
- `resume/`: two fixed tasks interrupted after a durable checkpoint, terminated, and
  resumed by a second process before the same official evaluation.

## Standard result

| System | Resolved | Fail2Pass | Pass2Pass | Model calls | Tool steps | Total tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| PonyCode | 3/4 | 3/4 | 3/4 | 84 | 106 | 691,426 |
| mini-SWE-agent | 3/4 | 3/4 | 4/4 | 32 | 51 | 299,283 |

Both systems used the same intermediary `gpt-5.4` model, frozen tasks, official Docker
images, 30-call ceiling, and post-run hidden evaluation. All failed tasks remain in the
denominator. The small subset supports a reproducible 75% result for PonyCode, but does
not show a raw repair-rate or efficiency advantage over mini-SWE-agent.

See `standard/report.md` for methodology, limitations, and per-task interpretation.

## Checkpoint / Resume result

- Cross-process resume triggered and completed: `2/2`.
- Distinct process IDs and same persisted Session: `2/2`.
- Full-valid checkpoint decisions: `2/2`.
- Officially resolved after resume: `1/2`, matching the selected continuous runs.
- Per-turn 30-step budget respected: `2/2`.
- Stale-memory probe: `partial-stale`, one summary invalidated, false stale accepts `0`.

The two-process arm used more calls, tools, and tokens than continuous execution and does
not support an efficiency claim. Exact repeated reads after resume are retained as a known
limitation. See `resume/report.md` and `resume/runs.csv`.

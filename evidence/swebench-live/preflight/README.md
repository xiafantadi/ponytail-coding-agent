# SWE-bench-Live lightweight preflight

This directory records the environment preflight for PonyCode's frozen four-task SWE-bench-Live subset. It is not a full SWE-bench-Live leaderboard result and does not measure PonyCode's repair rate.

## Result

- Dataset: `SWE-bench-Live/SWE-bench-Live`, `lite` split, snapshot `a637bd46829f3132e12938c8a0ca93173a977b8e`.
- Frozen tasks: 4 tasks from 4 repositories.
- Official gold-patch preflight: 4/4 resolved.
- Evaluator concurrency: one Docker worker.
- Model or Provider calls: none.

The first `amoffat__sh-744` attempt exposed a Windows-host compatibility issue: the evaluator wrote Linux shell scripts and patches with CRLF endings. That attempt is recorded as an environment incident, not a task result. The external evaluator copy was changed to emit LF, after which the same gold patch resolved.

The PonyCode evaluator bridge was also smoke-tested on `cyclotruc__gitingest-94` using an evaluator-side gold prediction. The bridge submitted one local snapshot instance and received `1/1 resolved`. This validates prediction transport and report parsing only; it is not included in PonyCode's repair rate.

## Leakage boundary

The public manifest contains only task identifiers, repositories, base commits, selection metadata, and preflight status. Gold patches, hidden test patches, Fail2Pass lists, and Pass2Pass lists remain evaluator-only and must not enter the Agent prompt, memory, workspace, trace, or report.

See `benchmarks/swebench_live/manifest.json` for the frozen task set and `runs.csv` for per-task preflight results.

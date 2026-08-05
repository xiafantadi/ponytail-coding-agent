# Minimal-Change Policy Evidence

This package records a fixed real-model comparison for a local Code Agent
Runtime. It evaluates whether a minimal-change policy can reduce unnecessary
tool work and token use without weakening external verification.

## Experiment Contract

- Source revision: `45bce581d9a8e0807a193d48a3ea2e1cd0aa2cd0`
- Provider protocol: OpenAI-compatible Responses API
- Model: `gpt-5.5`
- Matrix: 6 repository fixtures x 3 arms x 3 repetitions = 54 runs
- Task mix: 2 overbuild traps, 2 bug fixes, and 2 security-boundary tasks
- Quality gates: non-empty patch, Fail2Pass, Pass2Pass, holdout verifier,
  allowed change scope, and fixed tool/timeout budgets
- Failed runs remain in all denominators. No task, repetition, or threshold was
  changed after execution started.

The three arms are:

- `baseline`: normal Runtime contract without minimal-policy prompt rules.
- `short_yagni`: one short instruction to prefer the smallest sufficient fix.
- `minimal_policy`: the versioned policy that prioritizes existing repository
  capabilities, standard-library/native solutions, scope control, and external
  verification.

## Results

| Arm | Verified runs | Mean attempts | Mean tool steps | Mean total tokens | Change vs baseline |
|---|---:|---:|---:|---:|---|
| `baseline` | 18/18 | 6.33 | 6.06 | 4318.94 | reference |
| `short_yagni` | 18/18 | 5.72 | 5.50 | 4255.28 | attempts -9.65%, tools -9.17%, tokens -1.47% |
| `minimal_policy` | 18/18 | 5.78 | 5.39 | 4219.39 | attempts -8.77%, tools -11.01%, tokens -2.31% |

Across all 54 runs, task pass rate, Fail2Pass, Pass2Pass, and holdout verifier
pass rate were each 100%. Every run changed exactly one allowed file and
recorded Provider usage. The complete policy reduced average tool steps by
11.01% and average tokens per run by 2.31% relative to baseline while retaining
the same verification rate.

These are measured local-suite results, not a claim of statistical significance.
The original strong threshold of at least 15% token reduction was not reached.

## Representative Cases

- **Clear benefit:** `path-traversal-boundary` repetition 1 fell from 10 model
  attempts / 9 tool steps / 4990 tokens in baseline to 6 / 6 / 4416 under the
  complete policy, with all security and regression checks passing. See
  [benefit sample](sample-runs/benefit/result.json).
- **No material benefit:** `csv-formula-boundary` repetition 1 used 5 attempts
  and 5 tool steps in both arms; the complete policy used 4078 tokens versus
  4013 in baseline. See [no-benefit sample](sample-runs/no-benefit/result.json).
- **Negative case:** `json-object-contract` repetition 2 increased from 5
  attempts / 5 tool steps / 4061 tokens to 6 / 6 / 4237, while still passing
  all quality gates. See [negative sample](sample-runs/negative/result.json).

Each sample directory contains the result row, patch, sanitized trace excerpt,
and sanitized report.

## Reproduction

Configure an OpenAI-compatible Provider locally, then run from the repository
root:

```powershell
.\.venv\Scripts\python.exe scripts\run_minimal_change_experiment.py `
  --provider-profile openai --model gpt-5.5 `
  --tasks stdlib-url-host,json-object-contract,single-file-sum-boundary,config-timeout-migration,path-traversal-boundary,csv-formula-boundary `
  --arms baseline,short_yagni,minimal_policy --repetitions 3 `
  --seed 1401 --max-steps 12 --timeout 120 `
  --output-dir artifacts\minimal-change\resume-experiment-r15-54
```

Recompute the public aggregate without trusting the checked-in summary:

```powershell
.\.venv\Scripts\python.exe scripts\recompute_minimal_change_summary.py `
  evidence\minimal-change\runs.csv
```

The recorded run took about 29 minutes of experiment wall time and consumed
230,285 total Provider tokens. Monetary cost is not reported because the
gateway did not expose a reliable billed-cost field.

## Evidence Files

- [manifest.json](manifest.json): frozen plan, revision, and 54 result rows.
- [runs.csv](runs.csv): row-level quality, efficiency, usage, and artifact refs.
- [summary.json](summary.json): machine-recomputed aggregate.
- [report.md](report.md): human-readable aggregate report.
- [benefit trace](sample-runs/benefit/trace-excerpt.jsonl)
- [no-benefit trace](sample-runs/no-benefit/trace-excerpt.jsonl)
- [negative trace](sample-runs/negative/trace-excerpt.jsonl)

## Limitations

- This is a local 6-task fixture suite, not official SWE-bench or SWE-bench
  Verified, and it does not use official hidden tests.
- Results cover one model, one Provider route, and three repetitions per cell;
  broader model and repository diversity may change the effect size.
- The fixtures are copied into isolated non-Git workspaces, so added/deleted LOC
  and dependency-delta fields are `null`; they are not converted to zero.
- Prompt caching did not contribute to this experiment, and billed cost was not
  available.
- All arms achieved 100% verification, so this experiment measures efficiency
  differences but does not establish a quality improvement over baseline.

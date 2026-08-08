# Real Provider R03 Minimal-Change Evidence

This record captures the first controlled nine-run minimal-change experiment
after adding an explicit implementation contract and final-readiness enforcement.
The provider endpoint and API key are intentionally omitted.

## Configuration

- provider protocol: OpenAI-compatible
- provider profile: `openai`
- model: `gpt-5.4`
- planned runs: 9 (`baseline`, `short_yagni`, `minimal_policy`; 3 tasks; 1 repetition)
- raw artifacts: `artifacts/minimal-change/smoke-contract/`

## Results

| Metric | Result |
|---|---:|
| runtime runs completed | 9/9 |
| task pass rate | 0/9 |
| Fail2Pass pass rate | 0/9 |
| Pass2Pass pass rate | 9/9 |
| holdout verifier pass rate | 0/9 |
| patch not applied | 8/9 |
| patch applied but Fail2Pass failed | 1/9 |
| usage records | 9/9 |

The usage records contain provider protocol, model, input tokens, output tokens,
and total tokens. The recorded input-token range was 3,206-4,182 and the
output-token range was 49-174.

## Interpretation

The Runtime did not treat loop completion as task success. Eight runs returned
without a workspace change and were stopped by the final-readiness gate after a
corrective notice and a second false completion. One `short_yagni` run produced
an `app.py` patch, but the patch only changed line endings and did not satisfy
the target test; the external verifier classified it as `fail2pass_failed`.

This is a valid failure record, not a model success metric. It establishes that
the runtime, artifact collection, usage capture, and verifier rejection path are
working, while the selected gateway/model combination still needs compatibility
validation for reliable multi-step code editing.

## Step 10 Gate

The post-run structural gate passed all checks:

- 9 manifest plan entries and 9 CSV rows;
- 9 unique run keys and 9 unique runtime run IDs;
- patch, trace, report, and all verifier stdout/stderr artifacts present;
- usage and provider retry metadata present in all 9 rows;
- prompt-cache state consistent across all arms;
- baseline policy disabled and free of injected policy rules;
- `minimal_policy` reports contain policy version and rule hash;
- global Skills disabled for all experiment agents.

After the experiment changes, the focused gate passed `33 tests`, the final
full regression passed `574 tests` with `3 skipped`, and full Ruff passed.

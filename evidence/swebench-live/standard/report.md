# Standard four-task comparison

## Protocol

- Dataset: SWE-bench-Live `lite`, snapshot `a637bd46829f3132e12938c8a0ca93173a977b8e`.
- Frozen set: four tasks from four repositories, selected before any Agent outcome.
- Model: the same intermediary `gpt-5.4` endpoint for both systems.
- Budget: one run per task and at most 30 model calls per run.
- Environment: the same frozen official Docker image per task.
- Leakage boundary: only the Issue description and repair-before repository were visible
  to the Agent. Gold patches, hidden tests, Fail2Pass, and Pass2Pass stayed evaluator-only.
- Verification: official hidden evaluation ran only after each Agent terminated and did
  not feed failures back into that run.

PonyCode Trace audit found zero network-like shell commands. mini-SWE-agent containers
ran with Docker networking disabled.

## Results

| Metric | PonyCode | mini-SWE-agent |
| --- | ---: | ---: |
| Resolved | 3/4 | 3/4 |
| Fail2Pass passed | 3/4 | 3/4 |
| Pass2Pass passed | 3/4 | 4/4 |
| Non-empty patches | 3/4 | 4/4 |
| Model calls | 84 | 32 |
| Tool steps | 106 | 51 |
| Input tokens | 685,064 | 293,353 |
| Cached input tokens | 70,656 | 226,304 |
| Output tokens | 6,362 | 5,930 |
| Total tokens | 691,426 | 299,283 |
| Runtime duration | 343.0 s | 184.5 s |

Formulas:

- `resolution_rate = resolved / all_frozen_tasks`
- `total_tokens = sum(input_tokens + output_tokens)` across every model call
- `uncached_input_tokens = input_tokens - cached_input_tokens`
- `tool_steps = successfully dispatched tool calls recorded by each Runtime`

## Per-task outcome

| Instance | PonyCode | mini-SWE-agent |
| --- | --- | --- |
| `cyclotruc__gitingest-94` | Resolved | Resolved |
| `dynaconf__dynaconf-1241` | Resolved | Resolved |
| `amoffat__sh-744` | Resolved | Resolved |
| `run-llama__llama_deploy-384` | Empty patch | Patch applied; Fail2Pass failed |

The shared failed task remains in both denominators. PonyCode did not produce a source
change; mini-SWE-agent produced an applicable, regression-safe patch that did not fix the
target behavior.

## Interpretation

This experiment validates PonyCode's end-to-end task transport, controlled tool execution,
patch generation, Trace/Report evidence, and official post-run verification on real Issues.
It does not demonstrate superiority over mini-SWE-agent: both systems resolved 75%, while
mini-SWE-agent used fewer calls, tools, tokens, and runtime on this subset.

The next experiment evaluates PonyCode-specific Checkpoint / Resume and stale-memory
invalidation behavior, which the standard repair-rate comparison does not measure.

## Reproduction files

- `manifest.json`: frozen versions, task IDs, limits, and implementation hashes.
- `runs.csv`: one normalized row per system and task.
- `summary.json`: aggregate metrics recomputed from `runs.csv`.
- `cases/<instance-id>/result.json`: paired per-task result.
- `cases/<instance-id>/*.patch`: submitted candidate patches.
- `cases/<instance-id>/ponycode-trace-summary.json`: event and governance summary without
  full prompts, model responses, or Provider configuration.


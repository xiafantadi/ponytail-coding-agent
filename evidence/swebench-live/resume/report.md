# Cross-process Checkpoint / Resume experiment

## Protocol

- Cases: two tasks selected by SHA-256 ordering of the four frozen instance IDs; agent outcomes were not used.
- Interruption: the controller terminated process 1 after the fifth successful tool event and its checkpoint were persisted.
- Resume: process 2 loaded the same Session and workspace, then continued with the same model and Runtime configuration.
- Budget: each turn retained the 30-step Runtime ceiling; cumulative cost is reported separately from the continuous one-turn runs.
- Verification: the official hidden Fail2Pass / Pass2Pass evaluator ran only after the resumed process ended.

## Results

| Instance | Processes | Resume status | Official result | Exact repeated reads |
| --- | ---: | --- | --- | ---: |
| `cyclotruc__gitingest-94` | 2 | `full-valid` | Resolved | 6 |
| `run-llama__llama_deploy-384` | 2 | `full-valid` | patch_not_applied | 0 |

- Cross-process resume triggered and completed: 2/2.
- Full-valid checkpoint decisions: 2/2.
- Officially resolved after resume: 1/2.
- Per-turn budget respected: 2/2.
- False stale accepts: 0.

## Cost and limitations

The selected continuous runs used 281,309 tokens and 47 tool steps. The two-process runs used 463,460 tokens and 66 tool steps, a delta of +182,151 tokens and +19 tool steps.

The experiment supports a checkpoint continuity and recovery-correctness claim, not an efficiency claim. The resolved case still issued repeated exact read requests after resume; this limitation is retained in `runs.csv`.

The separate deterministic stale-memory probe changed a summarized file between sessions. It produced `partial-stale`, invalidated one summary, excluded its unique stale marker from the resumed prompt, and recorded zero false stale accepts.

This is a two-task mechanism experiment on a frozen lightweight subset, not a full SWE-bench-Live leaderboard result.

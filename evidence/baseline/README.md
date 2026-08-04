# Pico v3 Baseline Evidence

Captured on 2026-08-04 from baseline commit
`dfbb9385a0d7fa3f0149d7d3e1b04aa7ca7c4fc7` (`pico-v3-baseline`).

## Environment

- OS: Microsoft Windows NT 10.0.26200.0
- Python: 3.13.9
- uv: 0.11.17

## Results

| Check | Result | Evidence |
|---|---:|---|
| Ruff | passed | `ruff-check-final.txt` |
| Evaluator tests | 8 passed | `pytest-evaluator-final.txt` |
| OpenAI-compatible client tests | 6 passed, 65 deselected | `pytest-openai-client.txt` |
| Full test suite | 479 passed, 34 failed, 2 skipped | `pytest-all-final.txt` |
| CLI/REPL scenario S07 | passed | `v3-human-scenario-gate-s07.txt` |
| Real provider connectivity and usage | passed | `provider-smoke.json` |
| Real provider tool-task verification | failed | `provider-smoke.json` |

The 34 full-suite failures are retained as baseline defects. Most are associated
with POSIX command assumptions on Windows, shell quoting, environment handling,
or Git-root behavior. They are not reported as passing.

The live provider smoke separates transport/usage success from task success.
The provider returned actual token usage, but the model returned a final answer
without applying the requested patch, so the external file verifier failed.

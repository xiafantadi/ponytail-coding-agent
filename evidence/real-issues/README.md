# Real AI Infrastructure Issue Evidence

This package records a small, real-model evaluation against historical defects
from `openai/openai-agents-python`. The model received the defect description
and the repository at a fixed pre-fix commit. It did not receive upstream patch
content. External tests, not the model's final answer, determined success.

## Results

- Tasks evaluated: 3
- Tasks solved at least once: 2/3
- Real-model runs: 2/5 passed
- Runs with Provider usage: 5/5
- Successful-run mean tool steps: 24.5
- Successful-run mean total tokens: 10214.5
- Successful-run mean changed files: 1.5
- Successful-run mean patch lines: 14.5

Successful runs passed Fail2Pass, nearby Pass2Pass tests, and the configured
write-scope check. Failed runs remain in `runs.csv`.

## Cases

- [Issue #3994](cases/issue-3994/): empty streamed input rejected before model invocation.
- [Issue #4144](cases/issue-4144/): streamed handoff duplicated as `tool_called`; retained as a failed investigation case.
- [PR #4190](cases/issue-4190/): empty session persistence created an unnecessary remote conversation.

## Limitations

- This is a five-run local evaluation, not official SWE-bench.
- The task set contains two GitHub Issues and one merged upstream PR defect.
- One model and one Provider route were used.
- `holdout_verifier_passed` records a second execution of the target external
  verifier; it is not counted as a separate hidden-test result.
- The evaluation establishes case-level repair evidence, not a general coding success rate.

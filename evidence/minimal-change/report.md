# Minimal-Change Experiment Report

- Provider profile: `openai`
- Model: `gpt-5.5`
- Runs: 54

## Outcome

| Metric | Passed | Total | Rate |
|---|---:|---:|---:|
| Task | 54 | 54 | 100.00% |
| Fail2Pass | 54 | 54 | 100.00% |
| Pass2Pass | 54 | 54 | 100.00% |
| Holdout verifier | 54 | 54 | 100.00% |

## By Arm

| Arm | Passed | Total | Pass rate | Failures |
|---|---:|---:|---:|---|
| `baseline` | 18 | 18 | 100.00% | none |
| `minimal_policy` | 18 | 18 | 100.00% | none |
| `short_yagni` | 18 | 18 | 100.00% | none |

## Usage and Efficiency

- input_tokens: sum=225779.0, mean=4181.092592592592, median=4087.0, samples=54
- output_tokens: sum=4506.0, mean=83.44444444444444, median=80.5, samples=54
- total_tokens: sum=230285.0, mean=4264.537037037037, median=4163.0, samples=54

## Change Metrics

- added_lines: sum=None, median=None, samples=0
- deleted_lines: sum=None, median=None, samples=0
- changed_files: sum=54.0, median=1.0, samples=54
- dependencies_added_count: sum=None, median=None, samples=0
- tokens_per_verified_pass: 4264.537037037037 (available)
- cost_per_verified_pass: None (cost_not_recorded)

## Paired Deltas

- `minimal_policy` versus `baseline`:
  - added_lines: mean=None, samples=0
  - attempts: mean=-0.5555555555555556, samples=18
  - changed_files: mean=0.0, samples=18
  - tool_steps: mean=-0.6666666666666666, samples=18
  - total_tokens: mean=-99.55555555555556, samples=18
- `short_yagni` versus `baseline`:
  - added_lines: mean=None, samples=0
  - attempts: mean=-0.6111111111111112, samples=18
  - changed_files: mean=0.0, samples=18
  - tool_steps: mean=-0.5555555555555556, samples=18
  - total_tokens: mean=-63.666666666666664, samples=18

## Limitations

- Failed runs remain in all denominators and failure categories.
- Cost and LOC metrics are null when the runner does not record them.
- This local task suite is not an official SWE-bench result.

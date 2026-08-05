# Context and Memory Ablation Evidence

This document records the historical paired experiments used for the context
and memory claims in the resume. The experiments predate the Ponytail package
rename; the corresponding context and memory modules remain covered by the
current regression suite.

## Context ablation

- Configurations: 12 paired long-context configurations.
- Mean raw prompt length: 6964 characters.
- Mean managed prompt length: 5418 characters.
- Mean per-configuration compression rate: 18.01%.
- Maximum compression rate: 35.63%.
- Current request retained intact: 12/12 configurations.

The 18.01% value is the arithmetic mean of the 12 per-configuration
compression rates. It is not computed directly from the two aggregate means.

## Memory ablation

- Tasks: 12 paired memory-dependent follow-up tasks.
- Correct tasks with memory disabled: 8/12 (66.7%).
- Correct tasks with memory enabled: 12/12 (100%).
- Repeated file reads: 8 to 3.
- Mean follow-up tool steps: 0.67 to 0.25.

The experiment changes the memory condition while keeping the task and
follow-up request fixed. These results apply to the frozen task set and are not
presented as an open-task success rate.

## Limitation

The repository currently publishes the metric definitions and aggregate
results, but not the original per-case raw run files for these historical
experiments. New claims should use the public real-issue and minimal-change
evidence packages, which include row-level results.

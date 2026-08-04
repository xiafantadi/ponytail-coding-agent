# Real Provider R02 Evidence

This record separates the pre-fix failure from the post-fix validation. The
provider endpoint and API key are intentionally omitted.

## Pre-Fix Failure

- scenario: `R02` order-pricing bug fix
- provider transport and usage: available
- model behavior: executed `read_file` twice, then returned a completion claim
- `changed_paths`: empty
- `patch_file`: not executed
- `run_shell`: not executed
- external pytest verifier: failed
- raw artifacts: `D:/software/code_workspace/Agent_project/live-evidence-r02-20260804/`

This run demonstrated that a model final answer could previously terminate a
code task without evidence of the requested workspace change.

## Post-Fix Validation

- scenario result: `1/1 passed`
- actual provider profile: `openai` / `gpt-5.4`
- duration: `19.232s`
- tool sequence: `read_file -> read_file -> patch_file -> run_shell`
- `changed_paths`: `src/order_pricing.py`
- `attempts`: `6`
- `tool_steps`: `4`
- external pytest verifier: passed
- `verification_status`: `passed`
- `verified_success`: `true`
- provider usage: `input_tokens=3247`, `output_tokens=11`
- raw artifacts: `D:/software/code_workspace/Agent_project/live-evidence-r02-retry-20260804/`

The runtime now gives one corrective notice when a request explicitly requires
a workspace change but no changed path is recorded. A second false completion
is blocked and persisted as an unverified stopped run. Read-only tasks and
memory Dream runs are excluded from this code-change contract.

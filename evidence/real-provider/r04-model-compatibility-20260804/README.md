# Real Provider R04 Model Compatibility Evidence

This record captures a one-run model compatibility check. The provider endpoint
and API key are intentionally omitted.

## Result

- provider profile: `openai`
- requested model: `gpt-5.3-codex-spark`
- runner status: completed
- HTTP result: `400`
- provider error: the model is not supported for Codex with a ChatGPT account
- model attempts: `0` completed model calls
- tool steps: `0`
- changed paths: none
- task result: not evaluated
- raw artifacts: `artifacts/minimal-change/model-smoke/gpt-5.3-codex-spark/`

An additional one-run check with `claude-sonnet-4-6` was also rejected with
HTTP `400`: the model does not belong to the current interface provider. It
also produced zero model calls, zero tool steps, and no workspace change. The
raw artifacts are under
`artifacts/minimal-change/model-smoke/claude-sonnet-4-6/`.

A one-run check with `gpt-5.5` was accepted by the interface and returned real
usage metadata, but produced two parser retries followed by a `Done` final
without any tool call or workspace change. It was classified as
`patch_not_applied`; artifacts are under
`artifacts/minimal-change/model-smoke/gpt-5.5/`. This confirms transport
acceptance but not compatibility with the current text tool protocol.

## Interpretation

These are provider-interface model compatibility failures, not code-task or
Runtime-quality results. The Provider configuration was resolved and each error
was captured in usage/error metadata, but both requests were rejected before
the model could produce a tool call. The `/models` response should therefore
not be treated as sufficient evidence that every listed model is accepted by
the current chat route. The accepted `gpt-5.5` request adds a second boundary:
an accepted request can still be unusable for this text-protocol Runtime if the
model does not emit executable tool blocks.

"""Provider-facing result types."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelResult:
    text: str
    metadata: dict = field(default_factory=dict)


def complete_model(model_client, prompt, max_new_tokens, **kwargs):
    tools = kwargs.pop("tools", None)
    if tools and getattr(model_client, "supports_native_tools", False):
        from ..tools.native import build_native_tool_specs

        kwargs["native_tools"] = build_native_tool_specs(tools)
    if hasattr(model_client, "complete_result"):
        return model_client.complete_result(prompt, max_new_tokens, **kwargs)
    text = model_client.complete(prompt, max_new_tokens, **kwargs)
    metadata = dict(getattr(model_client, "last_completion_metadata", {}) or {})
    return ModelResult(text=str(text), metadata=metadata)

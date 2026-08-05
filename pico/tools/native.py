"""Provider-neutral native tool declarations."""

from .registry import _TOOL_SCHEMAS


def build_native_tool_specs(tools):
    specs = []
    for name, tool in tools.items():
        schema_cls = _TOOL_SCHEMAS.get(name)
        if schema_cls is None:
            continue
        parameters = schema_cls.model_json_schema()
        parameters.pop("title", None)
        specs.append(
            {
                "type": "function",
                "name": name,
                "description": tool.description,
                "parameters": parameters,
            }
        )
    return specs

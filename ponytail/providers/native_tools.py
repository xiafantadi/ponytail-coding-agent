"""Normalize native Provider tool calls into Pico's internal text protocol."""

import json


def native_tool_text(data):
    calls = _response_tool_calls(data)
    blocks = []
    for call in calls:
        arguments = call.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                pass
        payload = {"name": call.get("name", ""), "args": arguments}
        blocks.append(f"<tool>{json.dumps(payload, ensure_ascii=False)}</tool>")
    return "\n".join(blocks), len(calls)


def _response_tool_calls(data):
    calls = []
    for item in data.get("output", []) if isinstance(data, dict) else []:
        if isinstance(item, dict) and item.get("type") == "function_call":
            calls.append(item)
    choices = data.get("choices", []) if isinstance(data, dict) else []
    if choices:
        message = choices[0].get("message", {})
        for item in message.get("tool_calls", []) or []:
            function = item.get("function", {}) if isinstance(item, dict) else {}
            if function:
                calls.append(function)
    return calls

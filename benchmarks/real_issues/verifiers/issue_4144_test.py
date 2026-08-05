import sys
from pathlib import Path

import pytest


UPSTREAM_ROOT = Path.cwd().resolve()
sys.path.insert(0, str(UPSTREAM_ROOT))
sys.path.insert(0, str(UPSTREAM_ROOT / "src"))
sys.path.insert(0, str(UPSTREAM_ROOT / "tests"))

from agents import Agent, Runner  # noqa: E402
from agents.items import HandoffCallItem, ToolCallItem  # noqa: E402
from fake_model import FakeModel  # noqa: E402
from test_responses import get_handoff_tool_call, get_text_message  # noqa: E402


@pytest.mark.asyncio
async def test_handoff_is_not_duplicated_as_tool_called() -> None:
    target = Agent(name="TargetAgent", model=FakeModel())
    model = FakeModel()
    model.add_multiple_turn_outputs(
        [[get_handoff_tool_call(target)], [get_text_message("done")]]
    )
    source = Agent(name="SourceAgent", handoffs=[target], model=model)

    result = Runner.run_streamed(source, input="start")
    item_events = [
        (event.name, event.item)
        async for event in result.stream_events()
        if event.type == "run_item_stream_event"
    ]

    handoff_events = [
        (name, item) for name, item in item_events if isinstance(item, HandoffCallItem)
    ]
    assert len(handoff_events) == 1
    assert handoff_events[0][0] == "handoff_requested"
    assert [name for name, _ in item_events if name == "tool_called"] == []
    assert not any(isinstance(item, ToolCallItem) for _, item in item_events)

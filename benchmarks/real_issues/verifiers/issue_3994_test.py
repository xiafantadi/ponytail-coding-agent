import sys
from pathlib import Path

import pytest


UPSTREAM_ROOT = Path.cwd().resolve()
sys.path.insert(0, str(UPSTREAM_ROOT))
sys.path.insert(0, str(UPSTREAM_ROOT / "src"))
sys.path.insert(0, str(UPSTREAM_ROOT / "tests"))

from agents import Agent, Runner  # noqa: E402
from fake_model import FakeModel  # noqa: E402
from test_responses import get_text_message  # noqa: E402


@pytest.mark.asyncio
async def test_empty_streamed_input_reaches_model() -> None:
    model = FakeModel()
    model.set_next_output([get_text_message("ok")])
    agent = Agent(name="test", model=model)

    result = Runner.run_streamed(agent, input=[])
    async for _ in result.stream_events():
        pass

    assert result.final_output == "ok"
    assert model.last_turn_args["input"] == []

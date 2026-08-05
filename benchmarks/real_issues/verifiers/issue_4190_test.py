import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


UPSTREAM_ROOT = Path.cwd().resolve()
sys.path.insert(0, str(UPSTREAM_ROOT))
sys.path.insert(0, str(UPSTREAM_ROOT / "src"))

from agents.memory.openai_conversations_session import OpenAIConversationsSession  # noqa: E402


@pytest.mark.asyncio
async def test_empty_add_does_not_create_remote_conversation() -> None:
    client = AsyncMock()
    client.conversations.create.return_value = MagicMock(id="unexpected")
    session = OpenAIConversationsSession(openai_client=client)

    await session.add_items([])

    client.conversations.create.assert_not_called()
    client.conversations.items.create.assert_not_called()
    with pytest.raises(ValueError, match="Session ID not yet available"):
        _ = session.session_id


@pytest.mark.asyncio
async def test_empty_add_preserves_existing_session_id() -> None:
    client = AsyncMock()
    session = OpenAIConversationsSession(
        conversation_id="existing", openai_client=client
    )

    await session.add_items([])

    client.conversations.create.assert_not_called()
    client.conversations.items.create.assert_not_called()
    assert session.session_id == "existing"

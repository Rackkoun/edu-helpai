# file tests/test_chat.py

import pytest
from typing import Any, AsyncGenerator
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch
from src.backend.main import app


@pytest.mark.asyncio
async def test_get_history_empty() -> None:
    """GET /chat/history/{id} returns empty list for unknown session"""
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=_empty_session())
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("src.backend.api.routes.chat.get_session", return_value=mock_cm):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/chat/history/nonexistent-session")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_clear_history() -> None:
    """DELETE /chat/history/{id} returns 200"""
    mock_cm = MagicMock()
    mock_session = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("src.backend.api.routes.chat.get_session", return_value=mock_cm):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete("/chat/history/test-session")

    assert resp.status_code == 200
    assert "cleared" in resp.json()["message"]


def _empty_session() -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_chat_message_streams_tokens() -> None:
    """POST /chat/message streams SSE tokens"""

    async def fake_rag_query(*args: Any, **kwargs: Any) -> AsyncGenerator[str, None]:
        for token in ["Hello ", "you"]:
            yield token

    with (
        patch("src.backend.api.routes.chat.RAGService") as mock_rag_cls,
        patch("src.backend.api.routes.chat.track_query", new_callable=AsyncMock),
    ):

        mock_rag = MagicMock()
        mock_rag.query = fake_rag_query
        mock_rag.close = AsyncMock()
        mock_rag_cls.return_value = mock_rag

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/chat/message",
                json={"message": "What is an algorithm?", "session_id": "test-123"},
            )

    assert resp.status_code == 200
    assert "Hello" in resp.text

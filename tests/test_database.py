# file tests/test_database.py

"""Tests for database session helpers"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.backend.core.database import get_session, get_db, init_db, close_db


@pytest.mark.asyncio
async def test_get_session_commits_on_success() -> None:
    """get_session should commit when no exception is raised"""
    mock_session = AsyncMock()
    mock_session_maker = MagicMock(return_value=mock_session)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("src.backend.core.database.async_session_maker", mock_session_maker):
        async with get_session() as session:
            assert session is mock_session

    mock_session.commit.assert_called_once()
    mock_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_get_session_rolls_back_on_error() -> None:
    """get_session should rollback when an exception is raised"""
    mock_session = AsyncMock()
    mock_session_maker = MagicMock(return_value=mock_session)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("src.backend.core.database.async_session_maker", mock_session_maker):
        with pytest.raises(ValueError):
            async with get_session():  # as session:
                raise ValueError("something went wrong")

    mock_session.rollback.assert_called_once()
    mock_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_get_db_yields_session() -> None:
    """get_db dependency should yield the session by get_session"""
    mock_session = AsyncMock()

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("src.backend.core.database.get_session", return_value=mock_cm):
        result = None
        async for s in get_db():
            result = s

    assert result is mock_session


@pytest.mark.asyncio
async def test_init_db_creates_tables() -> None:
    """init_db should run create_all without error"""
    mock_conn = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("src.backend.core.database.engine") as mock_engine:
        mock_engine.begin.return_value = mock_ctx
        await init_db()

    mock_conn.run_sync.assert_called_once()


@pytest.mark.asyncio
async def test_close_db_disposes_engine() -> None:
    """close_db should call engine.dispose"""
    with patch("src.backend.core.database.engine") as mock_engine:
        mock_engine.dispose = AsyncMock()
        await close_db()

    mock_engine.dispose.assert_called_once()

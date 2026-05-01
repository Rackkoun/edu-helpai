# file tests/test_api_documents.py

"""Integration tests for /documents endpoints using TestClient"""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from typing import AsyncGenerator

from src.backend.main import app


@pytest.fixture
def sample_txt():
    return b"This is a sample text document for testing."


@pytest.mark.asyncio
async def test_upload_txt_file(sample_txt) -> None:
    """POST /documents/upload with a valid .txt file should return 200"""
    mock_doc = MagicMock()
    mock_doc.id = 1
    mock_doc.filename = "test.txt"
    mock_doc.content_type = "text/plain"
    # 2 chunks
    mock_doc.chunks = [MagicMock(), MagicMock()]

    with patch(
        "src.backend.api.routes.documents.DocumentProcessor.process_upload",
        new_callable=AsyncMock,
        return_value=mock_doc,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/documents/upload",
                files={"file": ("test.txt", sample_txt, "text/plain")},
            )

    assert resp.status_code == 200
    assert resp.json()["chunk_count"] == 2


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_type() -> None:
    """POST /documents/upload with .exe should return 415."""
    from src.backend.core.database import get_db

    async def override_get_db() -> AsyncGenerator[AsyncMock, None]:
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/documents/upload",
                files={"file": ("malware.exe", b"MZ", "application/octet-stream")},
            )
        assert resp.status_code == 415
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_documents_empty() -> None:
    """GET /documents/ should return an empty list when DB is empty."""
    from src.backend.core.database import get_db

    async def override_get_db() -> AsyncGenerator[AsyncMock, None]:
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/documents/")

        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_upload_file_too_large() -> None:
    """Files over MAX_UPLOAD_SIZE should return 413"""
    from src.backend.config import settings

    huge_content = b"x" * (settings.MAX_UPLOAD_SIZE + 1)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/documents/upload",
            files={"file": ("big.txt", huge_content, "text/plain")},
        )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_embed_document_not_found() -> None:
    """POST /documents/999/embed with unknown id should return 404"""
    from src.backend.core.database import get_db

    async def override_get_db() -> AsyncGenerator[AsyncMock, None]:
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/documents/999/embed")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_document_not_found() -> None:
    """DELETE /documents/999 with unknown id should return 404"""
    from src.backend.core.database import get_db

    async def override_get_db() -> AsyncGenerator[AsyncMock, None]:
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete("/documents/999")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_embed_document_success() -> None:
    """POST /documents/{id}/embed with existing doc returns 200"""
    from src.backend.core.database import get_db

    async def override_get_db() -> AsyncGenerator[AsyncMock, None]:
        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = MagicMock()  # doc exists
        mock_session.execute = AsyncMock(return_value=mock_result)
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with (
            patch(
                "src.backend.api.routes.documents.EmbeddingService.generate_embeddings",
                new_callable=AsyncMock,
            ),
            patch(
                "src.backend.api.routes.documents.EmbeddingService.close",
                new_callable=AsyncMock,
            ),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                resp = await client.post("/documents/1/embed")

        assert resp.status_code == 200

    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_document_success() -> None:
    """DELETE /documents/{id} with existing doc returns 200"""
    from src.backend.core.database import get_db

    async def override_get_db() -> AsyncGenerator[AsyncMock, None]:
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete("/documents/1")
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"]
    finally:
        app.dependency_overrides.clear()

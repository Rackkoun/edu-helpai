# file tests/embedding_service.py

"""
Tests for embedding service: ollama API integration and vector math
"""

import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.backend.services.embedding import EmbeddingService

# nomic-embed-text dimension : 768
FAKE_EMBEDDING = [0.1] * 768


# -----------------
# EMBED BATCH
# -----------------
@pytest.mark.asyncio
async def test_embed_batch_returns_numpy_array():
    """_embed_batch should return a (N, 768) float32 array"""

    svc = EmbeddingService(ollama_url="http://localhost:11434")

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"embedding": FAKE_EMBEDDING}

    svc.client = AsyncMock()
    svc.client.post = AsyncMock(return_value=mock_response)

    result = await svc._embed_batch(["Hello you"])

    assert isinstance(result, np.ndarray)
    assert result.shape == (1, 768)
    assert result.dtype == np.float32


@pytest.mark.asyncio
async def test_embed_batch_handles_multiple_texts():
    """N texts -> shape (N, 768)"""

    svc = EmbeddingService()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"embedding": FAKE_EMBEDDING}

    svc.client = MagicMock()
    svc.client.post = AsyncMock(return_value=mock_response)

    result = await svc._embed_batch(["text one", "text two", "text three"])
    assert result.shape == (3, 768)


@pytest.mark.asyncio
async def test_encode_query_returns_1d_array():
    """encoded query should return 1d vectorm not (1, 768)"""

    svc = EmbeddingService()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"embedding": FAKE_EMBEDDING}

    svc.client = AsyncMock()
    svc.client.post = AsyncMock(return_value=mock_response)

    result = await svc.encode_query("what is O-Notation?")
    assert result.ndim == 1
    assert result.shape == (768,)


@pytest.mark.asyncio
async def test_generate_embeddings_updates_chunks(db_session):
    """Chunks with empty embeddings should be updated after generation"""

    from src.backend.models.document import Document, DocumentChunk

    # seed db with a doc + chunk
    doc = Document(
        filename="test.pdf", content_type="application/pdf", file_path="/tmp/test.pdf"
    )
    db_session.add(doc)
    await db_session.flush()

    chunk = DocumentChunk(
        document_id=doc.id, chunk_index=0, content="The O-Notation is...", embedding=b""
    )
    db_session.add(chunk)
    await db_session.commit()

    svc = EmbeddingService()
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"embedding": FAKE_EMBEDDING}
    svc.client = AsyncMock()
    svc.client.post = AsyncMock(return_value=mock_response)

    with patch("src.backend.services.embedding.get_session") as mock_ctx:
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        await svc.generate_embeddings(doc.id)

    await db_session.refresh(chunk)
    assert chunk.embedding != b""
    assert len(chunk.embedding) == 768 * 4  # float32 = 4 bytes each

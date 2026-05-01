# file tests/test_rag_service.py

"""Tests for RAGService: cosine similarity, context building, streaming"""

import struct
import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.backend.services.rag_service import (
    RAGService,
    _cosine_similarity,
    _bytes_to_vector,
)

# ---------------------------
# Helper math
# ---------------------------


def _vec_to_bytes(v: list[float]) -> bytes:
    return struct.pack(f"{len(v)}f", *v)


def test_cosine_similarity_identical_vectors():
    a = np.array([1.0, 0.0, 0.0])
    assert _cosine_similarity(a, a) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors():
    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    assert _cosine_similarity(a, b) == pytest.approx(0.0)


def test_cosine_similarity_zero_vector():
    """Zero vector should return 0 without dividing by zero."""
    a = np.array([0.0, 0.0])
    b = np.array([1.0, 0.0])
    assert _cosine_similarity(a, b) == 0.0


def test_bytes_to_vector_roundtrip():
    original = [0.1, 0.2, 0.3, 0.4]
    blob = _vec_to_bytes(original)
    result = _bytes_to_vector(blob)
    np.testing.assert_allclose(result, original, rtol=1e-5)


def test_build_context_empty():
    rag = RAGService.__new__(RAGService)  # bypass __init__
    result = rag._build_context([])
    assert "No relevant" in result


def test_build_context_formats_chunks():
    rag = RAGService.__new__(RAGService)

    chunk = MagicMock()
    chunk.id = 42
    chunk.content = "Chunk content."

    result = rag._build_context([chunk])
    assert "Source 1" in result
    assert "chunk_id=42" in result
    assert "Chunk content." in result


# --------------------
# Retrieval
# --------------------


@pytest.mark.asyncio
async def test_retrieve_returns_top_k(db_session):
    """Given 5 chunks, retrieve should return top-K by similarity."""
    from src.backend.models.document import Document, DocumentChunk

    doc = Document(
        filename="bio.pdf", content_type="application/pdf", file_path="/tmp/bio.pdf"
    )
    db_session.add(doc)
    await db_session.flush()

    # Create 5 chunks with different embeddings
    base_vec = np.zeros(768, dtype=np.float32)
    for i in range(5):
        v = base_vec.copy()
        v[i] = float(i + 1)
        chunk = DocumentChunk(
            document_id=doc.id,
            chunk_index=i,
            content=f"chunk {i}",
            embedding=v.tobytes(),
        )
        db_session.add(chunk)
    await db_session.commit()

    rag = RAGService.__new__(RAGService)
    rag.embedding_svc = AsyncMock()

    query_vec = np.zeros(768, dtype=np.float32)
    query_vec[4] = 5.0  # most similar to chunk 4
    rag.embedding_svc.encode_query = AsyncMock(return_value=query_vec)

    with patch("src.backend.services.rag_service.get_session") as mock_ctx:
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        results = await rag._retrieve("test query", top_k=3)

    assert len(results) == 3
    assert results[0].chunk_index == 4  # highest similarity


@pytest.mark.asyncio
async def test_query_yields_tokens():
    """query() should yield at least one token"""
    rag = RAGService.__new__(RAGService)
    rag.embedding_svc = AsyncMock()
    rag.embedding_svc.encode_query = AsyncMock(return_value=np.zeros(768))
    rag.client = AsyncMock()

    async def fake_retrieve(*args, **kwargs):
        return []

    async def fake_stream(*args, **kwargs):
        for token in ["Hello ", "you"]:
            yield token

    async def fake_save(*args, **kwargs):
        pass

    async def fake_load(*args, **kwargs):
        return []

    setattr(rag, "_retrieve", fake_retrieve)
    setattr(rag, "_stream_ollama", fake_stream)
    setattr(rag, "_save_turn", fake_save)
    setattr(rag, "_load_history", fake_load)

    tokens = []
    async for token in rag.query("What is an algorithm?", "test-session"):
        tokens.append(token)

    assert len(tokens) > 0
    assert "".join(tokens) == "Hello you"


@pytest.mark.asyncio
async def test_save_turn_persists_to_db() -> None:
    """_save_turn should add a Conversation row and commit"""
    rag = RAGService.__new__(RAGService)

    mock_session = AsyncMock()
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("src.backend.services.rag_service.get_session", return_value=mock_cm):
        await rag._save_turn("sess-1", "user", "What is an algorithm?", None)

    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_load_history_returns_messages() -> None:
    """_load_history should return role/content dicts in chronological order"""
    from src.backend.models.document import Conversation
    from datetime import datetime, timezone

    rag = RAGService.__new__(RAGService)

    turn = MagicMock(spec=Conversation)
    turn.role = "user"
    turn.content = "Hello"
    turn.timestamp = datetime.now(timezone.utc)

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [turn]
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("src.backend.services.rag_service.get_session", return_value=mock_cm):
        result = await rag._load_history("sess-1", limit=6)

    assert result == [{"role": "user", "content": "Hello"}]


@pytest.mark.asyncio
async def test_rag_service_close() -> None:
    """close() should shut down both the HTTP client and embedding service"""
    rag = RAGService.__new__(RAGService)
    rag.client = AsyncMock()
    rag.embedding_svc = AsyncMock()

    await rag.close()

    rag.client.aclose.assert_called_once()
    rag.embedding_svc.close.assert_called_once()


def test_rag_service_init() -> None:
    """RAGService.__init__ should set up client and embedding service"""
    with (
        patch("src.backend.services.rag_service.EmbeddingService") as mock_emb,
        patch("src.backend.services.rag_service.httpx.AsyncClient") as mock_client,
    ):
        rag = RAGService()

    assert rag is not None
    mock_emb.assert_called_once()
    mock_client.assert_called_once()

# file src/backend/services/rag_service.py
"""
RAG Service.
Flow:
    1. embed user query via ollama nomic-embed-text
    2. load all chunk embeddings from SQLite
    3. cosine similarity -> top-k chunks
    4. build prompt with retrieved context
    5. stream response from ollama chat api
"""

import json
import struct
from typing import AsyncGenerator, List, Tuple

import httpx
import numpy as np
from sqlalchemy import select

from src.backend.core.database import get_session
from src.backend.models.document import Conversation, DocumentChunk
from src.backend.services.embedding import EmbeddingService
from src.backend.config import settings


def _bytes_to_vector(blob: bytes) -> np.ndarray:
    """Deserialize float32 bytes -> numpy array"""
    n = len(blob) // 4
    return np.array(struct.unpack(f"{n}f", blob), dtype=np.float32)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two 1D-vectors"""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


class RAGService:
    """RAG pipeline"""

    SYSTEM_PROMPT = """
        You are Edu-HelpAI, a helpful study assistant.
        Answer questions based ONLY on the provided context.
        If the context doesn't contain the answer, say so honestly, do not guess.
        Cite which document/chunk you used when possible.

        IMPORTANT: Always repond in the same language the user used in their question.
        If the user writes in French, respond in French.
        If the user writes in German, respond in German.
        If the user writes in English, respond in English.
        Never switch languages mid-response.
    """

    def __init__(self) -> None:
        self.embedding_svc = EmbeddingService()
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0, read=settings.OLLAMA_TIMEOUT, write=10.0, pool=10.0
            )
        )

    # --------------------------------------------------------------
    # PUBLIC API
    # --------------------------------------------------------------
    async def query(
        self, user_message: str, session_id: str, tok_k: int | None = None
    ) -> AsyncGenerator[str, None]:

        # 1. retrieve relevant chunks
        chunks = await self._retrieve(user_message, tok_k or settings.RAG_TOP_K)

        # 2. build context string
        context = self._build_context(chunks)

        # 3. load recent conversation history
        history = await self._load_history(session_id, limit=6)

        # 4. save user turn to db
        await self._save_turn(session_id, "user", user_message)

        # 5. stream llm response
        full_response = ""
        async for token in self._stream_ollama(user_message, context, history):
            full_response += token
            yield token

        # 6. save assistant turn + source chunk references
        source_ids = [str(c.id) for c in chunks]
        await self._save_turn(
            session_id, "assistant", full_response, source_chunks=json.dumps(source_ids)
        )

    async def get_source_chunks(
        self, user_message: str, top_k: int | None = None
    ) -> List[DocumentChunk]:
        """Return the chunks that will be used for a query"""

        return await self._retrieve(user_message, top_k or settings.RAG_TOP_K)

    # --------------------------------------------------------
    # INTERNAL HELPERS
    # --------------------------------------------------------
    async def _retrieve(self, query: str, top_k: int) -> List[DocumentChunk]:
        """Embed query and return top-k most similar chunks"""
        query_vec = await self.embedding_svc.encode_query(query)

        async with get_session() as session:
            result = await session.execute(
                select(DocumentChunk).where(DocumentChunk.embedding != b"")
            )
            all_chunks = result.scalars().all()

        if not all_chunks:
            return []

        # compute cosine similarity for every chunks
        scored: List[Tuple[float, DocumentChunk]] = []
        for chunk in all_chunks:
            vec = _bytes_to_vector(chunk.embedding)
            score = _cosine_similarity(query_vec, vec)
            scored.append((score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [chunk for _, chunk in scored[:top_k]]

    def _build_context(self, chunks: List[DocumentChunk]) -> str:
        """Format retrieved chunks into a context block for the prompt"""
        if not chunks:
            return "No relevant documents found."
        parts = []
        for i, chunk in enumerate(chunks, 1):
            parts.append(f"[Source {i} - chunk_id={chunk.id}]\n{chunk.content}")
        return "\n\n---\n\n".join(parts)

    async def _stream_ollama(
        self, user_message: str, context: str, history: List[dict[str, str]]
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from Ollama /api/chat endpoint"""
        messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]

        # inject retrieved context
        messages.append(
            {
                "role": "system",
                "content": f"RELEVANT CONTEXT:\n{context}",
            }
        )

        # recent conversation turns
        messages.extend(history)

        # current user question
        messages.append({"role": "user", "content": user_message})

        url = f"{settings.OLLAMA_URL}/api/chat"
        payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": messages,
            "stream": True,
            "options": {"num_predict": settings.MAX_TOKENS},
        }

        async with self.client.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                data = json.loads(line)
                token = data.get("message", {}).get("content", "")
                if token:
                    yield token
                if data.get("done"):
                    break

    async def _load_history(
        self, session_id: str, limit: int = 6
    ) -> List[dict[str, str]]:
        """Load the last N conversation turns"""
        async with get_session() as session:
            from sqlalchemy import desc
            from src.backend.models.document import Conversation

            result = await session.execute(
                select(Conversation)
                .where(Conversation.session_id == session_id)
                .order_by(desc(Conversation.timestamp))
                .limit(limit)
            )
            rows = result.scalars().all()

        # reverse to chronological order
        return [{"role": r.role, "content": r.content} for r in reversed(rows)]

    async def _save_turn(
        self, session_id: str, role: str, content: str, source_chunks: str | None = None
    ) -> None:
        """Persist a conversation turn to the db"""
        async with get_session() as session:
            turn = Conversation(
                session_id=session_id,
                role=role,
                content=content,
                source_chunks=source_chunks,
            )
            session.add(turn)
            await session.commit()

    async def close(self) -> None:
        await self.client.aclose()
        await self.embedding_svc.close()

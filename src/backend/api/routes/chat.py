# file src/backend/api/routes/chat.py

import uuid
from typing import AsyncGenerator, Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, delete

from src.backend.core.database import get_session
from src.backend.models.document import Conversation
from src.backend.services.rag_service import RAGService
from src.backend.services.mlflow_tracker import track_query

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    session_id: str = ""


@router.post("/message")
async def chat_message(request: ChatRequest) -> StreamingResponse:
    """
    RAG-powered chat endpoint with streaming
    Returns text/event-strem so the frontend can render token live
    """

    session_id = request.session_id or str(uuid.uuid4())
    rag = RAGService()

    async def token_stream() -> AsyncGenerator[str, None]:
        full = ""

        try:
            async for token in rag.query(request.message, session_id):
                full += token
                yield f"data: {token}\n\n"
        finally:
            await rag.close()
            # mlflow non blocking log
            await track_query(request.message, full, session_id)

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        token_stream(),
        media_type="text/event-stream",
        headers={
            "X-Session-Id": session_id,
            "Cache-Control": "no-cache",
        },
    )


@router.get("/history/{session_id}")
async def get_history(session_id: str) -> list[dict[str, Any]]:
    """Return full conversation history for a session"""
    async with get_session() as session:
        result = await session.execute(
            select(Conversation)
            .where(Conversation.session_id == session_id)
            .order_by(Conversation.timestamp)
        )
        rows = result.scalars().all()

    return [
        {
            "role": r.role,
            "content": r.content,
            "timestamp": r.timestamp,
            "source_chunks": r.source_chunks,
        }
        for r in rows
    ]


@router.delete("/history/{session_id}")
async def clear_history(session_id: str) -> dict[str, str]:
    """Clear all messages for a session"""
    async with get_session() as session:
        await session.execute(
            delete(Conversation).where(Conversation.session_id == session_id)
        )

        await session.commit()

    return {"message": f"History cleared for session {session_id}"}

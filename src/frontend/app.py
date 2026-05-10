# file src/frontend/app.py
"""
Edu-HelpAI UI

RUN with chainlit src/frontend/app.py --port 8001
"""

# flake8: noqa: E402
import os

# remove database url from the frontend so chainlit it from the backend
os.environ.pop("DATABASE_URL", None)
# disable literalai
os.environ.pop("LITERAL_API_KEY", None)
from typing import Any
import uuid
import httpx
import json
import chainlit as cl
from chainlit.server import app
from fastapi.responses import PlainTextResponse

#  FastAPI backend
API_BASE = os.environ.get("API_BASE", "http://localhost:8000")


# healthz check
@app.get("/healthz")
async def healthz() -> PlainTextResponse:
    return PlainTextResponse("ok")


# -----------------------------------
#  LIFECYCLE
# -----------------------------------
@cl.on_chat_start
async def on_chat_start() -> None:
    """Runs once whe a user opens the chat"""
    session_id = str(uuid.uuid4())
    cl.user_session.set("session_id", session_id)

    # fetch existing docs
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{API_BASE}/documents/")
        docs = resp.json() if resp.is_success else []

    doc_list = (
        "\n".join(f"  • **{d['filename']}** ({d['chunk_count']} chunks)" for d in docs)
        or "  *(none yet)*"
    )

    await cl.Message(
        content=(
            "# 👋 Welcome to Edu-HelpAI!\n\n"
            "I'm your personnal study assistant. "
            "Upload your lecture notes, PDFs, or CSV files and ask me everything.\n\n"
            f"**Knowledge base:**\n{doc_list}\n\n"
            "Attach files using this symbol 📎 below."
        )
    ).send()


# ------------------------------------
# FILE UPLOAD
# ------------------------------------
@cl.on_message
async def on_message(message: cl.Message) -> None:
    session_id = cl.user_session.get("session_id")

    # handle attached files first
    if message.elements:
        for element in message.elements:
            if hasattr(element, "path"):
                await _handle_file_upload(element)

        # if message has only files (no text questions) stop here
        if message.content.strip():
            await cl.Message(
                content=(
                    "✅ File processed. "
                    "Your question has been noted — "
                    "please send it again as a separate message so I can answer it."
                )
            ).send()
        return  # always return after uploads

    # otherwise treat as question
    await _handle_chat(message.content, session_id)


async def _handle_file_upload(element: Any) -> None:
    """Upload a file to the backend and trigger embedding"""
    filename = element.name
    status_msg = cl.Message(content=f"⏳ Processing **{filename}**...")
    await status_msg.send()

    with open(element.path, "rb") as f:
        file_bytes = f.read()

    # detect content type from extension
    ext = filename.rsplit(".", 1)[-1].lower()
    mime_map = {
        "pdf": "application/pdf",
        "txt": "text/plain",
        "md": "text/markdown",
        "csv": "text/csv",
    }
    content_type = mime_map.get(ext, "text/plain")

    async with httpx.AsyncClient(timeout=120.0) as client:
        # 1. upload + chunk
        upload_resp = await client.post(
            f"{API_BASE}/documents/upload",
            files={"file": (filename, file_bytes, content_type)},
        )
        if not upload_resp.is_success:
            status_msg.content = f"❌ Upload failed: {upload_resp.text}"
            await status_msg.update()
            return

        data = upload_resp.json()
        doc_id = data["id"]
        chunk_count = data["chunk_count"]

        status_msg.content = (
            f"⏳ Uploaded **{filename}** ({chunk_count} chunks). "
            "Generating embeddings..."
        )
        await status_msg.update()

        # 2. generate embeddings
        embed_resp = await client.post(f"{API_BASE}/documents/{doc_id}/embed")
        if not embed_resp.is_success:
            status_msg.content = f"❌ Embedding failed: {embed_resp.text}"
            await status_msg.update()
            return

    status_msg.content = (
        f"✅ **{filename}** added to knowledge base ({chunk_count} chunks). "
        "Ask away!"
    )
    await status_msg.update()


# -------------------------------------------
# CHAT
# -------------------------------------------
async def _handle_chat(user_message: str, session_id: str) -> None:
    """Send user question to RAG backend and stream the response"""
    answer_msg = cl.Message(content="")
    await answer_msg.send()

    try:
        async with httpx.AsyncClient(timeout=600.0) as client:
            async with client.stream(
                "POST",
                f"{API_BASE}/chat/message",
                json={"message": user_message, "session_id": session_id},
            ) as resp:
                if not resp.is_success:
                    answer_msg.content = "❌ Backend error. Is the API running?"
                    await answer_msg.update()
                    return

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    token = line[6:]
                    if token == "[DONE]":
                        break
                    answer_msg.content += token
                    await answer_msg.update()

    except httpx.ReadTimeout:
        answer_msg.content = (
            "⏱️ Ollama is taking too long to respond. "
            "The model may still be loading. Please try again in ~30 seconds."
        )
        await answer_msg.update()
    except httpx.RemoteProtocolError as e:
        answer_msg.content = f"⚠️ Connection interrupted: {e}. Please try again."
        await answer_msg.update()

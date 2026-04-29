# file src/frontend/app.py
"""
    Edu-HelpAI UI

    RUN with chainlit src/frontend/app.py --port 8001
"""

import uuid
import httpx
import chainlit as cl

#  FastAPI backend
API_BASE = "http://localhost:8000"


# -----------------------------------
#  LIFECYCLE
# -----------------------------------
@cl.on_chat_start
async def on_chat_start():
    """Runs once whe a user opens the chat"""
    session_id = str(uuid.uuid4())
    cl.user_session.set("session_id", session_id)

    # fetch existing docs
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{API_BASE}/documents/")
        docs = resp.json() if resp.is_success else []
    
    doc_list = "\n".join(
        f"  • **{d['filename']}** ({d['chunk_count']} chunks)" for d in docs
    ) or "  *(none yet)*"

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
async def on_message(message: cl.Message):
    session_id = cl.user_session.get("session_id")

    # handle attached files first
    if message.elements:
        for element in message.elements:
            if hasattr(element, "path"):
                await _handle_file_upload(element)
        
        # if message has only files (no text questions) stop here
        if not message.content.strip():
            return
    
    # otherwise treat as question
    await _handle_chat(message.content, session_id)

async def _handle_file_upload(element) -> None:
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
            files={"file": (filename, file_bytes, content_type)}
        )
        if not upload_resp.is_success:
            await status_msg.update(content=f"❌ Upload failed: {upload_resp.text}")
            return
        
        data = upload_resp.json()
        doc_id = data["id"]
        chunk_count = data["chunk_count"]

        await status_msg.update(
            content=f"⏳ Uploaded **{filename}** ({chunk_count} chunks). Generating embeddings..."
        )

        # 2. generate embeddings
        embed_resp = await client.post(f"{API_BASE}/documents/{doc_id}/embed")
        if not embed_resp.is_success:
            await status_msg.update(content=f"❌ Embedding failed: {embed_resp.text}")
            return
    
    await status_msg.update(content=f"✅ **{filename}** added to knowledge base ({chunk_count} chunks). Ask away!")


# -------------------------------------------
# CHAT
# -------------------------------------------
async def _handle_chat(user_message: str, session_id: str) -> None:
    """Send user question to RAG backend and stream the response"""
    answer_msg = cl.Message(content="")
    await answer_msg.send()

    async with httpx.AsyncClient(timeout=180.0) as client:
        async with client.stream(
            "POST", f"{API_BASE}/chat/message",
            json={"message": user_message, "session_id": session_id},
        ) as resp:
            if not resp.is_success:
                await answer_msg.update(content="❌ Backend error. Is the API running?")
                return
            
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue

                token = line[6:]  # strip "data: "
                if token == "[DONE]":
                    break

                answer_msg.content += token
                await answer_msg.update()
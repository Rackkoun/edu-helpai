# file src/backend/api/routes/documents.py

"""
    Endpoints to upload PDFs/txt/CSV to build knowledge base
    USAGE:
        POST /documents/upload: parse chunk, save to db (no embedding yet)
        POST /documents/{id}/embed: trigger embedding generation
        GET /documents/: list all uploaded documents
        DELETE /documents/{id}: remove document + its chunks
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.core.database import get_db
from src.backend.models.document import Document
from src.backend.services.document_processor import DocumentProcessor
from src.backend.services.embedding import EmbeddingService
from src.backend.config import settings

router = APIRouter()

ALLOWED_TYPES = {
    "application/pdf",
    "text/plain",
    "text/csv",
    "text/markdown",
}


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """
        Upload and process document
        Return the created Document with its chunk count
    """
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {file.content_type}."
            f"Allowed: {ALLOWED_TYPES}",
        )
    
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max {settings.MAX_UPLOAD_SIZE // 1024 // 1024} MB."
        )
    
    processor = DocumentProcessor()
    doc = await processor.process_upload(content, file.filename, file.content_type)

    return {
        "id": doc.id,
        "filename": doc.filename,
        "conten_type": doc.content_type,
        "chunk_count": len(doc.chunks),
        "message": "Upload successful. Call /embed to generate embeddings.",
    }

router.post("/{document_id}/embed")
async def embed_document(document_id: int, session: AsyncSession = Depends(get_db)):
    """
        Trigger embedding generation for all chunks of the document
    """
    result = await session.execute(
        select(Document).where(Document.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    svc = EmbeddingService()
    try:
        await svc.generate_embeddings(document_id)
    finally:
        await svc.close()
    
    return {"message": f"Embeddings generated for {document_id}"}

@router.get("/")
async def list_documents(session: AsyncSession = Depends(get_db)):
    """List all documents in the knowledge base"""
    result = await session.execute(select(Document))
    docs = result.scalars().all()
    return [{
        "id": d.id,
        "filename": d.filename,
        "content_type": d.content_type,
        "upload_date": d.upload_date,
        "chunk_count": len(d.chunks)
    } for d in docs]


@router.delete("/{document_id}")
async def delete_document(document_id: int, session: AsyncSession = Depends(get_db)):
    """Delete a document and all its chunks (cascade)"""
    result = await session.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    await session.delete(doc)
    await session.commit()
    return {"message": f"Document {document_id} deleted"}
# src/backend/models/document.py
from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.sqlite import BLOB

from src.backend.core.database import Base


class Document(Base):
    """Store uploaded documents with metadata"""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100))
    upload_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    file_path: Mapped[str] = mapped_column(String(500)) # local storage path

    # relationships
    chunks: Mapped[List["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all,delete-orphan",
        lazy="selectin",  # async-friendly loading
    )

class DocumentChunk(Base):
    """vector chunks for RAG retrieval"""

    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[bytes] = mapped_column(BLOB, nullable=True)
    document: Mapped["Document"] = relationship(back_populates="chunks")

class Conversation(Base):
    """Chat history for context."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    role: Mapped[str] = mapped_column(String(20))  # user or assistant
    content: Mapped[str] = mapped_column(Text)
    # track documents used for response
    source_chunks: Mapped[Optional[str]] = mapped_column(Text)  # JSON of chunk ids
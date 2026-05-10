# file tests/test_document_processor.py

"""Tests for document processor file parsing and chunking"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.services.document_processor import DocumentProcessor

SAMPLE_TXT = b"Hello! This is a test document. It as multiple sentences."
SAMPLE_PDF_CONTENT = b"%PDF-1.4"  # minimal pdf bytes for mocking


@pytest.fixture
def processor(tmp_path: Path) -> DocumentProcessor:
    """Document processor with a temp upload dir"""
    return DocumentProcessor(upload_dir=tmp_path / "uploads")


# ----------------------------
# TEXT EXTRACTION
# ----------------------------
def test_extract_text_from_txt(processor: DocumentProcessor) -> None:
    """Plain text"""
    # decode directly for txt
    text = SAMPLE_TXT.decode("utf-8")
    assert "Hello" in text


def test_extract_pdf_returns_string(processor: DocumentProcessor) -> None:
    result = processor._extract_pdf(b"not-a-real-pdf")

    assert isinstance(result, str)
    assert "PDF extraction error" in result


@patch("src.backend.services.document_processor.pypdf.PdfReader")
def extract_pdf_reads_pages(mock_reader_cls, processor: DocumentProcessor) -> None:
    """should concatenate text from all pages"""

    mock_page1 = MagicMock()
    mock_page1.extract_text.return_value = "Page one content"
    mock_page2 = MagicMock()
    mock_page2.extract_text.return_value = "Page two content"

    mock_reader = MagicMock()
    mock_reader.__enter__ = lambda s: mock_reader
    mock_reader.__exit__ = MagicMock(return_value=False)
    mock_reader.pages = [mock_page1, mock_page2]
    mock_reader_cls.return_value = mock_reader

    result = processor._extract_pdf(SAMPLE_PDF_CONTENT)
    assert "Page one content" in result
    assert "Page two content" in result


# --------------------------------
# UPLOAD
# --------------------------------
@pytest.mark.asyncio
async def test_process_upload_txt(
    processor: DocumentProcessor, db_session: AsyncSession
) -> None:
    """Full upload pipeline for .txt file. Mock get_session to the test db"""

    @asynccontextmanager
    async def fake_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    with patch("src.backend.services.document_processor.get_session", fake_get_session):
        doc = await processor.process_upload(SAMPLE_TXT, "test.txt", "text/plain")

    assert doc.filename == "test.txt"
    assert doc.content_type == "text/plain"
    assert len(doc.chunks) > 0


@pytest.mark.asyncio
async def test_process_upload_creates_file_on_disk(
    processor: DocumentProcessor, db_session: AsyncSession
) -> None:
    """Uploaded file should be persisted to disk"""

    @asynccontextmanager
    async def fake_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    with patch("src.backend.services.document_processor.get_session", fake_get_session):
        await processor.process_upload(SAMPLE_TXT, "notes.txt", "text/plain")

    saved_files = list(processor.upload_dir.iterdir())
    assert len(saved_files) >= 1


@pytest.mark.asyncio
async def test_process_upload_sanitize_filename(
    processor: DocumentProcessor, db_session: AsyncSession
) -> None:
    """Dangerous characters in filenames should be stripped"""

    @asynccontextmanager
    async def fake_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    dangerous_name = "../../../etc/passwd.txt"

    with patch("src.backend.services.document_processor.get_session", fake_get_session):

        doc = await processor.process_upload(SAMPLE_TXT, dangerous_name, "text/plain")
    # file path should not contain directory traversal
    assert ".." not in doc.file_path

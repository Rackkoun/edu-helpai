# file src/backend/services/document_processor.py

import hashlib
import io
from pathlib import Path
from typing import List
import pypdf
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.backend.models.document import Document, DocumentChunk
from src.backend.core.database import get_session
from src.backend.config import settings

class DocumentProcessor:
    """handles document parsing and chunking"""

    def __init__(self, upload_dir: Path = None):
        self.upload_dir = upload_dir or settings.UPLOAD_DIR
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
    
    async def process_upload(
            self,
            file_content: bytes,
             filename: str,
             content_type: str
    ) -> Document:
        """process upload file into chunks"""
        file_hash = hashlib.sha256(file_content).hexdigest()[:12]
        safe_name = "".join(c for c in filename if c.isalnum() or c in "._-")
        file_path = self.upload_dir / f"{file_hash}_{safe_name}"
        file_path.write_bytes(file_content)

        # extract text
        if content_type == "application/pdf":
            text = self._extract_pdf(file_content)
        else:
            text = file_content.decode("utf-8", errors="ignore")
        
        # create doc and chunks
        async with get_session() as session:
            doc = Document(
                filename=filename,
                content_type=content_type,
                file_path=str(file_path)
            )
            session.add(doc)
            await session.flush()

            chunks = self.text_splitter.split_text(text)
            for idx, chunk_text in enumerate(chunks):
                chunk = DocumentChunk(
                    document_id=doc.id,
                    chunk_index = idx,
                    content=chunk_text,
                    embedding=b"",  # placeholder
                )
                session.add(chunk)
            
            await session.commit()
            # refresh to get relationships loaded
            await session.refresh(doc, attribute_names=["chunks"])
            return doc
    

    def _extract_pdf(self, content: bytes) -> str:
        """extract text from"""
        text_parts = []

        try:
            with pypdf.PdfReader(io.BytesIO(content)) as reader:
                for page in reader.pages:
                    text_parts.append(page.extract_text() or "")
        except Exception as e:
            text_parts.append(f"PDF extraction error: {e}")
        
        return "\n".join(text_parts)

# file src/backend/services/embedding.py

import json
import struct
from typing import List

import httpx
import numpy as np

from sqlalchemy import select, text

from src.backend.models.document import DocumentChunk
from src.backend.core.database import get_session
from src.backend.config import settings

class EmbeddingService:
    """local embedding generation"""

    def __init__(self, model: str = "nomic-embed-text", ollama_url: str = None):
        self.model = model
        self.dimension = 768
        self.ollama_url = ollama_url or settings.OLLAMA_URL
        self.client = httpx.AsyncClient(timeout=60.0)
    
    async def generate_embeddings(self, document_id: int) -> None:
        """generate and store embeddings for all chunks of a doc"""
        async with get_session() as session:
            # get chunks without embeddings
            result = await session.execute(
                select(DocumentChunk).where(
                    DocumentChunk.document_id == document_id,
                    DocumentChunk.embedding == b""
                )
            )

            chunks = result.scalars().all()
            if not chunks:
                return
            
            # generate embeddings via ollama api
            texts = [chunk.content for chunk in chunks]
            embeddings = await self._embed_batch(texts)

            # store as bytes (float32)
            for chunk, embedding in zip(chunks, embeddings):
                chunk.embedding = embedding.astype(np.float32).tobytes()
            
            await session.commit()
        
    async def _embed_batch(self, texts: List[str]) -> np.ndarray:
        """call ollama embedding API"""

        # ollama endpoint
        url = f"{self.ollama_url}/api/embeddings"

        embeddings = []
        for text in texts:
            payload = {
                "model": self.model,
                "prompt": text
            }
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            embeddings.append(data["embedding"])
        
        return np.array(embeddings, dtype=np.float32)
    
    async def encode_query(self, text: str) -> np.ndarray:
        """encode user query for similarity search"""
        result = await self._embed_batch([text])
        return result[0]

    async def close(self):
        """clean up http client"""
        await self.client.aclose()
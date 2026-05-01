# file src/backend/main.py

"""
FastAPI application entry point

Startup: init DB tables
Shutdown: close engine + http clients
"""

from typing import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.backend.core.database import init_db, close_db
from src.backend.api.routes import health, documents, chat
from src.backend.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize on startup, clean up on shutdown"""
    await init_db()
    yield
    await close_db()


app = FastAPI(title=settings.APP_NAME, version="0.1.0", lifespan=lifespan)

# allow chainlit (on different port) to call API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://localhost:8001"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(documents.router, prefix="/documents", tags=["documents"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])

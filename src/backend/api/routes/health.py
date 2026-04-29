# file src/backend/api/routes/health.py

from fastapi import APIRouter
from src.backend.config import settings

router = APIRouter()

@router.get("/")
async def health_check():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "environment": settings.ENVIRONMENT
    }
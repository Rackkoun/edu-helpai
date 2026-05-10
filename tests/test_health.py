# file tests/test_health.py

import pytest
from httpx import AsyncClient, ASGITransport
from src.backend.main import app


@pytest.mark.asyncio
async def test_health_check() -> None:

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health/")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

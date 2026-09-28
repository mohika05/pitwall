from unittest.mock import AsyncMock

import httpx
import pytest

from app.api.routers import preparation
from app.main import app


@pytest.mark.asyncio
async def test_preparation_api_requires_configured_admin_token(monkeypatch):
    monkeypatch.setattr(preparation.settings, "app_env", "production")
    monkeypatch.setattr(preparation.settings, "pitwall_admin_token", "correct-token")
    start = AsyncMock(return_value={"state": "queued", "session_key": 42})
    monkeypatch.setattr(preparation.preparation_service, "start", start)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        missing = await client.post("/api/preparation/42", json={"telemetry": True})
        wrong = await client.post(
            "/api/preparation/42",
            json={"telemetry": True},
            headers={"X-Pitwall-Admin": "wrong-token"},
        )
        allowed = await client.post(
            "/api/preparation/42",
            json={"telemetry": True},
            headers={"X-Pitwall-Admin": "correct-token"},
        )

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert allowed.status_code == 202
    start.assert_awaited_once_with(42, True)


@pytest.mark.asyncio
async def test_production_preparation_fails_closed_without_server_token(monkeypatch):
    monkeypatch.setattr(preparation.settings, "app_env", "production")
    monkeypatch.setattr(preparation.settings, "pitwall_admin_token", None)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/preparation")

    assert response.status_code == 503

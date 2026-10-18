from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError


async def test_database_outage_does_not_prevent_application_startup(monkeypatch):
    from app import main

    recover = AsyncMock(side_effect=SQLAlchemyError("quota unavailable"))
    monkeypatch.setattr(main.preparation_service, "recover", recover)
    monkeypatch.setattr(main.preparation_service, "close", AsyncMock())
    monkeypatch.setattr(main.replay_registry, "close", AsyncMock())
    monkeypatch.setattr(main, "close_redis", AsyncMock())
    dispose = AsyncMock()
    monkeypatch.setattr(main, "engine", SimpleNamespace(dispose=dispose))

    async with main.lifespan(main.app):
        assert recover.await_count == 1

    main.preparation_service.close.assert_awaited_once()
    main.replay_registry.close.assert_awaited_once()
    main.close_redis.assert_awaited_once()
    dispose.assert_awaited_once()


async def test_database_health_reports_temporary_outage():
    from app.api.routers.health import database_health

    database = SimpleNamespace(
        execute=AsyncMock(side_effect=SQLAlchemyError("quota unavailable"))
    )

    with pytest.raises(HTTPException) as error:
        await database_health(database)

    assert error.value.status_code == 503
    assert error.value.detail == "Database is temporarily unavailable"

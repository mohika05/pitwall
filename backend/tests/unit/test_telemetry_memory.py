from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.api.routers import telemetry as telemetry_router


class _DatabaseContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_args):
        return None


async def test_field_snapshot_loads_car_data_only_for_selected_driver(monkeypatch):
    drivers = [
        SimpleNamespace(driver_number=4, name_acronym="NOR"),
        SimpleNamespace(driver_number=63, name_acronym="RUS"),
    ]
    context = SimpleNamespace(drivers=drivers)
    repository = SimpleNamespace(get_replay_context=AsyncMock(return_value=context))
    monkeypatch.setattr(telemetry_router, "AsyncSessionLocal", _DatabaseContext)
    monkeypatch.setattr(telemetry_router, "SessionRepository", lambda _db: repository)

    full = AsyncMock(
        return_value={"driver": "NOR", "car": {"Speed": 300}, "position": {"X": 1}}
    )
    position = AsyncMock(
        return_value={"driver": "RUS", "car": None, "position": {"X": 2}}
    )
    monkeypatch.setattr(telemetry_router.telemetry_service, "snapshot", full)
    monkeypatch.setattr(
        telemetry_router.telemetry_service,
        "position_snapshot",
        position,
    )

    response = await telemetry_router.telemetry_snapshot(
        9896,
        timestamp=SimpleNamespace(isoformat=lambda: "2025-10-05T12:00:00Z"),
        driver="nor",
        tolerance_seconds=2.0,
    )

    full.assert_awaited_once()
    position.assert_awaited_once()
    assert response["drivers"][0]["car"] == {"Speed": 300}
    assert response["drivers"][1]["car"] is None


async def test_field_snapshot_defaults_full_car_data_to_first_driver(monkeypatch):
    drivers = [
        SimpleNamespace(driver_number=4, name_acronym="NOR"),
        SimpleNamespace(driver_number=63, name_acronym="RUS"),
    ]
    context = SimpleNamespace(drivers=drivers)
    repository = SimpleNamespace(get_replay_context=AsyncMock(return_value=context))
    monkeypatch.setattr(telemetry_router, "AsyncSessionLocal", _DatabaseContext)
    monkeypatch.setattr(telemetry_router, "SessionRepository", lambda _db: repository)

    full = AsyncMock(
        return_value={"driver": "NOR", "car": {"Speed": 300}, "position": {"X": 1}}
    )
    position = AsyncMock(
        return_value={"driver": "RUS", "car": None, "position": {"X": 2}}
    )
    monkeypatch.setattr(telemetry_router.telemetry_service, "snapshot", full)
    monkeypatch.setattr(
        telemetry_router.telemetry_service,
        "position_snapshot",
        position,
    )

    response = await telemetry_router.telemetry_snapshot(
        9896,
        timestamp=SimpleNamespace(isoformat=lambda: "2025-10-05T12:00:00Z"),
        driver=None,
        tolerance_seconds=2.0,
    )

    full.assert_awaited_once()
    position.assert_awaited_once()
    assert response["drivers"][0]["car"] == {"Speed": 300}
    assert response["drivers"][1]["car"] is None

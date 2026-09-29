from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.api.routers import sessions as sessions_router


class _DatabaseContext:
    def __init__(self, database):
        self.database = database

    async def __aenter__(self):
        return self.database

    async def __aexit__(self, *_args):
        return None


async def test_session_directory_uses_bulk_metadata_and_readiness(monkeypatch):
    row = SimpleNamespace(
        session_key=9896,
        meeting_key=1270,
        year=2025,
        country_name="Singapore",
        session_name="Race",
        date_start=datetime(2025, 10, 5, 12, tzinfo=UTC),
    )
    result = SimpleNamespace(all=lambda: [(row, "Singapore Grand Prix")])
    database = SimpleNamespace(execute=AsyncMock(return_value=result))

    monkeypatch.setattr(
        sessions_router,
        "AsyncSessionLocal",
        lambda: _DatabaseContext(database),
    )
    readiness = AsyncMock(
        return_value=[
            {
                "session_key": 9896,
                "telemetry_drivers_ready": 20,
            }
        ]
    )
    monkeypatch.setattr(sessions_router.workspace_repository, "list", readiness)

    response = await sessions_router.list_sessions()

    database.execute.assert_awaited_once()
    readiness.assert_awaited_once_with("preparation", 1000)
    assert response == {
        "sessions": [
            {
                "session_key": 9896,
                "meeting_key": 1270,
                "year": 2025,
                "country": "Singapore",
                "session_name": "Race",
                "meeting_name": "Singapore Grand Prix",
                "date_start": "2025-10-05T12:00:00+00:00",
                "telemetry_available": True,
                "label": "2025 · Singapore · Race",
            }
        ]
    }

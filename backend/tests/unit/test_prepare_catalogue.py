from argparse import Namespace
from datetime import UTC, datetime

import pytest

from scripts import prepare_catalogue


def test_recent_session_must_be_finished_and_outside_delay():
    args = Namespace(recent_days=30, completion_delay_minutes=120)
    now = datetime(2026, 10, 5, 12, tzinfo=UTC)

    assert prepare_catalogue.is_due(
        {"date_end": "2026-10-05T09:00:00+00:00"}, now, args
    )
    assert not prepare_catalogue.is_due(
        {"date_end": "2026-10-05T11:00:00+00:00"}, now, args
    )
    assert not prepare_catalogue.is_due(
        {"date_end": "2026-08-01T12:00:00+00:00"}, now, args
    )


@pytest.mark.asyncio
async def test_complete_cloud_manifest_is_detected(monkeypatch):
    class Store:
        async def exists(self, key):
            return key == "manifests/42.json"

        async def read_json(self, key):
            return {"complete": True}

        async def evict_local(self, key):
            return None

    monkeypatch.setattr(prepare_catalogue, "object_store", Store())

    assert await prepare_catalogue.has_complete_manifest(42)
    assert not await prepare_catalogue.has_complete_manifest(43)

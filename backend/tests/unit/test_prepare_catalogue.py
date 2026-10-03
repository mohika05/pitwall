from argparse import Namespace
from datetime import UTC, datetime

import httpx
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


@pytest.mark.asyncio
async def test_catalog_request_retries_transient_failure(monkeypatch):
    attempts = 0
    delays = []

    async def handler(request):
        nonlocal attempts
        attempts += 1
        status = 502 if attempts == 1 else 200
        return httpx.Response(status, request=request, json={"meetings": []})

    async def record_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(prepare_catalogue.asyncio, "sleep", record_sleep)
    async with httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    ) as client:
        response = await prepare_catalogue.get_catalog_response(
            client, "/catalog/2026", 2
        )

    assert response.status_code == 200
    assert attempts == 2
    assert delays == [10]


@pytest.mark.asyncio
async def test_catalog_request_does_not_retry_permanent_failure(monkeypatch):
    attempts = 0

    async def handler(request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(400, request=request, json={"detail": "bad year"})

    async def fail_if_sleeping(_delay):
        pytest.fail("Permanent client errors must not be retried")

    monkeypatch.setattr(prepare_catalogue.asyncio, "sleep", fail_if_sleeping)
    async with httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await prepare_catalogue.get_catalog_response(
                client, "/catalog/2026", 2
            )

    assert attempts == 1

"""Exercise the actual HTTP serialization used by telemetry ingestion."""

from unittest.mock import AsyncMock
from urllib.parse import unquote

import httpx
import pytest

from app.core.exceptions import ExternalDataError
from app.ingestion.providers import openf1


@pytest.mark.parametrize("endpoint", ["car_data", "location"])
async def test_filters_reach_server_with_exact_operators(monkeypatch, endpoint):
    monkeypatch.setattr(openf1, "request_slot", AsyncMock())

    def handler(request):
        expressions = unquote(request.url.query.decode()).split("&")
        assert expressions == [
            "session_key=11388",
            "driver_number=3",
            "date>=2026-10-11T12:00:00+00:00",
            "date<2026-10-11T12:15:00+00:00",
            "speed<=300",
            "rpm>0",
            "team_name=Red Bull Racing",
        ]
        assert "%2B" in request.url.query.decode()
        return httpx.Response(200, json=[{"speed": 250}])

    provider = object.__new__(openf1.OpenF1Provider)
    async with httpx.AsyncClient(
        base_url="https://example.test/", transport=httpx.MockTransport(handler)
    ) as client:
        provider.client = client
        rows = await provider._get(
            endpoint,
            {
                "session_key": 11388,
                "driver_number": 3,
                "date>=": "2026-10-11T12:00:00+00:00",
                "date<": "2026-10-11T12:15:00+00:00",
                "speed<=": 300,
                "rpm>": 0,
                "team_name": "Red Bull Racing",
            },
        )
    assert rows == [{"speed": 250}]


@pytest.mark.parametrize("failure", [503, 429, "timeout", 401])
async def test_errors_preserve_cause_and_retry_only_transient_failures(monkeypatch, failure):
    monkeypatch.setattr(openf1, "request_slot", AsyncMock())
    monkeypatch.setattr(openf1.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(openf1.settings, "openf1_max_retries", 2)
    calls = []

    def handler(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("upstream timed out", request=request)
        return httpx.Response(failure, json={"error": "unavailable"})

    provider = object.__new__(openf1.OpenF1Provider)
    async with httpx.AsyncClient(
        base_url="https://example.test/", transport=httpx.MockTransport(handler)
    ) as client:
        provider.client = client
        with pytest.raises(ExternalDataError) as caught:
            await provider._get("car_data", {"session_key": 11388})
    assert len(calls) == (1 if failure == 401 else 2)
    if failure == "timeout":
        assert "ReadTimeout" in str(caught.value)
    else:
        assert str(failure) in str(caught.value) or failure == 429
        assert caught.value.status_code == failure


@pytest.mark.parametrize("channel", ["car", "position"])
async def test_chunk_export_skips_empty_windows_and_keeps_boundary_samples(
    monkeypatch, tmp_path, channel
):
    from datetime import UTC, datetime, timedelta

    import pandas as pd

    monkeypatch.setattr(openf1, "request_slot", AsyncMock())
    monkeypatch.setattr(
        openf1.OpenF1Provider,
        "_telemetry_path",
        staticmethod(lambda *_: tmp_path / "driver.parquet"),
    )
    start = datetime(2026, 10, 10, 13, tzinfo=UTC)
    calls = []

    def handler(request):
        expressions = unquote(request.url.query.decode())
        calls.append(expressions)
        if len(calls) == 1:
            return httpx.Response(404, json={"detail": "No results found."})
        assert f"date>={(start + timedelta(minutes=15)).isoformat()}" in expressions
        sample = {
            "date": (start + timedelta(minutes=15)).isoformat(),
            "speed": 250,
            "rpm": 11000,
            "x": 100,
            "y": 200,
        }
        return httpx.Response(200, json=[sample, sample])

    provider = object.__new__(openf1.OpenF1Provider)
    async with httpx.AsyncClient(
        base_url="https://example.test/", transport=httpx.MockTransport(handler)
    ) as client:
        provider.client = client
        export = await provider._export_driver_channel_chunked(
            11384,
            "VER",
            3,
            channel,
            start,
            start + timedelta(minutes=30),
            {3: ([start], [1])},
        )
    assert export.rows == 1
    frame = pd.read_parquet(export.path)
    assert frame["Date"].tolist() == [start + timedelta(minutes=15)]
    assert frame["LapNumber"].tolist() == [1]


@pytest.mark.parametrize(
    "status,body",
    [
        (404, {"detail": "Not Found"}),
        (401, {"detail": "Unauthorized"}),
    ],
)
async def test_real_provider_errors_never_publish_partial_file(monkeypatch, tmp_path, status, body):
    from datetime import UTC, datetime, timedelta

    monkeypatch.setattr(openf1, "request_slot", AsyncMock())
    path = tmp_path / "driver.parquet"
    path.write_bytes(b"previous complete file")
    monkeypatch.setattr(openf1.OpenF1Provider, "_telemetry_path", staticmethod(lambda *_: path))
    provider = object.__new__(openf1.OpenF1Provider)
    start = datetime(2026, 10, 10, 13, tzinfo=UTC)
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json=[{"date": start.isoformat(), "speed": 250}])
        return httpx.Response(status, json=body)

    async with httpx.AsyncClient(
        base_url="https://example.test/", transport=httpx.MockTransport(handler)
    ) as client:
        provider.client = client
        with pytest.raises(ExternalDataError, match="driver VER"):
            await provider._export_driver_channel_chunked(
                11384,
                "VER",
                3,
                "car",
                start,
                start + timedelta(minutes=30),
                {3: ([start], [1])},
            )
    assert path.read_bytes() == b"previous complete file"

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.storage.object_store import LocalObjectStore, S3ObjectStore, _safe_key


@pytest.mark.asyncio
async def test_local_store_publishes_and_materializes_verified_file(tmp_path: Path):
    source = tmp_path / "source.parquet"
    source.write_bytes(b"pitwall telemetry")
    store = LocalObjectStore(tmp_path / "objects")

    result = await store.publish(source, "telemetry/1/NOR_car.parquet")
    materialized = await store.materialize("telemetry/1/NOR_car.parquet")

    assert materialized.read_bytes() == b"pitwall telemetry"
    assert result["bytes"] == len(b"pitwall telemetry")
    assert len(result["sha256"]) == 64

    await store.evict_local("telemetry/1/NOR_car.parquet")
    assert await store.exists("telemetry/1/NOR_car.parquet")


def test_storage_keys_cannot_escape_storage_root():
    with pytest.raises(ValueError):
        _safe_key("../secrets")


@pytest.mark.asyncio
async def test_s3_store_verifies_upload_and_materializes_to_cache(tmp_path: Path):
    objects: dict[str, tuple[bytes, dict]] = {}

    class FakeS3:
        def upload_file(self, source, bucket, key, ExtraArgs):
            assert bucket == "pitwall"
            objects[key] = (Path(source).read_bytes(), ExtraArgs["Metadata"])

        def head_object(self, *, Bucket, Key):
            assert Bucket == "pitwall"
            body, metadata = objects[Key]
            return {"ContentLength": len(body), "Metadata": metadata}

        def download_file(self, bucket, key, destination):
            assert bucket == "pitwall"
            Path(destination).write_bytes(objects[key][0])

        def delete_object(self, *, Bucket, Key):
            assert Bucket == "pitwall"
            objects.pop(Key, None)

    store = S3ObjectStore(
        bucket="pitwall",
        cache_dir=tmp_path / "cache",
        prefix="demo",
        endpoint_url="http://127.0.0.1:1",
        access_key_id="test",
        secret_access_key="test",
    )
    store.client = FakeS3()
    source = tmp_path / "source.parquet"
    source.write_bytes(b"remote telemetry")

    result = await store.publish(source, "telemetry/1/NOR_car.parquet")
    materialized = await store.materialize("telemetry/1/NOR_car.parquet")

    assert result["sha256"] == objects["demo/telemetry/1/NOR_car.parquet"][1]["sha256"]
    assert materialized.read_bytes() == b"remote telemetry"

    await store.evict_local("telemetry/1/NOR_car.parquet")
    assert not materialized.exists()
    assert "demo/telemetry/1/NOR_car.parquet" in objects

    await store.delete("telemetry/1/NOR_car.parquet")
    assert "demo/telemetry/1/NOR_car.parquet" not in objects


@pytest.mark.asyncio
async def test_s3_uploads_keep_the_local_cache_bounded(tmp_path: Path):
    objects: dict[str, tuple[bytes, dict]] = {}

    class FakeS3:
        def upload_file(self, source, _bucket, key, ExtraArgs):
            objects[key] = (Path(source).read_bytes(), ExtraArgs["Metadata"])

        def head_object(self, *, Bucket, Key):
            body, metadata = objects[Key]
            return {"ContentLength": len(body), "Metadata": metadata}

    cache = tmp_path / "cache"
    store = S3ObjectStore(
        bucket="pitwall",
        cache_dir=cache,
        prefix="demo",
        access_key_id="test",
        secret_access_key="test",
        cache_max_bytes=20,
    )
    store.client = FakeS3()
    first = cache / "telemetry/1/NOR_car.parquet"
    second = cache / "telemetry/1/VER_car.parquet"
    first.parent.mkdir(parents=True)
    first.write_bytes(b"a" * 15)
    await store.publish(first, "telemetry/1/NOR_car.parquet")
    second.write_bytes(b"b" * 15)
    await store.publish(second, "telemetry/1/VER_car.parquet")

    assert not first.exists()
    assert second.exists()
    assert sum(path.stat().st_size for path in cache.rglob("*") if path.is_file()) <= 20


@pytest.mark.asyncio
async def test_partial_manifest_exposes_verified_drivers(monkeypatch, tmp_path: Path):
    from app.services import telemetry as telemetry_module

    store = LocalObjectStore(tmp_path)
    await store.write_json(
        "manifests/7774.json",
        {"complete": False, "drivers": ["VER", "PER"]},
    )
    monkeypatch.setattr(telemetry_module, "object_store", store)

    drivers = await telemetry_module.telemetry_service.available_drivers(7774)

    assert drivers == ["VER", "PER"]


@pytest.mark.asyncio
async def test_event_repository_falls_back_to_compressed_object(monkeypatch, tmp_path: Path):
    from app.persistence.repositories import event_repository as repository_module

    class EmptyResult:
        def scalars(self):
            return SimpleNamespace(all=list)

    class EmptySession:
        async def execute(self, _statement):
            return EmptyResult()

    store = LocalObjectStore(tmp_path)
    monkeypatch.setattr(repository_module, "object_store", store)
    path = store.local_path("processed/7_events.json.gz")
    path.parent.mkdir(parents=True)
    payload = [
        {
            "event_id": "event-1",
            "meeting_key": 2,
            "session_key": 7,
            "event_type": "lap_completed",
            "timestamp": datetime(2025, 1, 1, tzinfo=UTC).isoformat(),
            "driver_number": 4,
            "lap_number": 1,
            "payload": {"lap_duration": 90.0},
        }
    ]
    with gzip.open(path, "wt", encoding="utf-8") as destination:
        json.dump(payload, destination)

    events = await repository_module.EventRepository(EmptySession()).get_for_session(7)

    assert len(events) == 1
    assert events[0].event_id == "event-1"

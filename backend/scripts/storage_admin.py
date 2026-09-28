"""Index existing local telemetry and optionally remove disposable FastF1 data."""

import argparse
import asyncio
import gzip
import shutil
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings
from app.storage.object_store import (
    manifest_key,
    object_store,
    processed_events_key,
)


async def index_session(directory: Path) -> dict:
    session_key = int(directory.name)
    cars = {path.stem.removesuffix("_car") for path in directory.glob("*_car.parquet")}
    positions = {
        path.stem.removesuffix("_position")
        for path in directory.glob("*_position.parquet")
    }
    drivers = sorted(cars & positions)
    files = []
    for driver in drivers:
        for kind in ("car", "position"):
            source = directory / f"{driver}_{kind}.parquet"
            files.append(
                await object_store.publish(
                    source, f"telemetry/{session_key}/{source.name}"
                )
            )
    legacy_events = settings.data_dir / "processed" / f"{session_key}_events.json"
    if legacy_events.is_file():
        compressed = object_store.local_path(processed_events_key(session_key))
        compressed.parent.mkdir(parents=True, exist_ok=True)
        with legacy_events.open("rb") as source, gzip.open(
            compressed, "wb", compresslevel=6
        ) as destination:
            shutil.copyfileobj(source, destination)
        files.append(
            await object_store.publish(compressed, processed_events_key(session_key))
        )
    manifest = {
        "version": 1,
        "session_key": session_key,
        "created_at": datetime.now(UTC).isoformat(),
        "complete": bool(drivers),
        "drivers": drivers,
        "files": files,
        "total_bytes": sum(item["bytes"] for item in files),
    }
    await object_store.write_json(manifest_key(session_key), manifest)
    return manifest


async def run(prune_cache: bool) -> None:
    telemetry_root = settings.telemetry_dir
    manifests = []
    for directory in sorted(telemetry_root.iterdir() if telemetry_root.is_dir() else []):
        if directory.is_dir() and directory.name.isdigit():
            manifest = await index_session(directory)
            manifests.append(manifest)
            print(
                f"Indexed {manifest['session_key']}: {len(manifest['drivers'])} drivers, "
                f"{manifest['total_bytes'] / 1024 / 1024:.1f} MiB"
            )
    print(
        f"Indexed {len(manifests)} sessions, "
        f"{sum(item['total_bytes'] for item in manifests) / 1024 / 1024:.1f} MiB total"
    )
    if prune_cache:
        removed = 0
        for year in settings.fastf1_cache_dir.iterdir():
            if not year.is_dir() or not year.name.isdigit():
                continue
            for event in year.iterdir():
                if event.is_dir():
                    removed += sum(
                        path.stat().st_size for path in event.rglob("*") if path.is_file()
                    )
                    shutil.rmtree(event)
            if not any(year.iterdir()):
                year.rmdir()
        request_cache = settings.fastf1_cache_dir / "fastf1_http_cache.sqlite"
        if request_cache.is_file():
            removed += request_cache.stat().st_size
            request_cache.unlink()
        print(f"Removed {removed / 1024 / 1024:.1f} MiB of disposable FastF1 cache")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prune-fastf1-cache",
        action="store_true",
        help="Delete decoded provider files after every local session is indexed",
    )
    args = parser.parse_args()
    asyncio.run(run(args.prune_fastf1_cache))


if __name__ == "__main__":
    main()

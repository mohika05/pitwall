"""Verify cloud object storage, database access, and local ingestion headroom."""

import argparse
import asyncio
import shutil
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text

from app.core.config import REPO_ROOT, settings


def require_cloud_storage() -> None:
    required = {
        "S3_BUCKET": settings.s3_bucket,
        "S3_ENDPOINT_URL": settings.s3_endpoint_url,
        "S3_ACCESS_KEY_ID": settings.s3_access_key_id,
        "S3_SECRET_ACCESS_KEY": settings.s3_secret_access_key,
    }
    missing = [name for name, value in required.items() if not value]
    if settings.storage_backend.lower() != "s3":
        missing.insert(0, "STORAGE_BACKEND=s3")
    if missing:
        raise RuntimeError("Cloud storage is not configured: " + ", ".join(missing))


async def storage_check() -> tuple[int, int, int]:
    require_cloud_storage()
    from app.storage.object_store import S3ObjectStore, object_store

    if not isinstance(object_store, S3ObjectStore):
        raise TypeError("The configured object store is not S3-compatible")
    check_id = str(uuid4())
    key = f"_checks/{check_id}.json"
    payload = {"check_id": check_id, "created_at": datetime.now(UTC).isoformat()}
    try:
        published = await object_store.write_json(key, payload)
        object_store.local_path(key).unlink(missing_ok=True)
        downloaded = await object_store.read_json(key)
        if downloaded != payload:
            raise OSError("Cloud storage round-trip returned different content")
        print(
            f"Object round-trip verified: {published['bytes']} bytes, "
            f"SHA-256 {published['sha256'][:12]}…"
        )
    finally:
        await object_store.delete(key)

    def inventory() -> tuple[int, int, int]:
        prefix = f"{object_store.prefix}/" if object_store.prefix else ""
        paginator = object_store.client.get_paginator("list_objects_v2")
        objects = [
            item
            for page in paginator.paginate(Bucket=object_store.bucket, Prefix=prefix)
            for item in page.get("Contents", [])
            if "/_checks/" not in item["Key"] and not item["Key"].startswith("_checks/")
        ]
        manifests = sum(
            item["Key"].removeprefix(prefix).startswith("manifests/")
            and item["Key"].endswith(".json")
            for item in objects
        )
        return len(objects), sum(int(item["Size"]) for item in objects), manifests

    count, total, manifests = await asyncio.to_thread(inventory)
    print(
        f"Bucket inventory: {count} objects, {total / 1_000_000_000:.3f} GB, "
        f"{manifests} completed-session manifests"
    )
    return count, total, manifests


async def database_check(allow_local: bool) -> int:
    if not allow_local and any(
        host in settings.database_url for host in ("@localhost", "@127.0.0.1", "@postgres:")
    ):
        raise RuntimeError(
            "DATABASE_URL still points to a local database; configure the cloud database "
            "or pass --allow-local-database for a storage-only rehearsal"
        )
    from app.persistence.database import engine

    async with engine.connect() as connection:
        size = int(await connection.scalar(text("SELECT pg_database_size(current_database())")))
        await connection.execute(text("SELECT 1"))
    await engine.dispose()
    print(f"PostgreSQL connection verified; current database size is {size / 1_000_000:.1f} MB")
    return size


async def run(args: argparse.Namespace) -> None:
    _, total, manifests = await storage_check()
    if not args.storage_only:
        await database_check(args.allow_local_database)
    free = shutil.disk_usage(REPO_ROOT).free
    print(
        f"Local free disk: {free / 1_000_000_000:.2f} GB; "
        f"object cache limit: {settings.storage_cache_max_bytes / 1_000_000_000:.2f} GB"
    )
    if free < args.min_free_gb * 1_000_000_000:
        raise RuntimeError(f"Local disk is below the {args.min_free_gb:.2f} GB safety floor")
    if total > args.max_storage_gb * 1_000_000_000:
        raise RuntimeError(
            f"Remote objects already exceed the {args.max_storage_gb:.2f} GB storage budget"
        )
    print(
        f"CLOUD PREFLIGHT PASSED · {manifests} sessions ready · "
        f"{args.max_storage_gb - total / 1_000_000_000:.3f} GB budget remaining"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage-only", action="store_true")
    parser.add_argument("--allow-local-database", action="store_true")
    parser.add_argument("--min-free-gb", type=float, default=3.0)
    parser.add_argument("--max-storage-gb", type=float, default=9.5)
    try:
        asyncio.run(run(parser.parse_args()))
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise SystemExit(f"CLOUD PREFLIGHT FAILED · {exc}") from None


if __name__ == "__main__":
    main()

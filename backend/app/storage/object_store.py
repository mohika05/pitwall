import asyncio
import hashlib
import json
import os
import shutil
import threading
from abc import ABC, abstractmethod
from pathlib import Path, PurePosixPath
from typing import Any

from app.core.config import settings


def _safe_key(key: str) -> str:
    path = PurePosixPath(key)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"Unsafe storage key: {key}")
    return str(path)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ObjectStore(ABC):
    @abstractmethod
    def local_path(self, key: str) -> Path:
        raise NotImplementedError

    @abstractmethod
    async def publish(self, source: Path, key: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def materialize(self, key: str) -> Path:
        raise NotImplementedError

    @abstractmethod
    async def exists(self, key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, key: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def evict_local(self, key: str) -> None:
        """Remove a disposable local cache entry without deleting remote data."""
        raise NotImplementedError

    async def read_json(self, key: str) -> dict[str, Any]:
        path = await self.materialize(key)
        return await asyncio.to_thread(json.loads, path.read_text())

    async def write_json(self, key: str, payload: dict[str, Any]) -> dict[str, Any]:
        destination = self.local_path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True))
        temporary.replace(destination)
        return await self.publish(destination, key)


class LocalObjectStore(ObjectStore):
    def __init__(self, root: Path):
        self.root = root

    def local_path(self, key: str) -> Path:
        return self.root / _safe_key(key)

    async def publish(self, source: Path, key: str) -> dict[str, Any]:
        destination = self.local_path(key)
        if source.resolve() != destination.resolve():
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(destination.suffix + ".tmp")
            await asyncio.to_thread(shutil.copy2, source, temporary)
            temporary.replace(destination)
        return {
            "key": _safe_key(key),
            "bytes": destination.stat().st_size,
            "sha256": await asyncio.to_thread(file_sha256, destination),
        }

    async def materialize(self, key: str) -> Path:
        path = self.local_path(key)
        if not path.is_file():
            raise FileNotFoundError(f"Stored object not found: {_safe_key(key)}")
        return path

    async def exists(self, key: str) -> bool:
        return self.local_path(key).is_file()

    async def delete(self, key: str) -> None:
        self.local_path(key).unlink(missing_ok=True)

    async def evict_local(self, key: str) -> None:
        # Local storage is canonical, so it must never be evicted as cache.
        return None


class S3ObjectStore(ObjectStore):
    def __init__(
        self,
        *,
        bucket: str,
        cache_dir: Path,
        prefix: str = "",
        endpoint_url: str | None = None,
        region: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        cache_max_bytes: int = 2 * 1024 * 1024 * 1024,
    ):
        try:
            import boto3
            from botocore.exceptions import ClientError
        except ImportError as exc:  # pragma: no cover - configuration failure
            raise RuntimeError("S3 storage requires the boto3 dependency") from exc
        self.bucket = bucket
        self.cache_dir = cache_dir
        self.prefix = prefix.strip("/")
        self.cache_max_bytes = cache_max_bytes
        self._client_error = ClientError
        self._cache_lock = threading.Lock()
        self._download_locks: dict[str, asyncio.Lock] = {}
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )

    def _remote_key(self, key: str) -> str:
        safe = _safe_key(key)
        return f"{self.prefix}/{safe}" if self.prefix else safe

    def local_path(self, key: str) -> Path:
        return self.cache_dir / _safe_key(key)

    async def publish(self, source: Path, key: str) -> dict[str, Any]:
        safe = _safe_key(key)
        size = source.stat().st_size
        checksum = await asyncio.to_thread(file_sha256, source)
        await asyncio.to_thread(
            self.client.upload_file,
            str(source),
            self.bucket,
            self._remote_key(safe),
            ExtraArgs={"Metadata": {"sha256": checksum}},
        )
        metadata = await asyncio.to_thread(
            self.client.head_object,
            Bucket=self.bucket,
            Key=self._remote_key(safe),
        )
        if (
            int(metadata["ContentLength"]) != size
            or metadata.get("Metadata", {}).get("sha256") != checksum
        ):
            raise OSError(f"Object verification failed for {safe}")
        await asyncio.to_thread(self._trim_cache, source)
        return {"key": safe, "bytes": size, "sha256": checksum}

    async def materialize(self, key: str) -> Path:
        safe = _safe_key(key)
        destination = self.local_path(safe)
        lock = self._download_locks.setdefault(safe, asyncio.Lock())
        async with lock:
            if not destination.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_suffix(destination.suffix + ".download")
                try:
                    try:
                        await asyncio.to_thread(
                            self.client.download_file,
                            self.bucket,
                            self._remote_key(safe),
                            str(temporary),
                        )
                    except self._client_error as exc:
                        status = exc.response.get("ResponseMetadata", {}).get(
                            "HTTPStatusCode"
                        )
                        if status == 404:
                            raise FileNotFoundError(
                                f"Stored object not found: {safe}"
                            ) from exc
                        raise
                    temporary.replace(destination)
                finally:
                    temporary.unlink(missing_ok=True)
        os.utime(destination, None)
        await asyncio.to_thread(self._trim_cache, destination)
        return destination

    async def exists(self, key: str) -> bool:
        try:
            await asyncio.to_thread(
                self.client.head_object,
                Bucket=self.bucket,
                Key=self._remote_key(key),
            )
            return True
        except self._client_error as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status == 404:
                return False
            raise

    async def delete(self, key: str) -> None:
        safe = _safe_key(key)
        await asyncio.to_thread(
            self.client.delete_object,
            Bucket=self.bucket,
            Key=self._remote_key(safe),
        )
        self.local_path(safe).unlink(missing_ok=True)

    async def evict_local(self, key: str) -> None:
        self.local_path(_safe_key(key)).unlink(missing_ok=True)

    def _trim_cache(self, preserve: Path) -> None:
        with self._cache_lock:
            files = [
                path
                for path in self.cache_dir.rglob("*")
                if path.is_file() and not path.name.endswith((".download", ".tmp"))
            ]
            total = sum(path.stat().st_size for path in files)
            for path in sorted(files, key=lambda item: item.stat().st_mtime):
                if total <= self.cache_max_bytes:
                    break
                if path == preserve:
                    continue
                size = path.stat().st_size
                path.unlink(missing_ok=True)
                total -= size


def build_object_store() -> ObjectStore:
    backend = settings.storage_backend.lower().strip()
    if backend == "local":
        return LocalObjectStore(settings.data_dir)
    if backend != "s3":
        raise ValueError("STORAGE_BACKEND must be 'local' or 's3'")
    if not settings.s3_bucket:
        raise ValueError("S3_BUCKET is required when STORAGE_BACKEND=s3")
    return S3ObjectStore(
        bucket=settings.s3_bucket,
        cache_dir=settings.storage_cache_dir,
        prefix=settings.s3_prefix,
        endpoint_url=settings.s3_endpoint_url,
        region=settings.s3_region,
        access_key_id=settings.s3_access_key_id,
        secret_access_key=settings.s3_secret_access_key,
        cache_max_bytes=settings.storage_cache_max_bytes,
    )


object_store = build_object_store()


def telemetry_key(session_key: int, driver: str, kind: str) -> str:
    safe_driver = driver.upper().replace("/", "_")
    return f"telemetry/{session_key}/{safe_driver}_{kind}.parquet"


def manifest_key(session_key: int) -> str:
    return f"manifests/{session_key}.json"


def processed_events_key(session_key: int) -> str:
    return f"processed/{session_key}_events.json.gz"

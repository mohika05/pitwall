"""Single-process, durable session preparation jobs with bounded concurrency."""

import asyncio
import logging
from datetime import UTC, datetime

import pandas as pd

from app.core.config import settings
from app.ingestion.providers.fastf1 import FastF1TelemetryProvider
from app.ingestion.providers.openf1 import OpenF1Provider
from app.ingestion.service import IngestionService
from app.persistence.database import AsyncSessionLocal
from app.persistence.repositories.event_repository import EventRepository
from app.persistence.repositories.ingestion_repository import IngestionRepository
from app.persistence.repositories.workspace_repository import workspace_repository as records
from app.services.telemetry import clear_telemetry_cache
from app.storage.object_store import manifest_key, object_store

logger = logging.getLogger(__name__)
ACTIVE = {"queued", "preparing"}


def drivers_with_fastf1_laps(loaded, requested: list[str]) -> tuple[list[str], list[str]]:
    """Split requested drivers by whether FastF1 recorded at least one lap."""
    if "Driver" not in loaded.laps.columns:
        return requested, []
    recorded = {
        str(driver).upper()
        for driver in loaded.laps["Driver"].dropna().unique()
        if str(driver).strip()
    }
    available = [driver for driver in requested if driver.upper() in recorded]
    unavailable = [driver for driver in requested if driver.upper() not in recorded]
    return available, unavailable


class PreparationService:
    def __init__(self):
        self.tasks: dict[int, asyncio.Task] = {}
        self.lock = asyncio.Lock()
        self.worker = asyncio.Semaphore(1)

    async def start(self, session_key: int, telemetry: bool = True) -> dict:
        async with self.lock:
            existing = await records.get("preparation", str(session_key))
            if session_key in self.tasks and not self.tasks[session_key].done():
                return existing
            job = {
                "session_key": session_key,
                "state": "queued",
                "progress": 0,
                "message": "Waiting for preparation worker",
                "telemetry_requested": telemetry,
                "events_ready": False,
                "telemetry_ready": False,
                "errors": [],
            }
            await self.save(job)
            self.tasks[session_key] = asyncio.create_task(self.run(job))
            return job

    async def save(self, job: dict):
        job["updated_at"] = datetime.now(UTC).isoformat()
        await records.put("preparation", str(job["session_key"]), dict(job))

    async def run(self, job: dict):
        fast = None
        loaded = None
        stored_files: list[dict] = []
        try:
            async with self.worker:
                key = job["session_key"]
                job.update(
                    state="preparing", progress=5, message="Downloading timing and race history"
                )
                await self.save(job)
                async with OpenF1Provider() as provider:
                    session = await provider.get_session(key)
                    start = datetime.fromisoformat(session["date_start"])
                    if start > datetime.now(UTC):
                        raise ValueError("This session has not started yet")
                    bundle = await provider.fetch_bundle(session)
                service = IngestionService(provider)
                context, events = service.normalize(bundle)
                if not events:
                    raise ValueError("No replayable events are available yet")
                async with AsyncSessionLocal() as db, db.begin():
                    await IngestionRepository(db).persist_bundle(bundle)
                    if settings.persist_historical_events_in_database:
                        await EventRepository(db).upsert_many(events)
                stored_files = [await service.save_processed_events(key, events)]
                job.update(events_ready=True, progress=40, message="Timing ready")
                await self.save(job)
                if job["telemetry_requested"]:
                    fast = FastF1TelemetryProvider()
                    loaded = await fast.load_session(
                        context.session.year,
                        bundle.meeting.get("meeting_name") or context.session.country_name,
                        context.session.session_name,
                        telemetry=False,
                    )
                    # Preserve provider qualifying segments and official stage results.
                    enrichment = {"qualifying": [], "lap_stages": {}}
                    if (
                        "qualifying" in context.session.session_name.lower()
                        or "shootout" in context.session.session_name.lower()
                    ):
                        for _, row in loaded.results.iterrows():
                            enrichment["qualifying"].append(
                                {
                                    "driver_number": int(row["DriverNumber"]),
                                    **{
                                        stage: None
                                        if pd.isna(row.get(stage))
                                        else row[stage].total_seconds()
                                        for stage in ("Q1", "Q2", "Q3")
                                    },
                                    "position": None
                                    if pd.isna(row.get("Position"))
                                    else int(row["Position"]),
                                }
                            )
                        for index, laps in enumerate(loaded.laps.split_qualifying_sessions(), 1):
                            if laps is not None:
                                for _, row in laps.iterrows():
                                    enrichment["lap_stages"][
                                        f"{int(row['DriverNumber'])}:{int(row['LapNumber'])}"
                                    ] = f"Q{index}"
                    await records.put("session_enrichment", str(key), enrichment)
                    requested_drivers = [
                        driver.name_acronym for driver in context.drivers if driver.name_acronym
                    ]
                    drivers, unavailable_drivers = drivers_with_fastf1_laps(
                        loaded, requested_drivers
                    )
                    job["telemetry_unavailable_drivers"] = unavailable_drivers
                    if unavailable_drivers:
                        logger.info(
                            "Skipping drivers without recorded FastF1 laps for session %s: %s",
                            key,
                            ", ".join(unavailable_drivers),
                        )
                    if not drivers:
                        raise ValueError("FastF1 returned no laps for any session driver")
                    completed_channels = {driver: set() for driver in drivers}
                    channel_ranges = {
                        "car": (40, 27, "Car telemetry"),
                        "position": (67, 28, "Position telemetry"),
                    }
                    for channel, (base, span, label) in channel_ranges.items():
                        job.update(progress=base, message=f"Decoding {label.lower()}")
                        await self.save(job)
                        exports, objects = await fast.export_channel_streaming(
                            key, loaded, drivers, channel
                        )
                        stored_files.extend(objects)
                        exported_drivers = {exported.driver for exported in exports}
                        for driver in exported_drivers:
                            completed_channels[driver].add(channel)
                        unavailable_drivers.extend(
                            driver for driver in drivers if driver not in exported_drivers
                        )
                        job["telemetry_unavailable_drivers"] = sorted(
                            set(unavailable_drivers)
                        )
                        job.update(
                            progress=base + span,
                            message=f"{label} ready for {len(exported_drivers)}/{len(drivers)} drivers",
                        )
                        await self.save(job)

                    telemetry_drivers = [
                        driver
                        for driver, channels in completed_channels.items()
                        if channels == {"car", "position"}
                    ]
                    succeeded = len(telemetry_drivers)
                    if succeeded == 0:
                        raise ValueError(
                            "FastF1 produced no usable telemetry for any session driver"
                        )
                    clear_telemetry_cache()
                    job["telemetry_ready"] = not job["errors"]
                    job["telemetry_drivers_ready"] = succeeded
                    manifest = {
                        "version": 1,
                        "session_key": key,
                        "created_at": datetime.now(UTC).isoformat(),
                        "complete": job["telemetry_ready"],
                        "drivers": telemetry_drivers,
                        "files": stored_files,
                        "total_bytes": sum(item["bytes"] for item in stored_files),
                    }
                    await object_store.write_json(manifest_key(key), manifest)
                    job["stored_bytes"] = manifest["total_bytes"]
                job.update(
                    state="ready" if not job["errors"] else "partial",
                    progress=100,
                    message="Session ready"
                    if not job["errors"]
                    else "Timing ready; some telemetry is missing",
                )
        except asyncio.CancelledError:
            job.update(state="interrupted", message="Preparation interrupted; retry to resume")
            raise
        except Exception as exc:
            logger.exception("Session preparation failed")
            job.update(
                state="partial" if job["events_ready"] else "failed",
                message=str(exc),
                errors=[*job["errors"], type(exc).__name__],
            )
        finally:
            if settings.fastf1_cleanup_after_prepare and fast is not None and loaded is not None:
                try:
                    job["fastf1_cache_bytes_removed"] = await asyncio.shield(
                        fast.cleanup_session_cache(loaded)
                    )
                except Exception as exc:
                    logger.exception("FastF1 cache cleanup failed")
                    job["errors"].append(f"cache cleanup: {type(exc).__name__}")
            if job.get("state") == "ready" and settings.storage_backend == "s3":
                for stored in stored_files:
                    await object_store.evict_local(stored["key"])
                await object_store.evict_local(manifest_key(job["session_key"]))
            await self.save(job)

    async def recover(self):
        for job in await records.list("preparation", 1000):
            if job["state"] in ACTIVE:
                job.update(state="interrupted", message="Server restarted; retry preparation")
                await self.save(job)

    async def close(self):
        for task in self.tasks.values():
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)


preparation_service = PreparationService()

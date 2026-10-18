"""Single-process, durable session preparation jobs with bounded concurrency."""

import asyncio
import logging
from bisect import bisect_right
from datetime import UTC, datetime

import pandas as pd

from app.core.config import settings
from app.core.exceptions import ExternalDataError
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


def drivers_with_openf1_laps(bundle, requested: list[str]) -> tuple[list[str], list[str]]:
    number_by_driver = {
        str(row.get("name_acronym") or "").upper(): int(row["driver_number"])
        for row in bundle.drivers
        if row.get("name_acronym") and row.get("driver_number") is not None
    }
    recorded = {
        int(row["driver_number"])
        for row in bundle.laps
        if row.get("driver_number") is not None and row.get("date_start")
    }
    available = [
        driver
        for driver in requested
        if number_by_driver.get(driver.upper()) in recorded
    ]
    unavailable = [driver for driver in requested if driver not in available]
    return available, unavailable


def openf1_enrichment(bundle, session_name: str) -> dict:
    """Build qualifying results and lap-stage labels from OpenF1 resources."""
    enrichment: dict = {"qualifying": [], "lap_stages": {}}
    name = session_name.casefold()
    if "qualifying" not in name and "shootout" not in name:
        return enrichment

    def numeric_or_none(value):
        """OpenF1 may use result markers such as RT, DNS, or DNF."""
        if value is None or isinstance(value, bool):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def integer_or_none(value):
        numeric = numeric_or_none(value)
        return None if numeric is None else int(numeric)

    for row in bundle.session_result:
        number = row.get("driver_number")
        if number is None:
            continue
        duration = row.get("duration")
        stages = duration if isinstance(duration, list) else [duration]
        enrichment["qualifying"].append(
            {
                "driver_number": int(number),
                **{
                    f"Q{index}": (
                        None
                        if index > len(stages)
                        else numeric_or_none(stages[index - 1])
                    )
                    for index in (1, 2, 3)
                },
                "position": integer_or_none(row.get("position")),
            }
        )

    phase_markers: list[tuple[datetime, str]] = []
    for row in bundle.race_control:
        phase = row.get("qualifying_phase")
        date = row.get("date")
        if phase not in (1, 2, 3, "1", "2", "3") or not date:
            continue
        try:
            phase_markers.append(
                (datetime.fromisoformat(str(date)), f"Q{phase}")
            )
        except ValueError:
            continue
    phase_markers.sort(key=lambda item: item[0])
    marker_dates = [item[0] for item in phase_markers]
    for lap in bundle.laps:
        started = lap.get("date_start")
        number = lap.get("driver_number")
        lap_number = lap.get("lap_number")
        if not phase_markers or not started or number is None or lap_number is None:
            continue
        try:
            timestamp = datetime.fromisoformat(str(started))
        except ValueError:
            continue
        index = bisect_right(marker_dates, timestamp) - 1
        if index >= 0:
            enrichment["lap_stages"][f"{int(number)}:{int(lap_number)}"] = (
                phase_markers[index][1]
            )
    return enrichment


def fastf1_enrichment(loaded, session_name: str) -> dict:
    """Preserve FastF1's richer qualifying segmentation when it is available."""
    enrichment: dict = {"qualifying": [], "lap_stages": {}}
    name = session_name.casefold()
    if "qualifying" not in name and "shootout" not in name:
        return enrichment
    for _, row in loaded.results.iterrows():
        enrichment["qualifying"].append(
            {
                "driver_number": int(row["DriverNumber"]),
                **{
                    stage: (
                        None
                        if pd.isna(row.get(stage))
                        else row[stage].total_seconds()
                    )
                    for stage in ("Q1", "Q2", "Q3")
                },
                "position": (
                    None
                    if pd.isna(row.get("Position"))
                    else int(row["Position"])
                ),
            }
        )
    for index, laps in enumerate(loaded.laps.split_qualifying_sessions(), 1):
        if laps is None:
            continue
        for _, row in laps.iterrows():
            enrichment["lap_stages"][
                f"{int(row['DriverNumber'])}:{int(row['LapNumber'])}"
            ] = f"Q{index}"
    return enrichment


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

    async def _export_telemetry_channels(
        self,
        job: dict,
        provider,
        source,
        drivers: list[str],
        unavailable_drivers: list[str],
    ) -> tuple[list[dict], list[str]]:
        completed_channels = {driver: set() for driver in drivers}
        stored_files: list[dict] = []
        channel_ranges = {
            "car": (40, 27, "Car telemetry"),
            "position": (67, 28, "Position telemetry"),
        }
        for channel, (base, span, label) in channel_ranges.items():
            job.update(progress=base, message=f"Downloading {label.lower()}")
            await self.save(job)
            exports, objects = await provider.export_channel_streaming(
                job["session_key"], source, drivers, channel
            )
            stored_files.extend(objects)
            exported_drivers = {exported.driver for exported in exports}
            for driver in exported_drivers:
                completed_channels[driver].add(channel)
            unavailable_drivers.extend(
                driver for driver in drivers if driver not in exported_drivers
            )
            job["telemetry_unavailable_drivers"] = sorted(set(unavailable_drivers))
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
        if not telemetry_drivers:
            raise ExternalDataError("Telemetry provider produced no usable driver data")
        return stored_files, telemetry_drivers

    async def _prepare_telemetry(
        self,
        job: dict,
        bundle,
        context,
    ) -> tuple[list[dict], list[str], FastF1TelemetryProvider | None, object | None]:
        requested_drivers = [
            driver.name_acronym for driver in context.drivers if driver.name_acronym
        ]
        fast: FastF1TelemetryProvider | None = None
        loaded = None
        try:
            fast = FastF1TelemetryProvider()
            loaded = await fast.load_session(
                context.session.year,
                bundle.meeting.get("meeting_name") or context.session.country_name,
                context.session.session_name,
                telemetry=False,
            )
            drivers, unavailable_drivers = drivers_with_fastf1_laps(
                loaded, requested_drivers
            )
            if not drivers:
                raise ExternalDataError(
                    "FastF1 returned no laps for any session driver"
                )
            telemetry_files, telemetry_drivers = await self._export_telemetry_channels(
                job, fast, loaded, drivers, unavailable_drivers
            )
            job["telemetry_provider"] = "FastF1"
        except ExternalDataError as exc:
            logger.warning(
                "FastF1 unavailable for session %s; using OpenF1 telemetry: %s",
                job["session_key"],
                exc,
            )
            job.update(
                telemetry_provider="OpenF1",
                progress=40,
                message="FastF1 unavailable; switching to OpenF1 telemetry",
            )
            await self.save(job)
            drivers, unavailable_drivers = drivers_with_openf1_laps(
                bundle, requested_drivers
            )
            if not drivers:
                raise ExternalDataError(
                    "OpenF1 returned no laps for any session driver"
                ) from exc
            async with OpenF1Provider() as openf1_telemetry:
                telemetry_files, telemetry_drivers = (
                    await self._export_telemetry_channels(
                        job,
                        openf1_telemetry,
                        bundle,
                        drivers,
                        unavailable_drivers,
                    )
                )
        return telemetry_files, telemetry_drivers, fast, loaded

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
                    enrichment = openf1_enrichment(
                        bundle, context.session.session_name
                    )
                    await records.put("session_enrichment", str(key), enrichment)
                    telemetry_files, telemetry_drivers, fast, loaded = (
                        await self._prepare_telemetry(job, bundle, context)
                    )
                    if job.get("telemetry_provider") == "FastF1" and loaded is not None:
                        await records.put(
                            "session_enrichment",
                            str(key),
                            fastf1_enrichment(loaded, context.session.session_name),
                        )
                    stored_files.extend(telemetry_files)
                    succeeded = len(telemetry_drivers)
                    clear_telemetry_cache()
                    job["telemetry_ready"] = not job["errors"]
                    job["telemetry_drivers_ready"] = succeeded
                    manifest = {
                        "version": 1,
                        "session_key": key,
                        "created_at": datetime.now(UTC).isoformat(),
                        "complete": job["telemetry_ready"],
                        "telemetry_provider": job.get("telemetry_provider", "FastF1"),
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

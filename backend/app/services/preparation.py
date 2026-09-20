"""Single-process, durable session preparation jobs with bounded concurrency."""

import asyncio
import logging
from datetime import UTC, datetime

import pandas as pd

from app.ingestion.providers.fastf1 import FastF1TelemetryProvider
from app.ingestion.providers.openf1 import OpenF1Provider
from app.ingestion.service import IngestionService
from app.persistence.database import AsyncSessionLocal
from app.persistence.repositories.event_repository import EventRepository
from app.persistence.repositories.ingestion_repository import IngestionRepository
from app.persistence.repositories.workspace_repository import workspace_repository as records
from app.services.telemetry import _load_frame

logger = logging.getLogger(__name__)
ACTIVE = {"queued", "preparing"}


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
                    await EventRepository(db).upsert_many(events)
                service.save_processed_events(key, events)
                job.update(events_ready=True, progress=40, message="Timing ready")
                await self.save(job)
                if job["telemetry_requested"]:
                    fast = FastF1TelemetryProvider()
                    loaded = await fast.load_session(
                        context.session.year,
                        bundle.meeting.get("meeting_name") or context.session.country_name,
                        context.session.session_name,
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
                    drivers = [
                        driver.name_acronym for driver in context.drivers if driver.name_acronym
                    ]
                    succeeded = 0
                    for index, driver in enumerate(drivers):
                        try:
                            extracted = await fast.extract_driver(loaded, driver)
                            await fast.export_driver(key, extracted)
                            succeeded += 1
                        except Exception as exc:
                            logger.exception("Telemetry preparation failed for %s", driver)
                            job["errors"].append(f"{driver}: {type(exc).__name__}")
                        job.update(
                            progress=40 + round(55 * (index + 1) / max(len(drivers), 1)),
                            message=f"Telemetry {index + 1}/{len(drivers)} drivers",
                        )
                        await self.save(job)
                    _load_frame.cache_clear()
                    job["telemetry_ready"] = bool(drivers) and succeeded == len(drivers)
                    job["telemetry_drivers_ready"] = succeeded
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

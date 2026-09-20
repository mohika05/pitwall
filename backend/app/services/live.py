"""Polling live adapter. Rebuilds from normalized events to handle late corrections."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.ingestion.providers.base import SessionDataBundle
from app.ingestion.providers.openf1 import OpenF1Provider
from app.ingestion.service import IngestionService
from app.persistence.database import AsyncSessionLocal
from app.persistence.repositories.event_repository import EventRepository
from app.persistence.repositories.ingestion_repository import IngestionRepository
from app.replay.engine import ReplayEngine

logger = logging.getLogger(__name__)
ENDPOINTS = {
    "laps": "laps",
    "positions": "position",
    "intervals": "intervals",
    "stints": "stints",
    "pits": "pit",
    "race_control": "race_control",
    "weather": "weather",
}


def merge_rows(existing: list[dict], incoming: list[dict], kind: str) -> list[dict]:
    def key(row):
        if kind == "laps":
            return row.get("driver_number"), row.get("lap_number")
        if kind == "stints":
            return row.get("driver_number"), row.get("stint_number")
        return (
            row.get("driver_number"),
            row.get("date"),
            row.get("message") if kind == "race_control" else None,
        )

    merged = {key(row): row for row in existing}
    merged.update({key(row): row for row in incoming})
    return list(merged.values())


class LiveService:
    def __init__(self):
        self.tasks = {}
        self.feeds = {}
        self.lock = asyncio.Lock()

    async def start(self, key: int):
        if not settings.openf1_access_token:
            raise ValueError("Live access requires OPENF1_ACCESS_TOKEN on the server")
        async with self.lock:
            if key in self.tasks and not self.tasks[key].done():
                return self.feeds[key]
            self.feeds[key] = {
                "session_key": key,
                "status": "connecting",
                "state": None,
                "telemetry": None,
                "updated_at": None,
                "error": None,
            }
            self.tasks[key] = asyncio.create_task(self.run(key))
            return self.feeds[key]

    async def run(self, key):
        feed = self.feeds[key]
        try:
            async with OpenF1Provider() as provider:
                session = await provider.get_session(key)
                now = datetime.now(UTC)
                start = datetime.fromisoformat(session["date_start"])
                end = (
                    datetime.fromisoformat(session["date_end"]) if session.get("date_end") else None
                )
                if now < start - timedelta(minutes=30) or (
                    end and now > end + timedelta(minutes=30)
                ):
                    raise ValueError("Session is outside the live window; use historical replay")
                meetings = await provider._get("meetings", {"meeting_key": session["meeting_key"]})
                drivers = await provider._get("drivers", {"session_key": key})
                bundle = SessionDataBundle(
                    meeting=meetings[0],
                    session=session,
                    drivers=drivers,
                    starting_grid=await provider._get_optional(
                        "starting_grid", {"session_key": key}
                    ),
                    session_result=await provider._get_optional(
                        "session_result", {"session_key": key}
                    ),
                )
                since = None
                location_history = []
                while True:
                    cycle_start = datetime.now(UTC)
                    for field, endpoint in ENDPOINTS.items():
                        params = {"session_key": key}
                        if since and field != "stints":
                            params["date_start>=" if field == "laps" else "date>="] = (
                                since - timedelta(minutes=3)
                            ).isoformat()
                        rows = await provider._get(endpoint, params)
                        setattr(bundle, field, merge_rows(getattr(bundle, field), rows, field))
                    context, events = IngestionService(provider).normalize(bundle)
                    state = ReplayEngine(context, events).run_to_end()
                    async with AsyncSessionLocal() as db, db.begin():
                        await IngestionRepository(db).persist_bundle(bundle)
                        await EventRepository(db).upsert_many(events)
                    samples = {}
                    for endpoint in ("car_data", "location"):
                        samples[endpoint] = await provider._get(
                            endpoint,
                            {
                                "session_key": key,
                                "date>=": (cycle_start - timedelta(seconds=30)).isoformat(),
                            },
                        )
                    # Build a circuit from an observed completed lap when historical Parquet is absent.
                    if not feed.get("track"):
                        location_history = merge_rows(
                            location_history, samples["location"], "location"
                        )
                        for lap in reversed(bundle.laps):
                            if not lap.get("date_start") or not lap.get("lap_duration"):
                                continue
                            lap_start = datetime.fromisoformat(lap["date_start"])
                            lap_end = lap_start + timedelta(seconds=lap["lap_duration"])
                            points = sorted(
                                [
                                    row
                                    for row in location_history
                                    if row.get("driver_number") == lap["driver_number"]
                                    and lap_start <= datetime.fromisoformat(row["date"]) <= lap_end
                                    and row.get("x") is not None
                                    and row.get("y") is not None
                                ],
                                key=lambda row: row["date"],
                            )
                            if (
                                len(points) >= 50
                                and datetime.fromisoformat(points[0]["date"])
                                <= lap_start + timedelta(seconds=5)
                                and datetime.fromisoformat(points[-1]["date"])
                                >= lap_end - timedelta(seconds=5)
                            ):
                                feed["track"] = {
                                    "session_key": key,
                                    "driver": str(lap["driver_number"]),
                                    "lap_number": lap["lap_number"],
                                    "points": [
                                        {"x": row["x"], "y": row["y"]}
                                        for row in points[:: max(1, len(points) // 400)]
                                    ],
                                }
                                break
                    telemetry = []
                    for driver in context.drivers:

                        def latest(endpoint, samples=samples, driver=driver):
                            rows = [
                                row
                                for row in samples[endpoint]
                                if row.get("driver_number") == driver.driver_number
                            ]
                            return max(rows, key=lambda row: row.get("date", "")) if rows else None

                        car, position = latest("car_data"), latest("location")
                        telemetry.append(
                            {
                                "driver": driver.name_acronym,
                                "driver_number": driver.driver_number,
                                "car": {
                                    "Date": car["date"],
                                    "Speed": car.get("speed"),
                                    "RPM": car.get("rpm"),
                                    "nGear": car.get("n_gear"),
                                    "Throttle": car.get("throttle"),
                                    "Brake": bool(car.get("brake")),
                                    "DRS": car.get("drs"),
                                }
                                if car
                                else None,
                                "position": {
                                    "Date": position["date"],
                                    "X": position.get("x"),
                                    "Y": position.get("y"),
                                    "Z": position.get("z"),
                                    "Status": "Observed",
                                }
                                if position
                                else None,
                            }
                        )
                    feed.update(
                        status="live",
                        state=state.model_dump(mode="json"),
                        error=None,
                        updated_at=datetime.now(UTC).isoformat(),
                        telemetry={
                            "session_key": key,
                            "timestamp": cycle_start.isoformat(),
                            "drivers": telemetry,
                        },
                    )
                    since = cycle_start
                    if end and cycle_start > end + timedelta(minutes=30):
                        feed["status"] = "finished"
                        return
                    await asyncio.sleep(10)
        except asyncio.CancelledError:
            feed["status"] = "stopped"
            raise
        except Exception as exc:
            logger.exception("Live ingestion failed")
            feed.update(status="error", error=str(exc))

    async def stop(self, key):
        task = self.tasks.get(key)
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return self.feeds.get(key)

    async def close(self):
        for key in list(self.tasks):
            await self.stop(key)


live_service = LiveService()

from datetime import timedelta
from statistics import median

from app.core.config import settings
from app.domain.enums import EventType, SafetyCarState
from app.domain.race_state import apply_event, build_initial_state
from app.persistence.database import AsyncSessionLocal
from app.persistence.repositories.event_repository import EventRepository
from app.persistence.repositories.session_repository import SessionRepository
from app.persistence.repositories.workspace_repository import workspace_repository


def analyse(context, events, enrichment=None):
    enrichment = enrichment or {}
    state = build_initial_state(context)
    laps, stints, timeline = [], [], []
    for index, event in enumerate(events):
        if event.timestamp < context.session.date_start:
            continue
        apply_event(state, event)
        driver = state.drivers.get(event.driver_number)
        if event.event_type == EventType.LAP_COMPLETED:
            duration = event.payload.get("lap_duration")
            if duration is None or duration <= 0:
                continue
            laps.append(
                {
                    "driver_number": event.driver_number,
                    "driver": driver.name_acronym,
                    "lap": event.lap_number,
                    "seconds": duration,
                    "start": (event.timestamp - timedelta(seconds=duration)).isoformat(),
                    "end": event.timestamp.isoformat(),
                    "compound": driver.compound,
                    "tyre_age": driver.tyre_age,
                    "stint": driver.stint_number,
                    "pit_out": bool(event.payload.get("is_pit_out_lap")),
                    "neutralized": state.safety_car != SafetyCarState.NONE
                    or state.flag in ("YELLOW", "RED"),
                    "sectors": [event.payload.get(f"duration_sector_{i}") for i in (1, 2, 3)],
                    "stage": enrichment.get("lap_stages", {}).get(
                        f"{event.driver_number}:{event.lap_number}"
                    ),
                }
            )
        if event.event_type == EventType.STINT_STARTED:
            stints.append(
                {
                    "driver_number": event.driver_number,
                    "driver": driver.name_acronym,
                    **event.payload,
                    "timestamp": event.timestamp.isoformat(),
                }
            )
        if event.event_type in (EventType.PIT_STOP, EventType.RACE_CONTROL):
            timeline.append(
                {
                    "id": event.event_id,
                    "event_index": index,
                    "type": event.event_type.value,
                    "timestamp": event.timestamp.isoformat(),
                    "driver": driver.name_acronym if driver else None,
                    "lap": event.lap_number,
                    "payload": event.payload,
                }
            )
    summaries = []
    for driver in context.drivers:
        rows = [lap for lap in laps if lap["driver_number"] == driver.driver_number]
        clean = [lap["seconds"] for lap in rows if not lap["pit_out"] and not lap["neutralized"]]
        summaries.append(
            {
                **driver.model_dump(),
                "laps": len(rows),
                "best": min((lap["seconds"] for lap in rows), default=None),
                "median_pace": median(clean) if clean else None,
            }
        )
    directory = settings.telemetry_dir / str(context.session.session_key)
    ready = [
        d.name_acronym
        for d in context.drivers
        if d.name_acronym
        and (directory / f"{d.name_acronym}_car.parquet").exists()
        and (directory / f"{d.name_acronym}_position.parquet").exists()
    ]
    return {
        "session": context.session.model_dump(mode="json"),
        "drivers": summaries,
        "laps": laps,
        "stints": stints,
        "timeline": timeline,
        "qualifying": enrichment.get("qualifying", []),
        "start": context.session.date_start.isoformat(),
        "end": events[-1].timestamp.isoformat()
        if events
        else context.session.date_start.isoformat(),
        "quality": {
            "source": "OpenF1 timing / FastF1 telemetry",
            "telemetry_drivers": ready,
            "total_drivers": len(context.drivers),
            "note": "Recorded samples; missing and invalid laps are excluded from pace summaries. Qualifying stages require FastF1 preparation.",
        },
    }


async def load_history(session_key: int):
    async with AsyncSessionLocal() as db:
        repository = SessionRepository(db)
        context = await repository.get_replay_context(session_key)
        events = await EventRepository(db).get_for_session(session_key)
        official = await repository.get_official_result(session_key)
    return context, events, official


async def session_analysis(session_key: int):
    context, events, official = await load_history(session_key)
    enrichment = await workspace_repository.get("session_enrichment", str(session_key))
    result = analyse(context, events, enrichment)
    result["official_result"] = official
    return result

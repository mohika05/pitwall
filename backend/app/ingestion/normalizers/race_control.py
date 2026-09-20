from typing import Any

from app.domain.enums import EventType
from app.domain.events import RaceEvent
from app.ingestion.normalizers.common import (
    make_event,
    parse_datetime,
)

def normalize_race_control(
    rows: list[dict[str, Any]],
) -> list[RaceEvent]:
    events: list[RaceEvent] = []
    for row in rows:
        timestamp = parse_datetime(
            row.get("date")
        )
        if timestamp is None:
            continue
        driver_number_raw = row.get(
            "driver_number"
        )
        driver_number = (
            int(driver_number_raw)
            if driver_number_raw is not None
            else None
        )
        payload = {
            "category": row.get("category"),
            "flag": row.get("flag"),
            "message": row.get("message"),
            "scope": row.get("scope"),
            "sector": row.get("sector"),
        }
        events.append(
            make_event(
                event_type=EventType.RACE_CONTROL,
                timestamp=timestamp,
                meeting_key=int(
                    row["meeting_key"]
                ),
                session_key=int(
                    row["session_key"]
                ),
                driver_number=driver_number,
                lap_number=row.get(
                    "lap_number"
                ),
                payload=payload,
                identity=[
                    timestamp.isoformat(),
                    driver_number,
                    row.get("category"),
                    row.get("message"),
                ],
            )
        )
    return events
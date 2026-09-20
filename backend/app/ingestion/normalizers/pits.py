from typing import Any

from app.domain.enums import EventType
from app.domain.events import RaceEvent
from app.ingestion.normalizers.common import (
    make_event,
    parse_datetime,
)

def normalize_pits(
    rows: list[dict[str, Any]],
) -> list[RaceEvent]:
    events: list[RaceEvent] = []
    for row in rows:
        timestamp = parse_datetime(
            row.get("date")
        )
        if timestamp is None:
            continue
        driver_number = int(
            row["driver_number"]
        )
        lap_number = int(
            row["lap_number"]
        )
        events.append(
            make_event(
                event_type=EventType.PIT_STOP,
                timestamp=timestamp,
                meeting_key=int(
                    row["meeting_key"]
                ),
                session_key=int(
                    row["session_key"]
                ),
                driver_number=driver_number,
                lap_number=lap_number,
                payload={
                    "lane_duration": row.get(
                        "lane_duration"
                    ),
                    "stop_duration": row.get(
                        "stop_duration"
                    ),
                },
                identity=[
                    driver_number,
                    lap_number,
                    timestamp.isoformat(),
                ],
            )
        )
    return events
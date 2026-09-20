from typing import Any

from app.domain.enums import EventType
from app.domain.events import RaceEvent
from app.ingestion.normalizers.common import (
    make_event,
    parse_datetime,
)

def normalize_positions(
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
        events.append(
            make_event(
                event_type=EventType.POSITION_CHANGED,
                timestamp=timestamp,
                meeting_key=int(
                    row["meeting_key"]
                ),
                session_key=int(
                    row["session_key"]
                ),
                driver_number=driver_number,
                payload={
                    "position": int(
                        row["position"]
                    )
                },
                identity=[
                    driver_number,
                    timestamp.isoformat(),
                ],
            )
        )
    return events
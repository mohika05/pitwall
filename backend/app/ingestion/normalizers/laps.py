from datetime import timedelta
from typing import Any

from app.domain.enums import EventType
from app.domain.events import RaceEvent
from app.ingestion.normalizers.common import (
    make_event,
    parse_datetime,
)

def normalize_laps(
    rows: list[dict[str, Any]],
) -> list[RaceEvent]:
    events: list[RaceEvent] = []
    for row in rows:
        start = parse_datetime(
            row.get("date_start")
        )
        if start is None:
            continue
        duration = row.get("lap_duration")
        timestamp = start
        if isinstance(duration, (int, float)):
            timestamp = start + timedelta(
                seconds=float(duration)
            )
        driver_number = int(
            row["driver_number"]
        )
        lap_number = int(
            row["lap_number"]
        )
        payload = {
            "lap_duration": duration,
            "duration_sector_1": row.get(
                "duration_sector_1"
            ),
            "duration_sector_2": row.get(
                "duration_sector_2"
            ),
            "duration_sector_3": row.get(
                "duration_sector_3"
            ),
            "i1_speed": row.get("i1_speed"),
            "i2_speed": row.get("i2_speed"),
            "st_speed": row.get("st_speed"),
            "is_pit_out_lap": row.get(
                "is_pit_out_lap"
            ),
        }
        events.append(
            make_event(
                event_type=EventType.LAP_COMPLETED,
                timestamp=timestamp,
                meeting_key=int(
                    row["meeting_key"]
                ),
                session_key=int(
                    row["session_key"]
                ),
                driver_number=driver_number,
                lap_number=lap_number,
                payload=payload,
                identity=[
                    driver_number,
                    lap_number,
                ],
            )
        )
    return events
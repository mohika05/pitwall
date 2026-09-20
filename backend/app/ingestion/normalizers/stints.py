from collections import defaultdict
from datetime import datetime
from typing import Any

from app.domain.enums import EventType
from app.domain.events import RaceEvent
from app.ingestion.normalizers.common import (
    make_event,
    parse_datetime,
)

def normalize_stints(
    rows: list[dict[str, Any]],
    laps: list[dict[str, Any]],
    session_start: datetime,
) -> list[RaceEvent]:
    lap_starts: dict[
        tuple[int, int],
        datetime,
    ] = {}
    driver_laps: dict[
        int,
        list[tuple[int, datetime]],
    ] = defaultdict(list)
    for lap in laps:
        timestamp = parse_datetime(
            lap.get("date_start")
        )
        if timestamp is None:
            continue
        driver_number = int(
            lap["driver_number"]
        )
        lap_number = int(
            lap["lap_number"]
        )
        lap_starts[
            (driver_number, lap_number)
        ] = timestamp
        driver_laps[driver_number].append(
            (lap_number, timestamp)
        )
    for driver_number in driver_laps:
        driver_laps[driver_number].sort()
    events: list[RaceEvent] = []
    for row in rows:
        # A retired driver's tyre record may have no recorded lap range.
        # It cannot be placed on the replay timeline without inventing a lap.
        if row.get("lap_start") is None:
            continue
        driver_number = int(
            row["driver_number"]
        )
        lap_start = int(
            row["lap_start"]
        )
        timestamp = lap_starts.get(
            (driver_number, lap_start)
        )
        if timestamp is None:
            candidates = [
                date
                for lap_number, date
                in driver_laps.get(
                    driver_number,
                    [],
                )
                if lap_number >= lap_start
            ]
            timestamp = (
                candidates[0]
                if candidates
                else session_start
            )
        stint_number = int(
            row["stint_number"]
        )
        events.append(
            make_event(
                event_type=EventType.STINT_STARTED,
                timestamp=timestamp,
                meeting_key=int(
                    row["meeting_key"]
                ),
                session_key=int(
                    row["session_key"]
                ),
                driver_number=driver_number,
                lap_number=lap_start,
                payload={
                    "stint_number": stint_number,
                    "lap_start": lap_start,
                    "lap_end": row.get(
                        "lap_end"
                    ),
                    "compound": row.get(
                        "compound"
                    ),
                    "tyre_age_at_start": (
                        row.get(
                            "tyre_age_at_start"
                        )
                    ),
                },
                identity=[
                    driver_number,
                    stint_number,
                ],
            )
        )
    return events

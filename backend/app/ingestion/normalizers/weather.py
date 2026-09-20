from typing import Any

from app.domain.enums import EventType
from app.domain.events import RaceEvent
from app.ingestion.normalizers.common import (
    make_event,
    parse_datetime,
)

def normalize_weather(
    rows: list[dict[str, Any]],
) -> list[RaceEvent]:
    events: list[RaceEvent] = []
    for row in rows:
        timestamp = parse_datetime(
            row.get("date")
        )
        if timestamp is None:
            continue
        payload = {
            "air_temperature": row.get(
                "air_temperature"
            ),
            "track_temperature": row.get(
                "track_temperature"
            ),
            "humidity": row.get(
                "humidity"
            ),
            "pressure": row.get(
                "pressure"
            ),
            "rainfall": row.get(
                "rainfall"
            ),
            "wind_direction": row.get(
                "wind_direction"
            ),
            "wind_speed": row.get(
                "wind_speed"
            ),
        }
        events.append(
            make_event(
                event_type=EventType.WEATHER_UPDATED,
                timestamp=timestamp,
                meeting_key=int(
                    row["meeting_key"]
                ),
                session_key=int(
                    row["session_key"]
                ),
                payload=payload,
                identity=[
                    timestamp.isoformat()
                ],
            )
        )
    return events
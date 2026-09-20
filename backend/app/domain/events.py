from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain.enums import EventType


class RaceEvent(BaseModel):
    event_id: str

    meeting_key: int
    session_key: int

    event_type: EventType
    timestamp: datetime

    driver_number: int | None = None
    lap_number: int | None = None

    payload: dict[str, Any] = Field(
        default_factory=dict
    )


EVENT_PRIORITY: dict[EventType, int] = {
    EventType.STINT_STARTED: 10,
    EventType.POSITION_CHANGED: 20,
    EventType.INTERVAL_UPDATED: 30,
    EventType.PIT_STOP: 40,
    EventType.LAP_COMPLETED: 50,
    EventType.RACE_CONTROL: 60,
    EventType.WEATHER_UPDATED: 70,
}


def sort_events(
    events: list[RaceEvent],
) -> list[RaceEvent]:
    return sorted(
        events,
        key=lambda event: (
            event.timestamp,
            EVENT_PRIORITY[event.event_type],
            event.event_id,
        ),
    )
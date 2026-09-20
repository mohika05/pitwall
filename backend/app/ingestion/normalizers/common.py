import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.domain.enums import EventType
from app.domain.events import RaceEvent

def parse_datetime(
    value: str | None,
) -> datetime | None:
    if value is None:
        return None

    parsed = datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed

def stable_event_id(
    event_type: EventType,
    session_key: int,
    identity: list[Any],
) -> str:
    raw = {
        "event_type": event_type.value,
        "session_key": session_key,
        "identity": identity,
    }

    encoded = json.dumps(
        raw,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()

    return hashlib.sha256(encoded).hexdigest()

def make_event(
    *,
    event_type: EventType,
    timestamp: datetime,
    meeting_key: int,
    session_key: int,
    payload: dict[str, Any],
    identity: list[Any],
    driver_number: int | None = None,
    lap_number: int | None = None,
) -> RaceEvent:
    return RaceEvent(
        event_id=stable_event_id(
            event_type,
            session_key,
            identity,
        ),
        meeting_key=meeting_key,
        session_key=session_key,
        event_type=event_type,
        timestamp=timestamp,
        driver_number=driver_number,
        lap_number=lap_number,
        payload=payload,
    )
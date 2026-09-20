from typing import Any

from pydantic import BaseModel, Field


class RealtimeMessage(BaseModel):
    type: str

    session_key: int

    payload: dict[str, Any] = Field(
        default_factory=dict
    )

def race_state_message(
    session_key: int,
    state: dict[str, Any],
    event_index: int,
    total_events: int,
    playing: bool,
    speed: float,
    revision: int = 0,
) -> RealtimeMessage:
    return RealtimeMessage(
        type="race_state",
        session_key=session_key,
        payload={
            "state": state,
            "revision": revision,
            "event_index": (
                event_index
            ),
            "total_events": (
                total_events
            ),
            "playing": playing,
            "speed": speed,
        },
    )
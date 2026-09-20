from datetime import datetime, timezone

from app.domain.entities import (
    DriverInfo,
    ReplayContext,
    SessionInfo,
)
from app.domain.enums import (
    EventType,
    SafetyCarState,
)
from app.domain.events import RaceEvent
from app.domain.race_state import (
    apply_event,
    build_initial_state,
)


NOW = datetime(
    2025,
    1,
    1,
    tzinfo=timezone.utc,
)


def context() -> ReplayContext:
    return ReplayContext(
        session=SessionInfo(
            session_key=1,
            meeting_key=2,
            year=2025,
            session_name="Race",
            session_type="Race",
            date_start=NOW,
        ),
        drivers=[
            DriverInfo(
                driver_number=4,
                name_acronym="NOR",
            )
        ],
        starting_grid={
            4: 2
        },
    )


def event(
    event_type: EventType,
    payload: dict,
    lap_number: int | None = None,
) -> RaceEvent:
    return RaceEvent(
        event_id=event_type.value,
        meeting_key=2,
        session_key=1,
        event_type=event_type,
        timestamp=NOW,
        driver_number=(
            None
            if event_type
            in {
                EventType.RACE_CONTROL,
                EventType.WEATHER_UPDATED,
            }
            else 4
        ),
        lap_number=lap_number,
        payload=payload,
    )


def test_state_transitions() -> None:
    state = build_initial_state(
        context()
    )

    apply_event(
        state,
        event(
            EventType.STINT_STARTED,
            {
                "stint_number": 1,
                "lap_start": 1,
                "compound": "MEDIUM",
                "tyre_age_at_start": 0,
            },
            lap_number=1,
        ),
    )

    apply_event(
        state,
        event(
            EventType.POSITION_CHANGED,
            {"position": 1},
        ),
    )

    apply_event(
        state,
        event(
            EventType.INTERVAL_UPDATED,
            {
                "gap_to_leader": None,
                "interval": None,
            },
        ),
    )

    apply_event(
        state,
        event(
            EventType.LAP_COMPLETED,
            {"lap_duration": 90.5},
            lap_number=1,
        ),
    )

    driver = state.drivers[4]

    assert driver.position == 1
    assert driver.current_lap == 1
    assert driver.compound == "MEDIUM"
    assert driver.tyre_age == 1
    assert driver.last_lap_time == 90.5


def test_safety_car_state() -> None:
    state = build_initial_state(
        context()
    )

    apply_event(
        state,
        event(
            EventType.RACE_CONTROL,
            {
                "category": "SafetyCar",
                "message": (
                    "SAFETY CAR DEPLOYED"
                ),
                "flag": None,
            },
        ),
    )

    assert (
        state.safety_car
        == SafetyCarState.FULL
    )
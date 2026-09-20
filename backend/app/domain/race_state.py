from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.entities import ReplayContext
from app.domain.enums import EventType, SafetyCarState
from app.domain.events import RaceEvent

GapValue = float | str | None

class DriverState(BaseModel):
    driver_number: int
    full_name: str | None = None
    name_acronym: str | None = None
    team_name: str | None = None
    team_colour: str | None = None
    position: int | None = None
    classified_position: int | None = None
    dnf: bool = False
    dns: bool = False
    dsq: bool = False
    current_lap: int = 0
    last_lap_time: float | None = None
    gap_to_leader: GapValue = None
    gap_to_ahead: GapValue = None
    compound: str | None = None
    stint_number: int | None = None
    stint_lap_start: int | None = None
    tyre_age_at_stint_start: int | None = None
    tyre_age: int | None = None
    pit_count: int = 0
    last_pit_lap: int | None = None
    

class WeatherState(BaseModel):
    air_temperature: float | None = None
    track_temperature: float | None = None
    humidity: float | None = None
    pressure: float | None = None
    rainfall: bool | None = None
    wind_direction: float | None = None
    wind_speed: float | None = None

class RaceState(BaseModel):
    session_key: int
    meeting_key: int
    current_lap: int = 0
    replay_timestamp: datetime
    drivers: dict[int, DriverState] = Field(
        default_factory=dict
    )
    flag: str | None = None
    safety_car: SafetyCarState = (
        SafetyCarState.NONE
    )
    safety_car_ending: bool = False
    latest_race_control_message: str | None = None
    weather: WeatherState = Field(
        default_factory=WeatherState
    )

def build_initial_state(
    context: ReplayContext,
) -> RaceState:
    drivers: dict[int, DriverState] = {}
    for driver in context.drivers:
        drivers[driver.driver_number] = DriverState(
            driver_number=driver.driver_number,
            full_name=driver.full_name,
            name_acronym=driver.name_acronym,
            team_name=driver.team_name,
            team_colour=driver.team_colour,
            position=context.starting_grid.get(
                driver.driver_number
            ),
        )
    return RaceState(
        session_key=context.session.session_key,
        meeting_key=context.session.meeting_key,
        replay_timestamp=context.session.date_start,
        drivers=drivers,
    )

def _driver(
    state: RaceState,
    driver_number: int,
) -> DriverState:
    if driver_number not in state.drivers:
        state.drivers[driver_number] = DriverState(
            driver_number=driver_number
        )
    return state.drivers[driver_number]


def _apply_race_control(
    state: RaceState,
    event: RaceEvent,
) -> None:
    message = str(
        event.payload.get("message") or ""
    )
    category = str(
        event.payload.get("category") or ""
    )
    flag = event.payload.get("flag")
    state.latest_race_control_message = (
        message or state.latest_race_control_message
    )
    scope = str(event.payload.get("scope") or "").upper()
    if flag and scope != "DRIVER":
        state.flag = str(flag)
    upper_message = message.upper()
    upper_category = category.upper()
    if (
        "VIRTUAL SAFETY CAR" in upper_message
        and "DEPLOY" in upper_message
    ):
        state.safety_car = SafetyCarState.VIRTUAL
        state.safety_car_ending = False
    elif (
        "SAFETY CAR" in upper_message
        and "VIRTUAL" not in upper_message
        and "DEPLOY" in upper_message
    ):
        state.safety_car = SafetyCarState.FULL
        state.safety_car_ending = False
    elif "SAFETY CAR IN THIS LAP" in upper_message:
        state.safety_car_ending = True
    elif (
        "VIRTUAL SAFETY CAR" in upper_message
        and (
            "ENDING" in upper_message
            or "ENDED" in upper_message
        )
    ):
        state.safety_car = SafetyCarState.NONE
    elif (
        upper_category == "SAFETYCAR"
        and "CLEAR" in upper_message
    ):
        state.safety_car = SafetyCarState.NONE

    if (
        str(flag).upper() == "GREEN" and scope in {"", "TRACK"}
    ) or (
        state.safety_car_ending and scope == "TRACK" and str(flag).upper() == "CLEAR"
    ):
        state.safety_car = SafetyCarState.NONE
    if state.safety_car == SafetyCarState.NONE:
        state.safety_car_ending = False

def apply_event(
    state: RaceState,
    event: RaceEvent,
) -> RaceState:
    state.replay_timestamp = event.timestamp
    driver = None
    if event.driver_number is not None:
        driver = _driver(
            state,
            event.driver_number,
        )
    if event.event_type == EventType.STINT_STARTED:
        assert driver is not None
        driver.stint_number = event.payload.get(
            "stint_number"
        )
        driver.stint_lap_start = event.payload.get(
            "lap_start"
        )
        driver.compound = event.payload.get(
            "compound"
        )
        driver.tyre_age_at_stint_start = (
            event.payload.get("tyre_age_at_start")
        )
        driver.tyre_age = (
            driver.tyre_age_at_stint_start
        )
    elif event.event_type == EventType.POSITION_CHANGED:
        assert driver is not None
        driver.position = event.payload.get(
            "position"
        )
    elif event.event_type == EventType.INTERVAL_UPDATED:
        assert driver is not None
        driver.gap_to_leader = (
            event.payload.get("gap_to_leader")
        )
        driver.gap_to_ahead = (
            event.payload.get("interval")
        )
    elif event.event_type == EventType.PIT_STOP:
        assert driver is not None
        driver.pit_count += 1
        driver.last_pit_lap = event.lap_number
    elif event.event_type == EventType.LAP_COMPLETED:
        assert driver is not None
        if event.lap_number is not None:
            driver.current_lap = max(
                driver.current_lap,
                event.lap_number,
            )
            state.current_lap = max(
                state.current_lap,
                event.lap_number,
            )
        driver.last_lap_time = (
            event.payload.get("lap_duration")
        )
        if (
            driver.stint_lap_start is not None
            and driver.tyre_age_at_stint_start
            is not None
            and event.lap_number is not None
        ):
            driver.tyre_age = (
                driver.tyre_age_at_stint_start
                + (
                    event.lap_number
                    - driver.stint_lap_start
                    + 1
                )
            )
    elif event.event_type == EventType.RACE_CONTROL:
        _apply_race_control(
            state,
            event,
        )
    elif event.event_type == EventType.WEATHER_UPDATED:
        state.weather = WeatherState(
            air_temperature=event.payload.get(
                "air_temperature"
            ),
            track_temperature=event.payload.get(
                "track_temperature"
            ),
            humidity=event.payload.get(
                "humidity"
            ),
            pressure=event.payload.get(
                "pressure"
            ),
            rainfall=(
                bool(event.payload["rainfall"])
                if event.payload.get("rainfall")
                is not None
                else None
            ),
            wind_direction=event.payload.get(
                "wind_direction"
            ),
            wind_speed=event.payload.get(
                "wind_speed"
            ),
        )
    return state

def apply_official_classification(
    state: RaceState,
    official_result: list[dict],
) -> RaceState:
    """
    Return a copy of RaceState enriched with the official
    post-session classification.

    The timing-feed position is preserved separately.
    """

    final_state = state.model_copy(
        deep=True
    )

    for row in official_result:
        driver_number_raw = row.get(
            "driver_number"
        )

        if driver_number_raw is None:
            continue

        driver_number = int(
            driver_number_raw
        )

        driver = final_state.drivers.get(
            driver_number
        )

        if driver is None:
            continue

        position_raw = row.get(
            "position"
        )

        driver.classified_position = (
            int(position_raw)
            if position_raw is not None
            else None
        )

        driver.dnf = bool(
            row.get("dnf", False)
        )

        driver.dns = bool(
            row.get("dns", False)
        )

        driver.dsq = bool(
            row.get("dsq", False)
        )

    return final_state

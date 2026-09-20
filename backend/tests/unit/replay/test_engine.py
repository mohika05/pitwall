from datetime import (
    datetime,
    timedelta,
    timezone,
)

from app.domain.entities import (
    DriverInfo,
    ReplayContext,
    SessionInfo,
)
from app.domain.enums import EventType
from app.domain.events import RaceEvent
from app.replay.engine import (
    ReplayEngine,
    state_fingerprint,
)


START = datetime(
    2025,
    1,
    1,
    tzinfo=timezone.utc,
)


def make_context() -> ReplayContext:
    return ReplayContext(
        session=SessionInfo(
            session_key=1,
            meeting_key=2,
            year=2025,
            session_name="Race",
            session_type="Race",
            date_start=START,
        ),
        drivers=[
            DriverInfo(
                driver_number=4,
                name_acronym="NOR",
            )
        ],
        starting_grid={4: 2},
    )


def make_events() -> list[RaceEvent]:
    return [
        RaceEvent(
            event_id="position",
            meeting_key=2,
            session_key=1,
            event_type=(
                EventType.POSITION_CHANGED
            ),
            timestamp=(
                START
                + timedelta(seconds=1)
            ),
            driver_number=4,
            payload={"position": 1},
        ),
        RaceEvent(
            event_id="lap",
            meeting_key=2,
            session_key=1,
            event_type=(
                EventType.LAP_COMPLETED
            ),
            timestamp=(
                START
                + timedelta(seconds=90)
            ),
            driver_number=4,
            lap_number=1,
            payload={
                "lap_duration": 89.0
            },
        ),
    ]


def test_replay_is_deterministic() -> None:
    context = make_context()
    events = make_events()

    one = ReplayEngine(
        context,
        events,
    ).run_to_end()

    two = ReplayEngine(
        context,
        events,
    ).run_to_end()

    assert (
        state_fingerprint(one)
        == state_fingerprint(two)
    )


def test_seek() -> None:
    engine = ReplayEngine(
        make_context(),
        make_events(),
        snapshot_interval=1,
    )

    engine.run_to_end()

    state = engine.seek_time(
        START
        + timedelta(seconds=2)
    )

    assert state.drivers[4].position == 1
    assert state.drivers[4].current_lap == 0
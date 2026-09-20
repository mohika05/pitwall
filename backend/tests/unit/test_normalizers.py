from datetime import datetime, timezone

from app.domain.enums import EventType
from app.ingestion.normalizers.laps import (
    normalize_laps,
)
from app.ingestion.normalizers.stints import normalize_stints


def test_stint_without_recorded_laps_does_not_block_session():
    start = datetime(2025, 4, 20, 17, tzinfo=timezone.utc)
    common = {"meeting_key": 1258, "session_key": 10022, "stint_number": 1,
              "compound": "MEDIUM", "tyre_age_at_start": 0}
    rows = [
        {**common, "driver_number": 10, "lap_start": None, "lap_end": None},
        {**common, "driver_number": 1, "lap_start": 1, "lap_end": 20},
    ]
    events = normalize_stints(rows, [], start)
    assert len(events) == 1
    assert events[0].driver_number == 1
    assert events[0].lap_number == 1


def test_lap_normalization() -> None:
    row = {
        "date_start": (
            "2025-01-01T00:00:00+00:00"
        ),
        "driver_number": 4,
        "lap_number": 1,
        "lap_duration": 90.0,
        "meeting_key": 2,
        "session_key": 1,
        "duration_sector_1": 30.0,
        "duration_sector_2": 30.0,
        "duration_sector_3": 30.0,
        "i1_speed": 300,
        "i2_speed": 290,
        "st_speed": 310,
        "is_pit_out_lap": False,
    }

    first = normalize_laps(
        [row]
    )[0]

    second = normalize_laps(
        [row]
    )[0]

    assert (
        first.event_type
        == EventType.LAP_COMPLETED
    )

    assert (
        first.timestamp
        == datetime(
            2025,
            1,
            1,
            0,
            1,
            30,
            tzinfo=timezone.utc,
        )
    )

    assert (
        first.event_id
        == second.event_id
    )

from datetime import datetime, timezone

from app.domain.enums import EventType
from app.ingestion.normalizers.laps import (
    normalize_laps,
)


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
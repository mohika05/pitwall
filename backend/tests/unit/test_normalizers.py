from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from fastf1.exceptions import DataNotLoadedError

from app.core.exceptions import ExternalDataError
from app.domain.enums import EventType
from app.ingestion.normalizers.laps import (
    normalize_laps,
)
from app.ingestion.normalizers.stints import normalize_stints
from app.ingestion.providers import fastf1 as fastf1_provider
from app.ingestion.providers.fastf1 import FastF1TelemetryProvider


def test_2023_sprint_qualifying_uses_fastf1_historical_name() -> None:
    assert (
        FastF1TelemetryProvider._session_name(2023, "Sprint Qualifying")
        == "Sprint Shootout"
    )


def test_fastf1_unpublished_archive_is_reported_as_retryable(monkeypatch) -> None:
    class Session:
        def load(self, **_kwargs):
            return None

        @property
        def laps(self):
            raise DataNotLoadedError("laps")

    monkeypatch.setattr(fastf1_provider.fastf1, "get_session", lambda *_args: Session())

    with pytest.raises(ExternalDataError, match="scheduled ingestion will retry"):
        FastF1TelemetryProvider._load_session_sync(2026, "Bahrain Grand Prix", "Practice 2")
    assert (
        FastF1TelemetryProvider._session_name(2024, "Sprint Qualifying")
        == "Sprint Qualifying"
    )


def test_fastf1_session_can_skip_eager_telemetry(monkeypatch) -> None:
    calls = []

    class Session:
        laps = pd.DataFrame({"LapNumber": [1]})

        def load(self, **kwargs):
            calls.append(kwargs)

    session = Session()
    monkeypatch.setattr(fastf1_provider.fastf1, "get_session", lambda *_args: session)

    loaded = FastF1TelemetryProvider._load_session_sync(
        2026, "Bahrain Grand Prix", "Race", telemetry=False
    )

    assert loaded is session
    assert calls[0]["telemetry"] is False


def test_fastf1_stream_samples_are_assigned_to_laps() -> None:
    boundaries = ([10.0, 20.0], [(10.0, 20.0, 1), (20.0, 30.0, 2)])

    assert FastF1TelemetryProvider._lap_number_at(boundaries, 5.0) is None
    assert FastF1TelemetryProvider._lap_number_at(boundaries, 12.0) == 1
    assert FastF1TelemetryProvider._lap_number_at(boundaries, 22.0) == 2
    assert FastF1TelemetryProvider._lap_number_at(boundaries, 31.0) is None


def test_fastf1_streaming_writer_flushes_driver_parquet(monkeypatch, tmp_path) -> None:
    class Laps:
        def pick_drivers(self, _driver):
            return pd.DataFrame(
                {
                    "LapNumber": [1],
                    "LapStartTime": [timedelta(seconds=10)],
                    "Time": [timedelta(seconds=20)],
                }
            )

    class Session:
        api_path = "/static/test/"
        laps = Laps()

        @staticmethod
        def get_driver(_driver):
            return {"DriverNumber": "1"}

    monkeypatch.setattr(
        fastf1_provider.fastf1_api,
        "fetch_page",
        lambda *_args: ["00:00:12.000payload"],
    )
    monkeypatch.setattr(
        fastf1_provider.fastf1_api,
        "parse",
        lambda *_args, **_kwargs: {
            "Entries": [
                {
                    "Utc": "2026-10-04T12:00:12.000Z",
                    "Cars": {
                        "1": {
                            "Channels": {
                                "0": "12000",
                                "2": "300",
                                "3": "8",
                                "4": "100",
                                "5": "0",
                            }
                        }
                    },
                }
            ]
        },
    )
    monkeypatch.setattr(
        FastF1TelemetryProvider,
        "_driver_directory",
        staticmethod(lambda _session_key: tmp_path),
    )

    exports = FastF1TelemetryProvider._stream_channel_sync(
        11731, Session(), ["VER"], "car", chunk_rows=1
    )

    assert len(exports) == 1
    frame = pd.read_parquet(exports[0].path)
    assert frame[["LapNumber", "Speed", "Brake"]].to_dict("records") == [
        {"LapNumber": 1, "Speed": 300, "Brake": False}
    ]


def test_stint_without_recorded_laps_does_not_block_session():
    start = datetime(2025, 4, 20, 17, tzinfo=UTC)
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
            tzinfo=UTC,
        )
    )

    assert (
        first.event_id
        == second.event_id
    )

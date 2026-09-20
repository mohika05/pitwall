import asyncio
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.core.config import settings


def _clean_scalar(
    value: Any,
) -> Any:
    """
    Convert pandas/numpy values into JSON-safe
    Python values.
    """

    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(
        value,
        np.generic,
    ):
        return value.item()

    if isinstance(
        value,
        pd.Timestamp,
    ):
        return value.isoformat()

    if isinstance(
        value,
        pd.Timedelta,
    ):
        return value.total_seconds()

    return value


def _target_timestamp(
    timestamp: datetime,
) -> pd.Timestamp:
    """
    Convert an API datetime to UTC without timezone
    information so that it can be compared safely with
    FastF1's Date column.
    """

    target = pd.Timestamp(
        timestamp
    )

    if target.tzinfo is not None:
        target = (
            target
            .tz_convert("UTC")
            .tz_localize(None)
        )

    return target


@lru_cache(
    maxsize=128
)
def _load_frame(
    path_string: str,
) -> pd.DataFrame:
    path = Path(
        path_string
    )

    if not path.exists():
        raise FileNotFoundError(
            f"Telemetry file not found: {path}"
        )

    frame = pd.read_parquet(
        path
    )

    if "Date" not in frame.columns:
        raise ValueError(
            (
                "Telemetry file does not "
                f"contain Date: {path}"
            )
        )

    frame = frame.copy()

    # Normalize FastF1 timestamps into UTC-naive datetime64.
    frame["Date"] = pd.to_datetime(
        frame["Date"],
        utc=True,
        errors="coerce",
    ).dt.tz_localize(None)

    frame = (
        frame.dropna(
            subset=["Date"]
        )
        .sort_values(
            "Date"
        )
        .reset_index(
            drop=True
        )
    )

    return frame


def _nearest_row(
    frame: pd.DataFrame,
    timestamp: datetime,
    tolerance_seconds: float,
) -> tuple[
    pd.Series | None,
    float | None,
]:
    if frame.empty:
        return None, None

    target = _target_timestamp(
        timestamp
    )

    dates = frame["Date"]

    insertion_index = int(
        dates.searchsorted(
            target,
            side="left",
        )
    )

    candidate_indices: list[int] = []

    if (
        insertion_index
        < len(frame)
    ):
        candidate_indices.append(
            insertion_index
        )

    if insertion_index > 0:
        candidate_indices.append(
            insertion_index - 1
        )

    if not candidate_indices:
        return None, None

    best_index = min(
        candidate_indices,
        key=lambda index: abs(
            (
                frame.iloc[
                    index
                ]["Date"]
                - target
            ).total_seconds()
        ),
    )

    best_row = frame.iloc[
        best_index
    ]

    delta_seconds = abs(
        (
            best_row["Date"]
            - target
        ).total_seconds()
    )

    if (
        delta_seconds
        > tolerance_seconds
    ):
        return None, delta_seconds

    return (
        best_row,
        delta_seconds,
    )


class TelemetryService:
    CAR_FIELDS = (
        "Date",
        "SessionTime",
        "Time",
        "RPM",
        "Speed",
        "nGear",
        "Throttle",
        "Brake",
        "DRS",
        "LapNumber",
    )

    POSITION_FIELDS = (
        "Date",
        "SessionTime",
        "Time",
        "X",
        "Y",
        "Z",
        "Status",
        "LapNumber",
    )

    def _path(
        self,
        session_key: int,
        driver: str,
        kind: str,
    ) -> Path:
        return (
            settings.telemetry_dir
            / str(
                session_key
            )
            / (
                f"{driver.upper()}"
                f"_{kind}.parquet"
            )
        )

    async def _frame(
        self,
        session_key: int,
        driver: str,
        kind: str,
    ) -> pd.DataFrame:
        path = self._path(
            session_key,
            driver,
            kind,
        )

        return await asyncio.to_thread(
            _load_frame,
            str(path),
        )

    @staticmethod
    def _row_to_dict(
        row: pd.Series | None,
        fields: tuple[str, ...],
    ) -> dict[str, Any] | None:
        if row is None:
            return None

        return {
            field: _clean_scalar(
                row.get(
                    field
                )
            )
            for field in fields
            if field in row.index
        }

    async def snapshot(
        self,
        *,
        session_key: int,
        driver: str,
        timestamp: datetime,
        tolerance_seconds: float = 2.0,
    ) -> dict[str, Any]:
        car_frame, position_frame = (
            await asyncio.gather(
                self._frame(
                    session_key,
                    driver,
                    "car",
                ),
                self._frame(
                    session_key,
                    driver,
                    "position",
                ),
            )
        )

        car_row, car_delta = (
            await asyncio.to_thread(
                _nearest_row,
                car_frame,
                timestamp,
                tolerance_seconds,
            )
        )

        (
            position_row,
            position_delta,
        ) = await asyncio.to_thread(
            _nearest_row,
            position_frame,
            timestamp,
            tolerance_seconds,
        )

        return {
            "driver": (
                driver.upper()
            ),
            "requested_timestamp": (
                timestamp.isoformat()
            ),
            "car": self._row_to_dict(
                car_row,
                self.CAR_FIELDS,
            ),
            "position": (
                self._row_to_dict(
                    position_row,
                    self.POSITION_FIELDS,
                )
            ),
            "car_sample_age_seconds": (
                car_delta
            ),
            "position_sample_age_seconds": (
                position_delta
            ),
        }

    async def window(
        self,
        *,
        session_key: int,
        driver: str,
        start: datetime,
        end: datetime,
        max_points: int = 500,
    ) -> dict[str, Any]:
        if end <= start:
            raise ValueError(
                "end must be after start"
            )

        if (
            max_points < 10
            or max_points > 2000
        ):
            raise ValueError(
                (
                    "max_points must be "
                    "between 10 and 2000"
                )
            )

        car_frame, position_frame = (
            await asyncio.gather(
                self._frame(
                    session_key,
                    driver,
                    "car",
                ),
                self._frame(
                    session_key,
                    driver,
                    "position",
                ),
            )
        )

        start_ts = _target_timestamp(
            start
        )

        end_ts = _target_timestamp(
            end
        )

        car_window = car_frame[
            (
                car_frame["Date"]
                >= start_ts
            )
            & (
                car_frame["Date"]
                <= end_ts
            )
        ].copy()

        position_window = (
            position_frame[
                (
                    position_frame[
                        "Date"
                    ]
                    >= start_ts
                )
                & (
                    position_frame[
                        "Date"
                    ]
                    <= end_ts
                )
            ].copy()
        )

        car_window = (
            self._downsample(
                car_window,
                max_points,
            )
        )

        position_window = (
            self._downsample(
                position_window,
                max_points,
            )
        )

        return {
            "driver": (
                driver.upper()
            ),
            "start": (
                start.isoformat()
            ),
            "end": (
                end.isoformat()
            ),
            "car": (
                self._records(
                    car_window,
                    self.CAR_FIELDS,
                )
            ),
            "position": (
                self._records(
                    position_window,
                    self.POSITION_FIELDS,
                )
            ),
        }

    @staticmethod
    def _downsample(
        frame: pd.DataFrame,
        max_points: int,
    ) -> pd.DataFrame:
        if (
            frame.empty
            or len(frame)
            <= max_points
        ):
            return frame

        indices = np.linspace(
            0,
            len(frame) - 1,
            num=max_points,
            dtype=int,
        )

        return (
            frame.iloc[
                indices
            ]
            .drop_duplicates()
            .reset_index(
                drop=True
            )
        )

    @classmethod
    def _records(
        cls,
        frame: pd.DataFrame,
        fields: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        records: list[
            dict[str, Any]
        ] = []

        for _, row in (
            frame.iterrows()
        ):
            record = cls._row_to_dict(
                row,
                fields,
            )

            if record is not None:
                records.append(
                    record
                )

        return records

    async def track_shape(
        self,
        *,
        session_key: int,
        driver: str = "RUS",
        max_points: int = 400,
    ) -> dict[str, Any]:
        if (
            max_points < 100
            or max_points > 1000
        ):
            raise ValueError(
                "max_points must be between 100 and 1000"
            )

        frame = await self._frame(
            session_key,
            driver,
            "position",
        )

        required_columns = {
            "Date",
            "LapNumber",
            "X",
            "Y",
        }

        if not required_columns.issubset(
            frame.columns
        ):
            raise ValueError(
                "Position telemetry is missing required columns"
            )

        usable = frame.dropna(
            subset=[
                "Date",
                "LapNumber",
                "X",
                "Y",
            ]
        ).copy()

        usable = usable[
            usable["LapNumber"] > 1
        ]

        if usable.empty:
            raise ValueError(
                "No usable laps found for track shape"
            )

        candidates: list[
            tuple[float, int, pd.DataFrame]
        ] = []

        for (
            lap_number_raw,
            lap_frame,
        ) in usable.groupby(
            "LapNumber"
        ):
            lap_frame = (
                lap_frame
                .sort_values("Date")
                .copy()
            )

            if len(lap_frame) < 50:
                continue

            duration = (
                lap_frame["Date"].iloc[-1]
                - lap_frame["Date"].iloc[0]
            ).total_seconds()

            if duration <= 0:
                continue

            candidates.append(
                (
                    duration,
                    int(lap_number_raw),
                    lap_frame,
                )
            )

        if not candidates:
            raise ValueError(
                "No complete lap found for track shape"
            )

        # Fastest sufficiently complete lap is a good choice:
        # it avoids most pit / safety-car / slow laps.
        (
            _,
            lap_number,
            track_frame,
        ) = min(
            candidates,
            key=lambda item: item[0],
        )

        track_frame = (
            self._downsample(
                track_frame,
                max_points,
            )
        )

        points: list[
            dict[str, Any]
        ] = []

        for _, row in (
            track_frame.iterrows()
        ):
            points.append(
                {
                    "x": _clean_scalar(
                        row["X"]
                    ),
                    "y": _clean_scalar(
                        row["Y"]
                    ),
                    "z": (
                        _clean_scalar(
                            row.get("Z")
                        )
                        if "Z"
                        in row.index
                        else None
                    ),
                }
            )

        return {
            "session_key": (
                session_key
            ),
            "driver": (
                driver.upper()
            ),
            "lap_number": (
                lap_number
            ),
            "points": points,
        }

telemetry_service = (
    TelemetryService()
)
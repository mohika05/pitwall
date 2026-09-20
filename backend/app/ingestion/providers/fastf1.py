import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fastf1
import pandas as pd

from app.core.config import settings
from app.core.exceptions import ExternalDataError


logger = logging.getLogger(__name__)


CAR_COLUMNS = [
    "Date",
    "SessionTime",
    "Time",
    "RPM",
    "Speed",
    "nGear",
    "Throttle",
    "Brake",
    "DRS",
    "Source",
]

POSITION_COLUMNS = [
    "Date",
    "SessionTime",
    "Time",
    "X",
    "Y",
    "Z",
    "Status",
    "Source",
]


@dataclass
class DriverTelemetry:
    driver: str

    car_data: pd.DataFrame
    position_data: pd.DataFrame


@dataclass
class TelemetryExport:
    driver: str

    car_rows: int
    position_rows: int

    car_path: Path
    position_path: Path


class FastF1TelemetryProvider:
    """
    Historical high-frequency telemetry provider.

    OpenF1 remains the authoritative source for Pitwall's
    event/state reconstruction.

    FastF1 is used only for channels such as:

    - speed
    - RPM
    - gear
    - throttle
    - brake
    - DRS
    - X/Y/Z position

    These data are intentionally kept outside RaceEvent because
    they are high-frequency time series rather than domain events.
    """

    def __init__(self) -> None:
        settings.fastf1_cache_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        settings.telemetry_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        fastf1.Cache.enable_cache(
            str(
                settings.fastf1_cache_dir
            )
        )

    # ---------------------------------------------------------
    # SESSION LOADING
    # ---------------------------------------------------------

    @staticmethod
    def _load_session_sync(
        year: int,
        event: str,
        session_type: str,
    ) -> Any:
        logger.info(
            "Loading FastF1 session: %s %s %s",
            year,
            event,
            session_type,
        )

        try:
            session = fastf1.get_session(
                year,
                event,
                session_type,
            )

            session.load(
                laps=True,
                telemetry=True,
                weather=False,
                messages=False,
            )

        except Exception as exc:
            raise ExternalDataError(
                (
                    "FastF1 failed to load "
                    f"{year} {event} "
                    f"{session_type}"
                )
            ) from exc

        return session

    async def load_session(
        self,
        year: int,
        event: str,
        session_type: str = "R",
    ) -> Any:
        """
        FastF1 is blocking, so move the loading work off the
        asyncio event loop.
        """

        return await asyncio.to_thread(
            self._load_session_sync,
            year,
            event,
            session_type,
        )

    # ---------------------------------------------------------
    # HELPERS
    # ---------------------------------------------------------

    @staticmethod
    def _clean_car_data(
        frame: pd.DataFrame,
        lap_number: int,
    ) -> pd.DataFrame:
        if frame.empty:
            return frame.copy()

        available_columns = [
            column
            for column in CAR_COLUMNS
            if column in frame.columns
        ]

        cleaned = frame[
            available_columns
        ].copy()

        cleaned["LapNumber"] = (
            lap_number
        )

        return cleaned

    @staticmethod
    def _clean_position_data(
        frame: pd.DataFrame,
        lap_number: int,
    ) -> pd.DataFrame:
        if frame.empty:
            return frame.copy()

        available_columns = [
            column
            for column in POSITION_COLUMNS
            if column in frame.columns
        ]

        cleaned = frame[
            available_columns
        ].copy()

        cleaned["LapNumber"] = (
            lap_number
        )

        return cleaned

    # ---------------------------------------------------------
    # DRIVER EXTRACTION
    # ---------------------------------------------------------

    @classmethod
    def _extract_driver_sync(
        cls,
        session: Any,
        driver: str,
    ) -> DriverTelemetry:
        """
        Extract an entire race's telemetry for one driver.

        We use FastF1's public per-lap telemetry API rather than
        depending directly on FastF1's internal storage objects.
        """

        try:
            driver_laps = (
                session.laps.pick_drivers(
                    driver
                )
            )

        except Exception as exc:
            raise ExternalDataError(
                (
                    "Unable to select FastF1 "
                    f"laps for driver {driver}"
                )
            ) from exc

        if driver_laps.empty:
            raise ExternalDataError(
                (
                    "FastF1 returned no laps "
                    f"for driver {driver}"
                )
            )

        car_frames: list[
            pd.DataFrame
        ] = []

        position_frames: list[
            pd.DataFrame
        ] = []

        for _, lap in (
            driver_laps.iterlaps()
        ):
            lap_number_raw = lap.get(
                "LapNumber"
            )

            if pd.isna(
                lap_number_raw
            ):
                continue

            lap_number = int(
                lap_number_raw
            )

            # ---------------------------------------------
            # CAR TELEMETRY
            # ---------------------------------------------

            try:
                car_data = (
                    lap.get_car_data(
                        pad=0
                    )
                )

            except Exception as exc:
                logger.warning(
                    (
                        "Unable to load car data "
                        "for driver %s lap %s: %s"
                    ),
                    driver,
                    lap_number,
                    exc,
                )

                car_data = (
                    pd.DataFrame()
                )

            if not car_data.empty:
                cleaned_car = (
                    cls._clean_car_data(
                        car_data,
                        lap_number,
                    )
                )

                car_frames.append(
                    cleaned_car
                )

            # ---------------------------------------------
            # POSITION TELEMETRY
            # ---------------------------------------------

            try:
                position_data = (
                    lap.get_pos_data(
                        pad=0
                    )
                )

            except Exception as exc:
                logger.warning(
                    (
                        "Unable to load position "
                        "data for driver %s "
                        "lap %s: %s"
                    ),
                    driver,
                    lap_number,
                    exc,
                )

                position_data = (
                    pd.DataFrame()
                )

            if not position_data.empty:
                cleaned_position = (
                    cls._clean_position_data(
                        position_data,
                        lap_number,
                    )
                )

                position_frames.append(
                    cleaned_position
                )

        if car_frames:
            car = pd.concat(
                car_frames,
                ignore_index=True,
            )

            if "Date" in car.columns:
                car = (
                    car.sort_values(
                        "Date"
                    )
                    .drop_duplicates(
                        subset=["Date"],
                        keep="first",
                    )
                    .reset_index(
                        drop=True
                    )
                )

        else:
            car = pd.DataFrame()

        if position_frames:
            position = pd.concat(
                position_frames,
                ignore_index=True,
            )

            if "Date" in position.columns:
                position = (
                    position.sort_values(
                        "Date"
                    )
                    .drop_duplicates(
                        subset=["Date"],
                        keep="first",
                    )
                    .reset_index(
                        drop=True
                    )
                )

        else:
            position = pd.DataFrame()

        if car.empty:
            raise ExternalDataError(
                (
                    "FastF1 produced no car "
                    f"telemetry for driver {driver}"
                )
            )

        if position.empty:
            raise ExternalDataError(
                (
                    "FastF1 produced no position "
                    f"telemetry for driver {driver}"
                )
            )

        return DriverTelemetry(
            driver=driver,
            car_data=car,
            position_data=position,
        )

    async def extract_driver(
        self,
        session: Any,
        driver: str,
    ) -> DriverTelemetry:
        return await asyncio.to_thread(
            self._extract_driver_sync,
            session,
            driver,
        )

    # ---------------------------------------------------------
    # PERSISTENCE
    # ---------------------------------------------------------

    @staticmethod
    def _driver_directory(
        session_key: int,
    ) -> Path:
        directory = (
            settings.telemetry_dir
            / str(session_key)
        )

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        return directory

    @classmethod
    def _export_driver_sync(
        cls,
        session_key: int,
        telemetry: DriverTelemetry,
    ) -> TelemetryExport:
        directory = (
            cls._driver_directory(
                session_key
            )
        )

        safe_driver = (
            telemetry.driver
            .upper()
            .replace(
                "/",
                "_",
            )
        )

        car_path = (
            directory
            / f"{safe_driver}_car.parquet"
        )

        position_path = (
            directory
            / (
                f"{safe_driver}"
                "_position.parquet"
            )
        )

        telemetry.car_data.to_parquet(
            car_path,
            index=False,
        )

        telemetry.position_data.to_parquet(
            position_path,
            index=False,
        )

        return TelemetryExport(
            driver=telemetry.driver,
            car_rows=len(
                telemetry.car_data
            ),
            position_rows=len(
                telemetry.position_data
            ),
            car_path=car_path,
            position_path=position_path,
        )

    async def export_driver(
        self,
        session_key: int,
        telemetry: DriverTelemetry,
    ) -> TelemetryExport:
        return await asyncio.to_thread(
            self._export_driver_sync,
            session_key,
            telemetry,
        )
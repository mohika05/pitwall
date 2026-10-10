import asyncio
import gc
import logging
import shutil
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fastf1
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from fastf1 import api as fastf1_api
from fastf1.exceptions import DataNotLoadedError

from app.core.config import settings
from app.core.exceptions import ExternalDataError
from app.storage.object_store import object_store, telemetry_key

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


@dataclass
class TelemetryChannelExport:
    driver: str
    channel: str
    rows: int
    path: Path


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

        fastf1.Cache.enable_cache(
            str(settings.fastf1_cache_dir),
            use_requests_cache=settings.fastf1_use_requests_cache,
        )

    # ---------------------------------------------------------
    # SESSION LOADING
    # ---------------------------------------------------------

    @staticmethod
    def _session_name(year: int, session_type: str) -> str:
        # Formula 1 renamed Sprint Shootout to Sprint Qualifying in 2024.
        # OpenF1 uses the newer label for historical sessions as well, while
        # FastF1 retains the name used during each season.
        if year <= 2023 and session_type.casefold() == "sprint qualifying":
            return "Sprint Shootout"
        return session_type

    @staticmethod
    def _load_session_sync(
        year: int,
        event: str,
        session_type: str,
        telemetry: bool = True,
    ) -> Any:
        session_type = FastF1TelemetryProvider._session_name(year, session_type)

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
                telemetry=telemetry,
                weather=False,
                messages=False,
            )
            # FastF1 may log an archive-loading failure and return from load()
            # without raising. Touching laps here turns that incomplete result into
            # an explicit, retryable provider failure before preparation continues.
            _ = session.laps

        except DataNotLoadedError as exc:
            raise ExternalDataError(
                "FastF1 telemetry archive is not ready for "
                f"{year} {event} {session_type}; "
                "scheduled ingestion will retry"
            ) from exc
        except Exception as exc:
            raise ExternalDataError(
                "FastF1 failed to load "
                f"{year} {event} "
                f"{session_type}"
            ) from exc

        return session

    async def load_session(
        self,
        year: int,
        event: str,
        session_type: str = "R",
        telemetry: bool = True,
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
            telemetry,
        )

    # ---------------------------------------------------------
    # MEMORY-BOUNDED SESSION EXTRACTION
    # ---------------------------------------------------------

    @staticmethod
    def _driver_number(session: Any, driver: str) -> str:
        try:
            return str(session.get_driver(driver)["DriverNumber"])
        except Exception as exc:
            raise ExternalDataError(f"FastF1 has no driver number for {driver}") from exc

    @staticmethod
    def _lap_boundaries(session: Any, drivers: list[str]) -> dict[str, tuple[list[float], list]]:
        boundaries: dict[str, tuple[list[float], list]] = {}
        for driver in drivers:
            number = FastF1TelemetryProvider._driver_number(session, driver)
            laps = session.laps.pick_drivers(driver).dropna(
                subset=["LapNumber", "LapStartTime"]
            )
            rows = sorted(
                (
                    float(row["LapStartTime"].total_seconds()),
                    None
                    if pd.isna(row.get("Time"))
                    else float(row["Time"].total_seconds()),
                    int(row["LapNumber"]),
                )
                for _, row in laps.iterrows()
            )
            if rows:
                boundaries[number] = ([row[0] for row in rows], rows)
        return boundaries

    @staticmethod
    def _lap_number_at(
        boundaries: tuple[list[float], list] | None,
        session_seconds: float,
    ) -> int | None:
        if not boundaries:
            return None
        starts, rows = boundaries
        index = bisect_right(starts, session_seconds) - 1
        if index < 0:
            return None
        _, end, lap_number = rows[index]
        if end is not None and session_seconds > end:
            return None
        return lap_number

    @classmethod
    def _stream_channel_sync(
        cls,
        session_key: int,
        session: Any,
        drivers: list[str],
        channel: str,
        chunk_rows: int = 1000,
    ) -> list[TelemetryChannelExport]:
        """Decode a FastF1 stream into bounded per-driver Parquet batches."""
        endpoint = "car_data" if channel == "car" else "position"
        try:
            response = fastf1_api.fetch_page(session.api_path, endpoint)
        except Exception as exc:
            raise ExternalDataError(f"FastF1 failed to fetch {channel} telemetry") from exc
        if response is None:
            raise ExternalDataError(
                f"FastF1 {channel} telemetry archive is not ready; scheduled ingestion will retry"
            )

        boundaries = cls._lap_boundaries(session, drivers)
        number_to_driver = {
            cls._driver_number(session, driver): driver for driver in drivers
        }
        columns = [*(CAR_COLUMNS if channel == "car" else POSITION_COLUMNS), "LapNumber"]
        buffers: dict[str, list[dict[str, Any]]] = {driver: [] for driver in drivers}
        writers: dict[str, pq.ParquetWriter] = {}
        paths: dict[str, Path] = {}
        counts = {driver: 0 for driver in drivers}
        directory = cls._driver_directory(session_key)

        def flush(driver: str) -> None:
            rows = buffers[driver]
            if not rows:
                return
            frame = pd.DataFrame.from_records(rows, columns=columns)
            table = pa.Table.from_pandas(frame, preserve_index=False)
            if driver not in writers:
                safe_driver = driver.upper().replace("/", "_")
                path = directory / f"{safe_driver}_{channel}.parquet"
                paths[driver] = path
                writers[driver] = pq.ParquetWriter(path, table.schema, compression="snappy")
            writers[driver].write_table(table)
            counts[driver] += len(rows)
            rows.clear()

        decode_errors = 0
        try:
            for record in response:
                try:
                    session_time = fastf1_api.to_timedelta(record[:12])
                    session_seconds = float(session_time.total_seconds())
                    payload = fastf1_api.parse(record[12:], zipped=True)
                    if channel == "car":
                        samples = payload["Entries"]
                        for sample in samples:
                            date = fastf1_api.to_datetime(sample["Utc"])
                            for number, values in sample["Cars"].items():
                                driver = number_to_driver.get(number)
                                lap_number = cls._lap_number_at(
                                    boundaries.get(number), session_seconds
                                )
                                if driver is None or lap_number is None:
                                    continue
                                channels = values.get("Channels", {})
                                try:
                                    row = {
                                        "Date": date,
                                        "SessionTime": session_time,
                                        "Time": session_time,
                                        "RPM": int(channels["0"]),
                                        "Speed": int(channels["2"]),
                                        "nGear": int(channels["3"]),
                                        "Throttle": int(channels["4"]),
                                        "Brake": bool(int(channels["5"])),
                                        "DRS": int(channels.get("45", 0)),
                                        "Source": "car",
                                        "LapNumber": lap_number,
                                    }
                                except (KeyError, TypeError, ValueError):
                                    continue
                                buffers[driver].append(row)
                                if len(buffers[driver]) >= chunk_rows:
                                    flush(driver)
                    else:
                        for sample in payload["Position"]:
                            date = fastf1_api.to_datetime(sample["Timestamp"])
                            for number, values in sample["Entries"].items():
                                driver = number_to_driver.get(number)
                                lap_number = cls._lap_number_at(
                                    boundaries.get(number), session_seconds
                                )
                                if driver is None or lap_number is None:
                                    continue
                                try:
                                    status = values.get("Status")
                                    if str(status).isdigit():
                                        status = "OffTrack" if int(status) else "OnTrack"
                                    status = str(status or "OffTrack")
                                    row = {
                                        "Date": date,
                                        "SessionTime": session_time,
                                        "Time": session_time,
                                        "X": int(values["X"]),
                                        "Y": int(values["Y"]),
                                        "Z": int(values["Z"]),
                                        "Status": status,
                                        "Source": "pos",
                                        "LapNumber": lap_number,
                                    }
                                except (KeyError, TypeError, ValueError):
                                    continue
                                buffers[driver].append(row)
                                if len(buffers[driver]) >= chunk_rows:
                                    flush(driver)
                except Exception:  # noqa: BLE001 - skip malformed provider records
                    decode_errors += 1
            for driver in drivers:
                flush(driver)
        finally:
            for writer in writers.values():
                writer.close()
            response.clear()
            gc.collect()

        if decode_errors:
            logger.warning(
                "%s telemetry skipped %s malformed records", channel, decode_errors
            )
        return [
            TelemetryChannelExport(
                driver=driver,
                channel=channel,
                rows=counts[driver],
                path=paths[driver],
            )
            for driver in drivers
            if counts[driver] and driver in paths
        ]

    async def export_channel_streaming(
        self,
        session_key: int,
        session: Any,
        drivers: list[str],
        channel: str,
    ) -> tuple[list[TelemetryChannelExport], list[dict[str, Any]]]:
        exports = await asyncio.to_thread(
            self._stream_channel_sync,
            session_key,
            session,
            drivers,
            channel,
        )
        objects = []
        for exported in exports:
            objects.append(
                await object_store.publish(
                    exported.path,
                    telemetry_key(session_key, exported.driver, channel),
                )
            )
        return exports, objects

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
                "Unable to select FastF1 "
                f"laps for driver {driver}"
            ) from exc

        if driver_laps.empty:
            raise ExternalDataError(
                "FastF1 returned no laps "
                f"for driver {driver}"
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

            except Exception as exc:  # noqa: BLE001 - tolerate per-lap provider gaps
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

            except Exception as exc:  # noqa: BLE001 - tolerate per-lap provider gaps
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
                "FastF1 produced no car "
                f"telemetry for driver {driver}"
            )

        if position.empty:
            raise ExternalDataError(
                "FastF1 produced no position "
                f"telemetry for driver {driver}"
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
        directory = object_store.local_path(f"telemetry/{session_key}")

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
    ) -> tuple[TelemetryExport, list[dict[str, Any]]]:
        exported = await asyncio.to_thread(
            self._export_driver_sync,
            session_key,
            telemetry,
        )
        car = await object_store.publish(
            exported.car_path,
            telemetry_key(session_key, telemetry.driver, "car"),
        )
        position = await object_store.publish(
            exported.position_path,
            telemetry_key(session_key, telemetry.driver, "position"),
        )
        return exported, [car, position]

    @staticmethod
    async def cleanup_session_cache(session: Any) -> int:
        """Delete only the decoded FastF1 cache for one verified session."""
        api_path = getattr(session, "api_path", "")
        relative = api_path.strip("/")
        if relative.startswith("static/"):
            relative = relative.removeprefix("static/")
        target = (settings.fastf1_cache_dir / relative).resolve()
        root = settings.fastf1_cache_dir.resolve()
        if root not in target.parents or not target.is_dir():
            return 0
        size = sum(path.stat().st_size for path in target.rglob("*") if path.is_file())
        await asyncio.to_thread(shutil.rmtree, target)
        parent = target.parent
        while parent != root and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
        return size

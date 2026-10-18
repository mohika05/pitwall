import asyncio
import logging
import time
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Self

import httpx
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from app.core.config import settings
from app.core.exceptions import ExternalDataError, ResourceNotFoundError
from app.ingestion.providers.base import RaceDataProvider, SessionDataBundle
from app.services.provider_rate import request_slot
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
    "LapNumber",
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
    "LapNumber",
]


@dataclass
class OpenF1TelemetryChannelExport:
    driver: str
    channel: str
    rows: int
    path: Path


def _parse_datetime(value: str) -> datetime:
    """
    Convert an ISO-8601 OpenF1 timestamp into a Python datetime.
    """
    return datetime.fromisoformat(value)


def _derive_starting_grid_from_positions(
    positions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Derive the initial grid from the earliest position record
    available for each driver.

    This acts as a fallback when OpenF1's starting_grid endpoint
    is unavailable for a session.
    """

    first_position: dict[int, dict[str, Any]] = {}

    sorted_positions = sorted(
        positions,
        key=lambda row: row.get("date") or "",
    )

    for row in sorted_positions:
        driver_number_raw = row.get("driver_number")
        position_raw = row.get("position")

        if (
            driver_number_raw is None
            or position_raw is None
        ):
            continue

        driver_number = int(driver_number_raw)

        # We only want the earliest known position.
        if driver_number in first_position:
            continue

        first_position[driver_number] = {
            "driver_number": driver_number,
            "position": int(position_raw),
            "meeting_key": int(row["meeting_key"]),
            "session_key": int(row["session_key"]),
        }

    return sorted(
        first_position.values(),
        key=lambda row: row["position"],
    )


class OpenF1Provider(RaceDataProvider):
    def __init__(self) -> None:
        base_url = (
            settings.openf1_base_url.rstrip("/")
            + "/"
        )

        headers = {
            "Accept": "application/json",
            "User-Agent": "pitwall/0.1",
        }

        self.client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(
                settings.openf1_timeout_seconds
            ),
            headers=headers,
        )

        self._rate_lock = asyncio.Lock()
        self._last_request_started = 0.0

    async def __aenter__(
        self,
    ) -> Self:
        return self

    async def __aexit__(
        self,
        *_: object,
    ) -> None:
        await self.client.aclose()

    # ---------------------------------------------------------
    # RATE LIMITING
    # ---------------------------------------------------------

    async def _throttle(self) -> None:
        """
        Ensure requests are spaced out so that we stay below the
        configured OpenF1 request-rate limit.
        """

        async with self._rate_lock:
            elapsed = (
                time.monotonic()
                - self._last_request_started
            )

            delay = (
                settings.openf1_min_request_interval_seconds
                - elapsed
            )

            if delay > 0:
                await asyncio.sleep(delay)

            self._last_request_started = (
                time.monotonic()
            )

    # ---------------------------------------------------------
    # HTTP HELPERS
    # ---------------------------------------------------------

    async def _get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Perform an OpenF1 GET request.

        Retries:
        - network failures
        - timeouts
        - HTTP 429
        - HTTP 5xx

        Does NOT silently ignore HTTP 4xx responses.
        """

        last_error: Exception | None = None
        for attempt in range(
            settings.openf1_max_retries
        ):
            await request_slot()

            try:
                response = await self.client.get(
                    endpoint,
                    params=params,
                )

            except (
                httpx.TimeoutException,
                httpx.NetworkError,
            ) as exc:
                last_error = exc

                if (
                    attempt + 1
                    >= settings.openf1_max_retries
                ):
                    break

                wait_seconds = 2 ** attempt

                logger.warning(
                    (
                        "Network error requesting "
                        "OpenF1 endpoint %s. "
                        "Retrying in %ss."
                    ),
                    endpoint,
                    wait_seconds,
                )

                await asyncio.sleep(
                    wait_seconds
                )

                continue

            # ---------------------------------------------
            # RATE LIMIT
            # ---------------------------------------------

            if response.status_code == 429:
                retry_after_raw = (
                    response.headers.get(
                        "Retry-After",
                        "1",
                    )
                )

                try:
                    retry_after = float(
                        retry_after_raw
                    )
                except ValueError:
                    retry_after = 1.0

                wait_seconds = max(
                    retry_after,
                    1.0,
                ) * (attempt + 1)

                last_error = ExternalDataError(
                    (
                        "OpenF1 rate limit "
                        f"for endpoint {endpoint}"
                    ),
                    status_code=429,
                    response_text=(
                        response.text[:500]
                    ),
                )

                logger.warning(
                    (
                        "OpenF1 rate limit on %s. "
                        "Retrying in %.1fs."
                    ),
                    endpoint,
                    wait_seconds,
                )

                await asyncio.sleep(
                    wait_seconds
                )

                continue

            # ---------------------------------------------
            # SERVER ERRORS
            # ---------------------------------------------

            if response.status_code >= 500:
                last_error = ExternalDataError(
                    (
                        "OpenF1 server error "
                        f"{response.status_code} "
                        f"for endpoint {endpoint}"
                    ),
                    status_code=(
                        response.status_code
                    ),
                    response_text=(
                        response.text[:500]
                    ),
                )

                if (
                    attempt + 1
                    >= settings.openf1_max_retries
                ):
                    break

                wait_seconds = 2 ** attempt

                logger.warning(
                    (
                        "OpenF1 server error %s "
                        "on endpoint %s. "
                        "Retrying in %ss."
                    ),
                    response.status_code,
                    endpoint,
                    wait_seconds,
                )

                await asyncio.sleep(
                    wait_seconds
                )

                continue

            # ---------------------------------------------
            # CLIENT ERRORS
            # ---------------------------------------------

            if response.status_code >= 400:
                raise ExternalDataError(
                    (
                        "OpenF1 returned "
                        f"{response.status_code} "
                        f"for endpoint {endpoint}"
                    ),
                    status_code=(
                        response.status_code
                    ),
                    response_text=(
                        response.text[:500]
                    ),
                )

            # ---------------------------------------------
            # SUCCESS
            # ---------------------------------------------

            try:
                payload = response.json()

            except ValueError as exc:
                raise ExternalDataError(
                    (
                        "OpenF1 returned invalid "
                        f"JSON for endpoint {endpoint}"
                    ),
                    status_code=(
                        response.status_code
                    ),
                    response_text=(
                        response.text[:500]
                    ),
                ) from exc

            if not isinstance(payload, list):
                raise ExternalDataError(
                    (
                        "Unexpected OpenF1 "
                        f"response from {endpoint}: "
                        "expected list, received "
                        f"{type(payload).__name__}"
                    ),
                    status_code=(
                        response.status_code
                    ),
                    response_text=(
                        response.text[:500]
                    ),
                )

            return payload

        raise ExternalDataError(
            (
                "OpenF1 request failed after "
                f"{settings.openf1_max_retries} "
                f"attempts for endpoint "
                f"{endpoint}"
            ),
            status_code=(
                last_error.status_code
                if isinstance(
                    last_error,
                    ExternalDataError,
                )
                else None
            ),
            response_text=(
                last_error.response_text
                if isinstance(
                    last_error,
                    ExternalDataError,
                )
                else None
            ),
        ) from last_error

    async def _get_optional(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch an optional OpenF1 resource.

        Only a real 404 is treated as "resource unavailable".
        Authentication, rate-limit and server errors still propagate.
        """

        try:
            return await self._get(
                endpoint,
                params,
            )

        except ExternalDataError as exc:
            if exc.status_code == 404:
                logger.warning(
                    (
                        "Optional OpenF1 endpoint "
                        "%s returned 404"
                    ),
                    endpoint,
                )

                return []

            raise

    # ---------------------------------------------------------
    # SESSION DISCOVERY
    # ---------------------------------------------------------

    async def find_race_session(
        self,
        year: int,
        country_name: str,
    ) -> dict[str, Any]:
        """
        Find the non-cancelled Race session for a country/year.
        """

        rows = await self._get(
            "sessions",
            {
                "year": year,
                "country_name": country_name,
                "session_name": "Race",
            },
        )

        rows = [
            row
            for row in rows
            if not bool(
                row.get(
                    "is_cancelled",
                    False,
                )
            )
        ]

        if not rows:
            raise ResourceNotFoundError(
                "No Race session found "
                f"for {country_name} {year}"
            )

        rows.sort(
            key=lambda row: (
                row.get("date_start")
                or ""
            )
        )

        return rows[-1]

    # ---------------------------------------------------------
    # HIGH-FREQUENCY DATA
    # ---------------------------------------------------------

    async def _high_frequency_sample(
        self,
        endpoint: str,
        session_key: int,
        driver_number: int,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        """
        Fetch a small time-window sample of high-frequency
        telemetry/location data.
        """

        return await self._get(
            endpoint,
            {
                "session_key": session_key,
                "driver_number": (
                    driver_number
                ),
                "date>=": start.isoformat(),
                "date<": end.isoformat(),
            },
        )

    # ---------------------------------------------------------
    # HISTORICAL TELEMETRY FALLBACK
    # ---------------------------------------------------------

    @staticmethod
    def _lap_boundaries(
        laps: list[dict[str, Any]],
    ) -> dict[int, tuple[list[datetime], list[int]]]:
        """Build per-driver lap starts for assigning high-frequency samples."""
        grouped: dict[int, list[tuple[datetime, int]]] = {}
        for lap in laps:
            number = lap.get("driver_number")
            lap_number = lap.get("lap_number")
            started = lap.get("date_start")
            if number is None or lap_number is None or not started:
                continue
            try:
                row = (_parse_datetime(str(started)), int(lap_number))
            except (TypeError, ValueError):
                continue
            grouped.setdefault(int(number), []).append(row)

        boundaries: dict[int, tuple[list[datetime], list[int]]] = {}
        for number, rows in grouped.items():
            rows.sort(key=lambda row: row[0])
            boundaries[number] = (
                [row[0] for row in rows],
                [row[1] for row in rows],
            )
        return boundaries

    @staticmethod
    def _lap_number_at(
        boundaries: tuple[list[datetime], list[int]] | None,
        timestamp: datetime,
    ) -> int | None:
        if not boundaries:
            return None
        starts, lap_numbers = boundaries
        index = bisect_right(starts, timestamp) - 1
        return lap_numbers[index] if index >= 0 else None

    @staticmethod
    def _telemetry_path(session_key: int, driver: str, channel: str) -> Path:
        directory = object_store.local_path(f"telemetry/{session_key}")
        directory.mkdir(parents=True, exist_ok=True)
        safe_driver = driver.upper().replace("/", "_")
        return directory / f"{safe_driver}_{channel}.parquet"

    @classmethod
    def _write_telemetry_channel(
        cls,
        session_key: int,
        driver: str,
        driver_number: int,
        channel: str,
        rows: list[dict[str, Any]],
        session_start: datetime,
        boundaries: dict[int, tuple[list[datetime], list[int]]],
    ) -> OpenF1TelemetryChannelExport | None:
        records = cls._telemetry_records(
            channel, rows, driver_number, session_start, boundaries
        )
        if not records:
            return None
        columns = CAR_COLUMNS if channel == "car" else POSITION_COLUMNS
        frame = cls._telemetry_frame(records, columns)
        path = cls._telemetry_path(session_key, driver, channel)
        frame.to_parquet(path, index=False, compression="snappy")
        return OpenF1TelemetryChannelExport(
            driver=driver,
            channel=channel,
            rows=len(frame),
            path=path,
        )

    @staticmethod
    def _telemetry_frame(
        records: list[dict[str, Any]], columns: list[str]
    ) -> pd.DataFrame:
        return (
            pd.DataFrame.from_records(records, columns=columns)
            .sort_values("Date")
            .drop_duplicates(subset=["Date"], keep="first")
            .reset_index(drop=True)
        )

    @classmethod
    def _telemetry_records(
        cls,
        channel: str,
        rows: list[dict[str, Any]],
        driver_number: int,
        session_start: datetime,
        boundaries: dict[int, tuple[list[datetime], list[int]]],
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for sample in rows:
            raw_date = sample.get("date")
            if not raw_date:
                continue
            try:
                date = _parse_datetime(str(raw_date))
            except ValueError:
                continue
            lap_number = cls._lap_number_at(boundaries.get(driver_number), date)
            if lap_number is None:
                continue
            elapsed = date - session_start
            try:
                if channel == "car":
                    records.append(
                        {
                            "Date": date,
                            "SessionTime": elapsed,
                            "Time": elapsed,
                            "RPM": int(sample.get("rpm") or 0),
                            "Speed": int(sample.get("speed") or 0),
                            "nGear": int(sample.get("n_gear") or 0),
                            "Throttle": int(sample.get("throttle") or 0),
                            "Brake": bool(int(sample.get("brake") or 0)),
                            "DRS": int(sample.get("drs") or 0),
                            "Source": "car",
                            "LapNumber": lap_number,
                        }
                    )
                else:
                    records.append(
                        {
                            "Date": date,
                            "SessionTime": elapsed,
                            "Time": elapsed,
                            "X": int(sample["x"]),
                            "Y": int(sample["y"]),
                            "Z": int(sample.get("z") or 0),
                            "Status": "OnTrack",
                            "Source": "pos",
                            "LapNumber": lap_number,
                        }
                    )
            except (KeyError, TypeError, ValueError):
                continue
        return records

    async def _export_driver_channel_chunked(
        self,
        session_key: int,
        driver: str,
        driver_number: int,
        channel: str,
        session_start: datetime,
        session_end: datetime,
        boundaries: dict[int, tuple[list[datetime], list[int]]],
    ) -> OpenF1TelemetryChannelExport | None:
        """Write one driver incrementally so a race response never fills RAM."""
        endpoint = "car_data" if channel == "car" else "location"
        columns = CAR_COLUMNS if channel == "car" else POSITION_COLUMNS
        path = self._telemetry_path(session_key, driver, channel)
        partial_path = path.with_suffix(f"{path.suffix}.part")
        partial_path.unlink(missing_ok=True)
        writer: pq.ParquetWriter | None = None
        rows_written = 0
        cursor = session_start
        chunk = timedelta(minutes=15)
        try:
            while cursor < session_end:
                chunk_end = min(cursor + chunk, session_end)
                rows = await self._get(
                    endpoint,
                    {
                        "session_key": session_key,
                        "driver_number": driver_number,
                        "date>=": cursor.isoformat(),
                        "date<": chunk_end.isoformat(),
                    },
                )
                records = self._telemetry_records(
                    channel,
                    rows,
                    driver_number,
                    session_start,
                    boundaries,
                )
                del rows
                if records:
                    frame = self._telemetry_frame(records, columns)
                    del records
                    table = pa.Table.from_pandas(frame, preserve_index=False)
                    del frame
                    if writer is None:
                        writer = pq.ParquetWriter(
                            partial_path, table.schema, compression="snappy"
                        )
                    writer.write_table(table)
                    rows_written += table.num_rows
                    del table
                cursor = chunk_end
        finally:
            if writer is not None:
                writer.close()

        if rows_written == 0:
            partial_path.unlink(missing_ok=True)
            return None
        partial_path.replace(path)
        return OpenF1TelemetryChannelExport(
            driver=driver,
            channel=channel,
            rows=rows_written,
            path=path,
        )

    async def export_channel_streaming(
        self,
        session_key: int,
        bundle: SessionDataBundle,
        drivers: list[str],
        channel: str,
    ) -> tuple[list[OpenF1TelemetryChannelExport], list[dict[str, Any]]]:
        """Export one OpenF1 channel a driver at a time to bound memory use."""
        number_by_driver = {
            str(row.get("name_acronym") or "").upper(): int(row["driver_number"])
            for row in bundle.drivers
            if row.get("name_acronym") and row.get("driver_number") is not None
        }
        boundaries = self._lap_boundaries(bundle.laps)
        session_start = _parse_datetime(str(bundle.session["date_start"]))
        raw_end = bundle.session.get("date_end")
        if raw_end:
            session_end = _parse_datetime(str(raw_end))
        else:
            latest_start = max(
                (dates[-1] for dates, _ in boundaries.values() if dates),
                default=session_start,
            )
            session_end = latest_start + timedelta(minutes=10)
        exports: list[OpenF1TelemetryChannelExport] = []
        objects: list[dict[str, Any]] = []

        for driver in drivers:
            driver_number = number_by_driver.get(driver.upper())
            if driver_number is None or driver_number not in boundaries:
                continue
            exported = await self._export_driver_channel_chunked(
                session_key,
                driver,
                driver_number,
                channel,
                session_start,
                session_end,
                boundaries,
            )
            if exported is None:
                continue
            exports.append(exported)
            objects.append(
                await object_store.publish(
                    exported.path,
                    telemetry_key(session_key, driver, channel),
                )
            )
        return exports, objects

    # ---------------------------------------------------------
    # FULL SESSION BUNDLE
    # ---------------------------------------------------------

    async def get_session(self, session_key: int) -> dict[str, Any]:
        rows = await self._get("sessions", {"session_key": session_key})
        if not rows:
            raise ValueError(f"Session {session_key} was not found")
        return rows[0]

    async def fetch_bundle(
        self,
        session: dict[str, Any],
    ) -> SessionDataBundle:
        session_key = int(
            session["session_key"]
        )

        meeting_key = int(
            session["meeting_key"]
        )

        logger.info(
            "Fetching OpenF1 session %s",
            session_key,
        )

        # -----------------------------------------------------
        # MEETING
        # -----------------------------------------------------

        meeting_rows = await self._get(
            "meetings",
            {
                "meeting_key": meeting_key
            },
        )

        if not meeting_rows:
            raise ResourceNotFoundError(
                f"Meeting {meeting_key} "
                "was not found"
            )

        # -----------------------------------------------------
        # CORE HISTORICAL DATA
        # -----------------------------------------------------

        drivers = await self._get(
            "drivers",
            {
                "session_key": session_key
            },
        )

        # A small number of historical sessions have no OpenF1 laps resource
        # even though their other timing feeds and FastF1 telemetry exist.
        # Keep preparing those sessions from the available sources.
        laps = await self._get_optional(
            "laps",
            {
                "session_key": session_key
            },
        )

        # Some historical sessions publish laps, stints and results without the
        # position feed. Strategy analysis remains usable without position-change
        # events, so do not block the whole archive on this optional resource.
        positions = await self._get_optional(
            "position",
            {
                "session_key": session_key
            },
        )

        # Practice/qualifying may not publish race-gap intervals.
        intervals = await self._get_optional(
            "intervals",
            {
                "session_key": session_key
            },
        )

        stints = await self._get(
            "stints",
            {
                "session_key": session_key
            },
        )

        # Testing/practice sessions may not publish pit-stop records.
        pits = await self._get_optional(
            "pit",
            {
                "session_key": session_key
            },
        )

        race_control = await self._get(
            "race_control",
            {
                "session_key": session_key
            },
        )

        weather = await self._get(
            "weather",
            {
                "session_key": session_key
            },
        )

        # -----------------------------------------------------
        # STARTING GRID
        # -----------------------------------------------------

        starting_grid = (
            await self._get_optional(
                "starting_grid",
                {
                    "session_key": (
                        session_key
                    )
                },
            )
        )

        if not starting_grid:
            logger.warning(
                (
                    "Starting-grid endpoint "
                    "unavailable for session %s. "
                    "Deriving grid from earliest "
                    "position records."
                ),
                session_key,
            )

            starting_grid = (
                _derive_starting_grid_from_positions(
                    positions
                )
            )

        logger.info(
            "Starting grid contains %d drivers",
            len(starting_grid),
        )

        # -----------------------------------------------------
        # OFFICIAL RESULT
        # -----------------------------------------------------

        session_result = (
            await self._get_optional(
                "session_result",
                {
                    "session_key": (
                        session_key
                    )
                },
            )
        )

        if not session_result:
            logger.warning(
                (
                    "Official session result "
                    "unavailable for session %s"
                ),
                session_key,
            )

        # -----------------------------------------------------
        # HIGH-FREQUENCY SAMPLE
        # -----------------------------------------------------

        car_data_sample: list[
            dict[str, Any]
        ] = []

        location_sample: list[
            dict[str, Any]
        ] = []

        first_timed_lap = next(
            (
                lap
                for lap in laps
                if (
                    lap.get("date_start")
                    and lap.get(
                        "driver_number"
                    )
                    is not None
                )
            ),
            None,
        )

        if first_timed_lap is None:
            logger.warning(
                (
                    "No timed lap found for "
                    "session %s. "
                    "Skipping high-frequency "
                    "data probe."
                ),
                session_key,
            )

        else:
            sample_start = _parse_datetime(
                first_timed_lap[
                    "date_start"
                ]
            )

            sample_end = (
                sample_start
                + timedelta(minutes=1)
            )

            driver_number = int(
                first_timed_lap[
                    "driver_number"
                ]
            )

            logger.info(
                (
                    "Probing high-frequency "
                    "data for driver %s "
                    "between %s and %s"
                ),
                driver_number,
                sample_start.isoformat(),
                sample_end.isoformat(),
            )

            # ---------------------------------------------
            # CAR TELEMETRY SAMPLE
            # ---------------------------------------------

            try:
                car_data_sample = (
                    await self._high_frequency_sample(
                        endpoint="car_data",
                        session_key=session_key,
                        driver_number=(
                            driver_number
                        ),
                        start=sample_start,
                        end=sample_end,
                    )
                )

                logger.info(
                    (
                        "Fetched %d car-data "
                        "samples"
                    ),
                    len(car_data_sample),
                )

            except ExternalDataError as exc:
                logger.warning(
                    (
                        "Car-data probe failed "
                        "for session %s, "
                        "driver %s: "
                        "status=%s body=%r"
                    ),
                    session_key,
                    driver_number,
                    exc.status_code,
                    exc.response_text,
                )

                car_data_sample = []

            # ---------------------------------------------
            # LOCATION SAMPLE
            # ---------------------------------------------

            try:
                location_sample = (
                    await self._high_frequency_sample(
                        endpoint="location",
                        session_key=session_key,
                        driver_number=(
                            driver_number
                        ),
                        start=sample_start,
                        end=sample_end,
                    )
                )

                logger.info(
                    (
                        "Fetched %d location "
                        "samples"
                    ),
                    len(location_sample),
                )

            except ExternalDataError as exc:
                logger.warning(
                    (
                        "Location probe failed "
                        "for session %s, "
                        "driver %s: "
                        "status=%s body=%r"
                    ),
                    session_key,
                    driver_number,
                    exc.status_code,
                    exc.response_text,
                )

                location_sample = []

        # -----------------------------------------------------
        # FINAL BUNDLE
        # -----------------------------------------------------

        return SessionDataBundle(
            meeting=meeting_rows[0],
            session=session,

            drivers=drivers,
            laps=laps,
            positions=positions,
            intervals=intervals,
            stints=stints,
            pits=pits,
            race_control=race_control,
            weather=weather,

            starting_grid=starting_grid,
            session_result=session_result,

            car_data_sample=(
                car_data_sample
            ),
            location_sample=(
                location_sample
            ),
        )

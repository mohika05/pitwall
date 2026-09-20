import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import ExternalDataError, ResourceNotFoundError
from app.ingestion.providers.base import RaceDataProvider, SessionDataBundle


logger = logging.getLogger(__name__)


def _parse_datetime(value: str) -> datetime:
    """
    Convert an ISO-8601 OpenF1 timestamp into a Python datetime.
    """
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


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

        if settings.openf1_access_token:
            headers["Authorization"] = (
                f"Bearer "
                f"{settings.openf1_access_token}"
            )

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
    ) -> "OpenF1Provider":
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
            await self._throttle()

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
                (
                    "No Race session found "
                    f"for {country_name} {year}"
                )
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
    # FULL SESSION BUNDLE
    # ---------------------------------------------------------

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
                (
                    f"Meeting {meeting_key} "
                    "was not found"
                )
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

        laps = await self._get(
            "laps",
            {
                "session_key": session_key
            },
        )

        positions = await self._get(
            "position",
            {
                "session_key": session_key
            },
        )

        intervals = await self._get(
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

        pits = await self._get(
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
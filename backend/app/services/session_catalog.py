import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import text

from app.core.config import settings
from app.core.exceptions import ExternalDataError
from app.persistence.database import AsyncSessionLocal
from app.persistence.repositories.workspace_repository import workspace_repository


class SessionCatalogService:
    FIRST_SUPPORTED_YEAR = 2023

    # Stay safely below OpenF1's REST request-rate limit.
    MIN_REQUEST_INTERVAL_SECONDS = 0.45

    MAX_RETRIES = 4

    # Historical seasons can stay cached permanently.
    # The current season gets refreshed periodically.
    CURRENT_YEAR_CACHE_HOURS = 6

    def __init__(self) -> None:
        self.cache_dir = (
            settings.data_dir
            / "catalog"
        )

        self.cache_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        # Stops duplicate catalogue builds from happening
        # at the same time.
        self._catalogue_lock = asyncio.Lock()

        # Ensures OpenF1 catalogue requests are serialized.
        self._request_lock = asyncio.Lock()

        self._last_request_time = 0.0

    # =========================================================
    # YEARS
    # =========================================================

    def years(self) -> list[int]:
        current_year = datetime.now(
            timezone.utc
        ).year

        return list(
            range(
                self.FIRST_SUPPORTED_YEAR,
                current_year + 1,
            )
        )

    # =========================================================
    # CACHE
    # =========================================================

    def _cache_path(
        self,
        year: int,
    ) -> Path:
        return (
            self.cache_dir
            / f"{year}.json"
        )

    def _cache_is_valid(
        self,
        year: int,
        fetched_at: datetime,
    ) -> bool:
        current_year = datetime.now(
            timezone.utc
        ).year

        # Past seasons are effectively static.
        if year < current_year:
            return True

        age = (
            datetime.now(
                timezone.utc
            )
            - fetched_at
        )

        return (
            age
            < timedelta(
                hours=(
                    self.CURRENT_YEAR_CACHE_HOURS
                )
            )
        )

    def _load_cache(
        self,
        year: int,
    ) -> dict[str, Any] | None:
        path = self._cache_path(
            year
        )

        if not path.exists():
            return None

        try:
            with path.open(
                "r",
                encoding="utf-8",
            ) as file:
                wrapper = json.load(
                    file
                )

            fetched_at_raw = (
                wrapper.get(
                    "fetched_at"
                )
            )

            catalogue = (
                wrapper.get(
                    "catalogue"
                )
            )

            if (
                not fetched_at_raw
                or not isinstance(
                    catalogue,
                    dict,
                )
            ):
                return None

            fetched_at = (
                datetime.fromisoformat(
                    fetched_at_raw
                )
            )

            if (
                fetched_at.tzinfo
                is None
            ):
                fetched_at = (
                    fetched_at.replace(
                        tzinfo=timezone.utc
                    )
                )

            if not self._cache_is_valid(
                year,
                fetched_at,
            ):
                return None

            return catalogue

        except (
            OSError,
            ValueError,
            json.JSONDecodeError,
        ):
            return None

    def _save_cache(
        self,
        year: int,
        catalogue: dict[str, Any],
    ) -> None:
        path = self._cache_path(
            year
        )

        wrapper = {
            "fetched_at":
                datetime.now(
                    timezone.utc
                ).isoformat(),

            "catalogue":
                catalogue,
        }

        temporary_path = (
            path.with_suffix(
                ".tmp"
            )
        )

        with temporary_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                wrapper,
                file,
                indent=2,
            )

        temporary_path.replace(
            path
        )

    # =========================================================
    # RATE LIMITING
    # =========================================================

    async def _wait_for_request_slot(
        self,
    ) -> None:
        elapsed = (
            time.monotonic()
            - self._last_request_time
        )

        wait_seconds = (
            self.MIN_REQUEST_INTERVAL_SECONDS
            - elapsed
        )

        if wait_seconds > 0:
            await asyncio.sleep(
                wait_seconds
            )

    # =========================================================
    # OPENF1 REQUEST
    # =========================================================

    async def _get_openf1(
        self,
        endpoint: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        url = (
            f"{settings.openf1_base_url}/"
            f"{endpoint}"
        )

        headers: dict[str, str] = {
            "accept":
                "application/json",
        }

        if (
            settings.openf1_access_token
        ):
            headers[
                "Authorization"
            ] = (
                "Bearer "
                f"{settings.openf1_access_token}"
            )

        last_error: Exception | None = None

        for attempt in range(
            self.MAX_RETRIES
        ):
            try:
                async with self._request_lock:
                    await (
                        self._wait_for_request_slot()
                    )

                    async with httpx.AsyncClient(
                        timeout=(
                            settings
                            .openf1_timeout_seconds
                        )
                    ) as client:
                        response = (
                            await client.get(
                                url,
                                params=params,
                                headers=headers,
                            )
                        )

                    self._last_request_time = (
                        time.monotonic()
                    )

            except httpx.HTTPError as exc:
                last_error = exc

                if (
                    attempt
                    == self.MAX_RETRIES - 1
                ):
                    break

                await asyncio.sleep(
                    min(
                        2 ** attempt,
                        8,
                    )
                )

                continue

            # -------------------------------------------------
            # RATE LIMIT
            # -------------------------------------------------

            if (
                response.status_code
                == 429
            ):
                retry_after_raw = (
                    response.headers.get(
                        "Retry-After"
                    )
                )

                try:
                    retry_after = (
                        float(
                            retry_after_raw
                        )
                        if retry_after_raw
                        else None
                    )

                except ValueError:
                    retry_after = None

                wait_seconds = (
                    retry_after
                    if retry_after
                    is not None
                    else min(
                        2 ** (
                            attempt + 1
                        ),
                        15,
                    )
                )

                if (
                    attempt
                    == self.MAX_RETRIES - 1
                ):
                    raise ExternalDataError(
                        (
                            "OpenF1 rate limit "
                            f"reached for "
                            f"{endpoint}"
                        ),
                        status_code=429,
                        response_text=(
                            response.text
                        ),
                    )

                await asyncio.sleep(
                    wait_seconds
                )

                continue

            # -------------------------------------------------
            # OTHER HTTP ERRORS
            # -------------------------------------------------

            if (
                response.status_code
                >= 400
            ):
                raise ExternalDataError(
                    (
                        f"OpenF1 "
                        f"{endpoint} "
                        f"returned "
                        f"{response.status_code}"
                    ),
                    status_code=(
                        response.status_code
                    ),
                    response_text=(
                        response.text
                    ),
                )

            payload = response.json()

            if not isinstance(
                payload,
                list,
            ):
                raise ExternalDataError(
                    (
                        f"OpenF1 "
                        f"{endpoint} "
                        "returned unexpected data"
                    )
                )

            return payload

        raise ExternalDataError(
            (
                "Unable to retrieve "
                f"OpenF1 {endpoint}"
            )
        ) from last_error

    # =========================================================
    # LOCAL SESSION STATUS
    # =========================================================

    async def _local_session_keys(
        self,
    ) -> set[int]:
        async with (
            AsyncSessionLocal()
            as db
        ):
            result = (
                await db.execute(
                    text(
                        """
                        SELECT session_key
                        FROM sessions
                        """
                    )
                )
            )

            return {
                int(row[0])
                for row
                in result.fetchall()
            }

    def _legacy_telemetry_available(self, session_key: int) -> bool:
        directory = (
            settings.telemetry_dir
            / str(
                session_key
            )
        )

        return (
            directory.exists()
            and any(
                directory.glob(
                    "*_car.parquet"
                )
            )
            and any(
                directory.glob(
                    "*_position.parquet"
                )
            )
        )

    async def _telemetry_session_keys(self) -> set[int]:
        jobs = await workspace_repository.list("preparation", 1000)
        ready = {
            int(job["session_key"])
            for job in jobs
            if (
                job.get("telemetry_ready")
                or int(job.get("telemetry_drivers_ready") or 0) > 0
            )
            and job.get("session_key") is not None
        }
        if settings.telemetry_dir.is_dir():
            for directory in settings.telemetry_dir.iterdir():
                if directory.is_dir() and directory.name.isdigit():
                    key = int(directory.name)
                    if self._legacy_telemetry_available(key):
                        ready.add(key)
        return ready

    # =========================================================
    # YEAR CATALOGUE
    # =========================================================

    async def _with_readiness(self, catalogue: dict) -> dict:
        local = await self._local_session_keys()
        telemetry = await self._telemetry_session_keys()
        for meeting in catalogue["meetings"]:
            for session in meeting["sessions"]:
                key = session["session_key"]
                session["ingested"] = key in local
                session["telemetry_available"] = key in telemetry
        return catalogue

    async def year_catalogue(
        self,
        year: int,
        *,
        refresh: bool = False,
    ) -> dict[str, Any]:
        if (
            year not in self.years()
        ):
            raise ValueError(
                f"Unsupported year: {year}"
            )

        # -----------------------------------------------------
        # FAST PATH: CACHE
        # -----------------------------------------------------

        if not refresh:
            cached = (
                self._load_cache(
                    year
                )
            )

            if (
                cached is not None
            ):
                return await self._with_readiness(cached)

        # Prevent simultaneous duplicate builds.
        async with self._catalogue_lock:

            # Another request may have populated
            # the cache while we were waiting.
            if not refresh:
                cached = (
                    self._load_cache(
                        year
                    )
                )

                if (
                    cached is not None
                ):
                    return await self._with_readiness(cached)

            # -------------------------------------------------
            # OPENF1
            #
            # Deliberately sequential.
            # Do NOT use asyncio.gather here.
            # -------------------------------------------------

            meetings = (
                await self._get_openf1(
                    "meetings",
                    {
                        "year":
                            year,
                    },
                )
            )

            sessions = (
                await self._get_openf1(
                    "sessions",
                    {
                        "year":
                            year,
                    },
                )
            )

            local_session_keys = (
                await self
                ._local_session_keys()
            )
            telemetry_session_keys = await self._telemetry_session_keys()

            # -------------------------------------------------
            # GROUP SESSIONS BY MEETING
            # -------------------------------------------------

            sessions_by_meeting: dict[
                int,
                list[
                    dict[
                        str,
                        Any,
                    ]
                ],
            ] = {}

            for session in sessions:
                meeting_key_raw = (
                    session.get(
                        "meeting_key"
                    )
                )

                session_key_raw = (
                    session.get(
                        "session_key"
                    )
                )

                if (
                    meeting_key_raw is None
                    or session_key_raw is None
                ):
                    continue

                meeting_key = int(
                    meeting_key_raw
                )

                session_key = int(
                    session_key_raw
                )

                sessions_by_meeting.setdefault(
                    meeting_key,
                    [],
                ).append(
                    {
                        "session_key":
                            session_key,

                        "meeting_key":
                            meeting_key,

                        "session_name":
                            session.get(
                                "session_name"
                            ),

                        "session_type":
                            session.get(
                                "session_type"
                            ),

                        "date_start":
                            session.get(
                                "date_start"
                            ),

                        "date_end":
                            session.get(
                                "date_end"
                            ),

                        "is_cancelled":
                            bool(
                                session.get(
                                    "is_cancelled",
                                    False,
                                )
                            ),

                        "ingested":
                            (
                                session_key
                                in local_session_keys
                            ),

                        "telemetry_available": session_key in telemetry_session_keys,
                    }
                )

            # -------------------------------------------------
            # BUILD MEETING OUTPUT
            # -------------------------------------------------

            output_meetings: list[
                dict[
                    str,
                    Any,
                ]
            ] = []

            for meeting in meetings:
                meeting_key_raw = (
                    meeting.get(
                        "meeting_key"
                    )
                )

                if (
                    meeting_key_raw
                    is None
                ):
                    continue

                meeting_key = int(
                    meeting_key_raw
                )

                meeting_sessions = (
                    sessions_by_meeting.get(
                        meeting_key,
                        [],
                    )
                )

                meeting_sessions.sort(
                    key=lambda item: (
                        item.get(
                            "date_start"
                        )
                        or ""
                    )
                )

                if (
                    not meeting_sessions
                ):
                    continue

                output_meetings.append(
                    {
                        "meeting_key":
                            meeting_key,

                        "meeting_name":
                            meeting.get(
                                "meeting_name"
                            ),

                        "meeting_official_name":
                            meeting.get(
                                "meeting_official_name"
                            ),

                        "country_name":
                            meeting.get(
                                "country_name"
                            ),

                        "country_code":
                            meeting.get(
                                "country_code"
                            ),

                        "location":
                            meeting.get(
                                "location"
                            ),

                        "circuit_short_name":
                            meeting.get(
                                "circuit_short_name"
                            ),

                        "date_start":
                            meeting.get(
                                "date_start"
                            ),

                        "sessions":
                            meeting_sessions,
                    }
                )

            output_meetings.sort(
                key=lambda item: (
                    item.get(
                        "date_start"
                    )
                    or ""
                )
            )

            catalogue = {
                "year":
                    year,

                "meetings":
                    output_meetings,
            }

            self._save_cache(
                year,
                catalogue,
            )

            return catalogue


session_catalog_service = (
    SessionCatalogService()
)

from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.normalizers.common import (
    parse_datetime,
)
from app.ingestion.providers.base import (
    SessionDataBundle,
)
from app.persistence.models.driver import DriverRecord
from app.persistence.models.lap import LapRecord
from app.persistence.models.pit_stop import PitStopRecord
from app.persistence.models.race import RaceRecord
from app.persistence.models.session import SessionRecord
from app.persistence.models.stint import StintRecord


def _chunks(
    rows: list[dict[str, Any]],
    size: int = 500,
):
    for index in range(
        0,
        len(rows),
        size,
    ):
        yield rows[index:index + size]


class IngestionRepository:
    def __init__(
        self,
        db: AsyncSession,
    ) -> None:
        self.db = db

    async def _upsert_many(
        self,
        model,
        rows: list[dict[str, Any]],
        conflict_columns: list[str],
        update_columns: list[str],
    ) -> None:
        if not rows:
            return

        for chunk in _chunks(rows):
            statement = insert(
                model
            ).values(chunk)

            statement = statement.on_conflict_do_update(
                index_elements=conflict_columns,
                set_={
                    column: getattr(
                        statement.excluded,
                        column,
                    )
                    for column in update_columns
                },
            )

            await self.db.execute(
                statement
            )

    async def persist_bundle(
        self,
        bundle: SessionDataBundle,
    ) -> None:
        meeting = bundle.meeting
        session = bundle.session

        race_row = {
            "meeting_key": int(
                meeting["meeting_key"]
            ),
            "year": int(
                meeting["year"]
            ),
            "meeting_name": meeting.get(
                "meeting_name"
            ),
            "meeting_official_name": (
                meeting.get(
                    "meeting_official_name"
                )
            ),
            "country_name": meeting.get(
                "country_name"
            ),
            "location": meeting.get(
                "location"
            ),
            "circuit_key": meeting.get(
                "circuit_key"
            ),
            "circuit_short_name": (
                meeting.get(
                    "circuit_short_name"
                )
            ),
            "date_start": parse_datetime(
                meeting.get("date_start")
            ),
            "date_end": parse_datetime(
                meeting.get("date_end")
            ),
        }

        await self._upsert_many(
            RaceRecord,
            [race_row],
            ["meeting_key"],
            [
                key
                for key in race_row
                if key != "meeting_key"
            ],
        )

        session_row = {
            "session_key": int(
                session["session_key"]
            ),
            "meeting_key": int(
                session["meeting_key"]
            ),
            "year": int(
                session["year"]
            ),
            "session_name": session[
                "session_name"
            ],
            "session_type": session[
                "session_type"
            ],
            "country_name": session.get(
                "country_name"
            ),
            "circuit_short_name": (
                session.get(
                    "circuit_short_name"
                )
            ),
            "date_start": parse_datetime(
                session["date_start"]
            ),
            "date_end": parse_datetime(
                session.get("date_end")
            ),
            "gmt_offset": session.get(
                "gmt_offset"
            ),
            "is_cancelled": bool(
                session.get(
                    "is_cancelled",
                    False,
                )
            ),
            "starting_grid": bundle.starting_grid,
            "session_result": bundle.session_result,
        }

        await self._upsert_many(
            SessionRecord,
            [session_row],
            ["session_key"],
            [
                key
                for key in session_row
                if key != "session_key"
            ],
        )

        driver_rows = [
            {
                "session_key": int(
                    row["session_key"]
                ),
                "driver_number": int(
                    row["driver_number"]
                ),
                "full_name": row.get(
                    "full_name"
                ),
                "name_acronym": row.get(
                    "name_acronym"
                ),
                "team_name": row.get(
                    "team_name"
                ),
                "team_colour": row.get(
                    "team_colour"
                ),
                "headshot_url": row.get(
                    "headshot_url"
                ),
            }
            for row in bundle.drivers
        ]

        await self._upsert_many(
            DriverRecord,
            driver_rows,
            [
                "session_key",
                "driver_number",
            ],
            [
                "full_name",
                "name_acronym",
                "team_name",
                "team_colour",
                "headshot_url",
            ],
        )

        lap_rows = [
            {
                "session_key": int(
                    row["session_key"]
                ),
                "driver_number": int(
                    row["driver_number"]
                ),
                "lap_number": int(
                    row["lap_number"]
                ),
                "date_start": parse_datetime(
                    row.get("date_start")
                ),
                "lap_duration": row.get(
                    "lap_duration"
                ),
                "duration_sector_1": row.get(
                    "duration_sector_1"
                ),
                "duration_sector_2": row.get(
                    "duration_sector_2"
                ),
                "duration_sector_3": row.get(
                    "duration_sector_3"
                ),
                "i1_speed": row.get(
                    "i1_speed"
                ),
                "i2_speed": row.get(
                    "i2_speed"
                ),
                "st_speed": row.get(
                    "st_speed"
                ),
                "is_pit_out_lap": row.get(
                    "is_pit_out_lap"
                ),
                "segments_sector_1": (
                    row.get(
                        "segments_sector_1"
                    )
                ),
                "segments_sector_2": (
                    row.get(
                        "segments_sector_2"
                    )
                ),
                "segments_sector_3": (
                    row.get(
                        "segments_sector_3"
                    )
                ),
            }
            for row in bundle.laps
        ]

        await self._upsert_many(
            LapRecord,
            lap_rows,
            [
                "session_key",
                "driver_number",
                "lap_number",
            ],
            [
                key
                for key in lap_rows[0]
                if key
                not in {
                    "session_key",
                    "driver_number",
                    "lap_number",
                }
            ]
            if lap_rows
            else [],
        )

        stint_rows = [
            {
                "session_key": int(
                    row["session_key"]
                ),
                "driver_number": int(
                    row["driver_number"]
                ),
                "stint_number": int(
                    row["stint_number"]
                ),
                "lap_start": int(
                    row["lap_start"]
                ),
                "lap_end": row.get(
                    "lap_end"
                ),
                "compound": row.get(
                    "compound"
                ),
                "tyre_age_at_start": (
                    row.get(
                        "tyre_age_at_start"
                    )
                ),
            }
            for row in bundle.stints
            if row.get("lap_start") is not None
        ]

        await self._upsert_many(
            StintRecord,
            stint_rows,
            [
                "session_key",
                "driver_number",
                "stint_number",
            ],
            [
                "lap_start",
                "lap_end",
                "compound",
                "tyre_age_at_start",
            ],
        )

        pit_rows = []

        for row in bundle.pits:
            date = parse_datetime(
                row.get("date")
            )

            if date is None:
                continue

            pit_rows.append(
                {
                    "session_key": int(
                        row["session_key"]
                    ),
                    "driver_number": int(
                        row["driver_number"]
                    ),
                    "lap_number": int(
                        row["lap_number"]
                    ),
                    "date": date,
                    "lane_duration": row.get(
                        "lane_duration"
                    ),
                    "stop_duration": row.get(
                        "stop_duration"
                    ),
                }
            )

        await self._upsert_many(
            PitStopRecord,
            pit_rows,
            [
                "session_key",
                "driver_number",
                "lap_number",
                "date",
            ],
            [
                "lane_duration",
                "stop_duration",
            ],
        )

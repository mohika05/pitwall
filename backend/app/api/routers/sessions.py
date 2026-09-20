from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.persistence.database import (
    AsyncSessionLocal,
)
from app.persistence.repositories.session_repository import (
    SessionRepository,
)


router = APIRouter(
    prefix="/sessions",
    tags=["sessions"],
)


def _value(
    obj,
    *names: str,
):
    """
    Safely retrieve the first matching
    attribute from a model/object.
    """

    for name in names:
        value = getattr(
            obj,
            name,
            None,
        )

        if value is not None:
            return value

    return None


@router.get("")
async def list_sessions():
    async with AsyncSessionLocal() as db:

        # -------------------------------------------------
        # FIND ALL INGESTED SESSIONS
        # -------------------------------------------------

        result = await db.execute(
            text(
                """
                SELECT session_key
                FROM sessions
                ORDER BY session_key DESC
                """
            )
        )


        session_keys = [
            int(row[0])
            for row
            in result.fetchall()
        ]


        repository = (
            SessionRepository(
                db
            )
        )


        sessions = []


        # -------------------------------------------------
        # BUILD FRONTEND-FRIENDLY SESSION METADATA
        # -------------------------------------------------

        for session_key in session_keys:

            context = (
                await repository
                .get_replay_context(
                    session_key
                )
            )


            session = (
                context.session
            )


            year = _value(
                session,
                "year",
            )


            meeting_key = _value(
                session,
                "meeting_key",
            )


            country = _value(
                session,
                "country_name",
                "country",
                "location",
            )


            session_name = _value(
                session,
                "session_name",
                "name",
            )


            meeting_name = _value(
                session,
                "meeting_name",
            )


            date_start = _value(
                session,
                "date_start",
            )


            # -------------------------------------------------
            # DOES THIS SESSION HAVE FASTF1 TELEMETRY?
            # -------------------------------------------------

            telemetry_directory = (
                settings.telemetry_dir
                / str(
                    session_key
                )
            )


            telemetry_available = (
                telemetry_directory.exists()
                and any(
                    telemetry_directory.glob(
                        "*_car.parquet"
                    )
                )
            )


            # -------------------------------------------------
            # DISPLAY LABEL
            # -------------------------------------------------

            label_parts = []


            if year is not None:
                label_parts.append(
                    str(year)
                )


            if country:
                label_parts.append(
                    str(country)
                )


            if session_name:
                label_parts.append(
                    str(session_name)
                )


            label = (
                " · ".join(
                    label_parts
                )
                if label_parts
                else (
                    f"Session "
                    f"{session_key}"
                )
            )


            # -------------------------------------------------
            # SERIALIZE DATE
            # -------------------------------------------------

            if (
                date_start is not None
                and hasattr(
                    date_start,
                    "isoformat",
                )
            ):
                date_start_value = (
                    date_start.isoformat()
                )

            elif date_start is not None:
                date_start_value = (
                    str(
                        date_start
                    )
                )

            else:
                date_start_value = (
                    None
                )


            sessions.append(
                {
                    "session_key":
                        session_key,

                    "meeting_key":
                        meeting_key,

                    "year":
                        year,

                    "country":
                        country,

                    "session_name":
                        session_name,

                    "meeting_name":
                        meeting_name,

                    "date_start":
                        date_start_value,

                    "telemetry_available":
                        telemetry_available,

                    "label":
                        label,
                }
            )


        return {
            "sessions":
                sessions,
        }
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import (
    DriverInfo,
    ReplayContext,
    SessionInfo,
)
from app.persistence.models.driver import DriverRecord
from app.persistence.models.session import SessionRecord


class SessionRepository:
    def __init__(
        self,
        db: AsyncSession,
    ) -> None:
        self.db = db

    async def get_replay_context(
        self,
        session_key: int,
    ) -> ReplayContext:
        session = await self.db.get(
            SessionRecord,
            session_key,
        )

        if session is None:
            raise ValueError(
                f"Session {session_key} "
                f"not found"
            )

        result = await self.db.execute(
            select(
                DriverRecord
            ).where(
                DriverRecord.session_key
                == session_key
            )
        )

        driver_rows = result.scalars().all()

        drivers = [
            DriverInfo(
                driver_number=(
                    driver.driver_number
                ),
                full_name=driver.full_name,
                name_acronym=(
                    driver.name_acronym
                ),
                team_name=driver.team_name,
                team_colour=(
                    driver.team_colour
                ),
                headshot_url=(
                    driver.headshot_url
                ),
            )
            for driver in driver_rows
        ]

        grid: dict[int, int] = {}

        for row in (
            session.starting_grid or []
        ):
            if (
                row.get("driver_number")
                is not None
                and row.get("position")
                is not None
            ):
                grid[
                    int(row["driver_number"])
                ] = int(row["position"])

        return ReplayContext(
            session=SessionInfo(
                session_key=(
                    session.session_key
                ),
                meeting_key=(
                    session.meeting_key
                ),
                year=session.year,
                country_name=(
                    session.country_name
                ),
                circuit_short_name=(
                    session.circuit_short_name
                ),
                session_name=(
                    session.session_name
                ),
                session_type=(
                    session.session_type
                ),
                date_start=(
                    session.date_start
                ),
                date_end=session.date_end,
            ),
            drivers=drivers,
            starting_grid=grid,
        )

    async def get_official_result(
        self,
        session_key: int,
    ) -> list[dict]:
        session = await self.db.get(
            SessionRecord,
            session_key,
        )

        if session is None:
            raise ValueError(
                f"Session {session_key} "
                f"not found"
            )

        return session.session_result or []
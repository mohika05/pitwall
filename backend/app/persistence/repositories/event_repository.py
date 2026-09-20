from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import EventType
from app.domain.events import (
    RaceEvent,
    sort_events,
)
from app.persistence.models.race_event import (
    RaceEventRecord,
)


class EventRepository:
    def __init__(
        self,
        db: AsyncSession,
    ) -> None:
        self.db = db

    async def upsert_many(
        self,
        events: list[RaceEvent],
        chunk_size: int = 1000,
    ) -> None:
        for start in range(
            0,
            len(events),
            chunk_size,
        ):
            chunk = events[
                start:start + chunk_size
            ]

            rows = [
                {
                    "event_id": event.event_id,
                    "meeting_key": (
                        event.meeting_key
                    ),
                    "session_key": (
                        event.session_key
                    ),
                    "event_type": (
                        event.event_type.value
                    ),
                    "timestamp": (
                        event.timestamp
                    ),
                    "driver_number": (
                        event.driver_number
                    ),
                    "lap_number": (
                        event.lap_number
                    ),
                    "payload": event.payload,
                }
                for event in chunk
            ]

            statement = insert(
                RaceEventRecord
            ).values(rows)

            statement = statement.on_conflict_do_update(
                index_elements=["event_id"],
                set_={
                    "meeting_key": (
                        statement.excluded.meeting_key
                    ),
                    "session_key": (
                        statement.excluded.session_key
                    ),
                    "event_type": (
                        statement.excluded.event_type
                    ),
                    "timestamp": (
                        statement.excluded.timestamp
                    ),
                    "driver_number": (
                        statement.excluded.driver_number
                    ),
                    "lap_number": (
                        statement.excluded.lap_number
                    ),
                    "payload": (
                        statement.excluded.payload
                    ),
                },
            )

            await self.db.execute(
                statement
            )

    async def get_for_session(
        self,
        session_key: int,
    ) -> list[RaceEvent]:
        result = await self.db.execute(
            select(
                RaceEventRecord
            ).where(
                RaceEventRecord.session_key
                == session_key
            )
        )

        rows = result.scalars().all()

        events = [
            RaceEvent(
                event_id=row.event_id,
                meeting_key=row.meeting_key,
                session_key=row.session_key,
                event_type=EventType(
                    row.event_type
                ),
                timestamp=row.timestamp,
                driver_number=(
                    row.driver_number
                ),
                lap_number=row.lap_number,
                payload=row.payload,
            )
            for row in rows
        ]

        return sort_events(events)
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.database import Base

class RaceEventRecord(Base):
    __tablename__ = "race_events"

    __table_args__ = (
        Index(
            "ix_race_events_session_timestamp",
            "session_key",
            "timestamp",
        ),
    )

    event_id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )

    meeting_key: Mapped[int] = mapped_column(
        Integer,
        index=True,
    )

    session_key: Mapped[int] = mapped_column(
        ForeignKey(
            "sessions.session_key",
            ondelete="CASCADE",
        ),
        index=True,
    )

    event_type: Mapped[str] = mapped_column(
        String(50),
        index=True,
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )

    driver_number: Mapped[
        int | None
    ] = mapped_column(
        Integer,
        index=True,
    )

    lap_number: Mapped[
        int | None
    ] = mapped_column(Integer)

    payload: Mapped[dict] = mapped_column(
        JSONB
    )
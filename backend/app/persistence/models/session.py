from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.database import Base

class SessionRecord(Base):
    __tablename__ = "sessions"

    session_key: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    meeting_key: Mapped[int] = mapped_column(
        ForeignKey(
            "races.meeting_key",
            ondelete="CASCADE",
        ),
        index=True,
    )

    year: Mapped[int] = mapped_column(
        Integer
    )

    session_name: Mapped[str] = mapped_column(
        String(100)
    )

    session_type: Mapped[str] = mapped_column(
        String(100)
    )

    country_name: Mapped[str | None] = mapped_column(
        String(100)
    )

    circuit_short_name: Mapped[
        str | None
    ] = mapped_column(String(100))

    date_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )

    date_end: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True)
    )

    gmt_offset: Mapped[
        str | None
    ] = mapped_column(String(20))

    is_cancelled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    starting_grid: Mapped[
        list | None
    ] = mapped_column(JSONB)

    session_result: Mapped[
        list | None
    ] = mapped_column(JSONB)
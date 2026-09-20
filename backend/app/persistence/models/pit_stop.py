from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.database import Base

class PitStopRecord(Base):
    __tablename__ = "pit_stops"

    __table_args__ = (
        UniqueConstraint(
            "session_key",
            "driver_number",
            "lap_number",
            "date",
            name="uq_pit_session_driver_lap_date",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    session_key: Mapped[int] = mapped_column(
        ForeignKey(
            "sessions.session_key",
            ondelete="CASCADE",
        ),
        index=True,
    )

    driver_number: Mapped[int] = mapped_column(
        Integer,
        index=True,
    )

    lap_number: Mapped[int] = mapped_column(
        Integer
    )

    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )

    lane_duration: Mapped[
        float | None
    ] = mapped_column(Float)

    stop_duration: Mapped[
        float | None
    ] = mapped_column(Float)
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.database import Base

class LapRecord(Base):
    __tablename__ = "laps"

    __table_args__ = (
        UniqueConstraint(
            "session_key",
            "driver_number",
            "lap_number",
            name="uq_lap_session_driver_number",
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

    date_start: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True)
    )

    lap_duration: Mapped[
        float | None
    ] = mapped_column(Float)

    duration_sector_1: Mapped[
        float | None
    ] = mapped_column(Float)

    duration_sector_2: Mapped[
        float | None
    ] = mapped_column(Float)

    duration_sector_3: Mapped[
        float | None
    ] = mapped_column(Float)

    i1_speed: Mapped[
        float | None
    ] = mapped_column(Float)

    i2_speed: Mapped[
        float | None
    ] = mapped_column(Float)

    st_speed: Mapped[
        float | None
    ] = mapped_column(Float)

    is_pit_out_lap: Mapped[
        bool | None
    ] = mapped_column(Boolean)

    segments_sector_1: Mapped[
        list | None
    ] = mapped_column(JSONB)

    segments_sector_2: Mapped[
        list | None
    ] = mapped_column(JSONB)

    segments_sector_3: Mapped[
        list | None
    ] = mapped_column(JSONB)
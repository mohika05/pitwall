from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.database import Base

class RaceRecord(Base):
    __tablename__ = "races"

    meeting_key: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    year: Mapped[int] = mapped_column(
        Integer,
        index=True,
    )

    meeting_name: Mapped[str | None] = mapped_column(
        String(255)
    )

    meeting_official_name: Mapped[
        str | None
    ] = mapped_column(Text)

    country_name: Mapped[str | None] = mapped_column(
        String(100)
    )

    location: Mapped[str | None] = mapped_column(
        String(100)
    )

    circuit_key: Mapped[int | None] = mapped_column(
        Integer
    )

    circuit_short_name: Mapped[
        str | None
    ] = mapped_column(String(100))

    date_start: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True)
    )

    date_end: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True)
    )
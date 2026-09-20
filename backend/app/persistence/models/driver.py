from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.database import Base

class DriverRecord(Base):
    __tablename__ = "drivers"

    session_key: Mapped[int] = mapped_column(
        ForeignKey(
            "sessions.session_key",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    driver_number: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    full_name: Mapped[str | None] = mapped_column(
        String(150)
    )

    name_acronym: Mapped[str | None] = mapped_column(
        String(10)
    )

    team_name: Mapped[str | None] = mapped_column(
        String(150)
    )

    team_colour: Mapped[str | None] = mapped_column(
        String(16)
    )

    headshot_url: Mapped[str | None] = mapped_column(
        Text
    )
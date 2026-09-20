from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.database import Base

class StintRecord(Base):
    __tablename__ = "stints"

    __table_args__ = (
        UniqueConstraint(
            "session_key",
            "driver_number",
            "stint_number",
            name="uq_stint_session_driver_number",
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

    stint_number: Mapped[int] = mapped_column(
        Integer
    )

    lap_start: Mapped[int] = mapped_column(
        Integer
    )

    lap_end: Mapped[
        int | None
    ] = mapped_column(Integer)

    compound: Mapped[
        str | None
    ] = mapped_column(String(30))

    tyre_age_at_start: Mapped[
        int | None
    ] = mapped_column(Integer)
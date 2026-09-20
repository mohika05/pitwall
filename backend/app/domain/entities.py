from datetime import datetime

from pydantic import BaseModel, Field

class DriverInfo(BaseModel):
    driver_number: int
    full_name: str | None = None
    name_acronym: str | None = None
    team_name: str | None = None
    team_colour: str | None = None
    headshot_url: str | None = None

class SessionInfo(BaseModel):
    session_key: int
    meeting_key: int 
    year: int
    country_name: str | None = None
    circuit_short_name: str | None = None
    session_name: str
    session_type: str
    date_start: datetime
    date_end: datetime | None = None

class ReplayContext(BaseModel):
    session: SessionInfo
    drivers: list[DriverInfo]
    starting_grid: dict[int, int] = Field(
        default_factory=dict
    )
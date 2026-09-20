from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

class SessionDataBundle(BaseModel):
    meeting: dict[str, Any]
    session: dict[str, Any]

    drivers: list[dict[str, Any]] = Field(default_factory=list)
    laps: list[dict[str, Any]] = Field(default_factory=list)
    positions: list[dict[str, Any]] = Field(default_factory=list)
    intervals: list[dict[str, Any]] = Field(default_factory=list)
    stints: list[dict[str, Any]] = Field(default_factory=list)
    pits: list[dict[str, Any]] = Field(default_factory=list)
    race_control: list[dict[str, Any]] = Field(default_factory=list)
    weather: list[dict[str, Any]] = Field(default_factory=list)

    starting_grid: list[dict[str, Any]] = Field(default_factory=list)
    session_result: list[dict[str, Any]] = Field(default_factory=list)

    car_data_sample: list[dict[str, Any]] = Field(default_factory=list)
    location_sample: list[dict[str, Any]] = Field(default_factory=list)

class RaceDataProvider(ABC):
    @abstractmethod
    async def find_race_session(
        self,
        year: int,
        country_name: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def fetch_bundle(
        self,
        session: dict[str, Any],
    ) -> SessionDataBundle:
        raise NotImplementedError
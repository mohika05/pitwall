from datetime import datetime

from pydantic import BaseModel


class ReplaySpeedRequest(
    BaseModel
):
    speed: float


class ReplaySeekIndexRequest(
    BaseModel
):
    event_index: int


class ReplaySeekTimeRequest(
    BaseModel
):
    timestamp: datetime
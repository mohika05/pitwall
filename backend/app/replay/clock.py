from datetime import datetime
from math import isfinite


class ReplayClock:
    def __init__(
        self,
        speed: float = 1.0,
    ) -> None:
        self.set_speed(speed)

    @property
    def speed(self) -> float:
        return self._speed

    def set_speed(
        self,
        speed: float,
    ) -> None:
        if not isfinite(speed) or speed <= 0:
            raise ValueError(
                "Replay speed must be > 0"
            )

        self._speed = speed

    def delay_between(
        self,
        previous: datetime,
        current: datetime,
    ) -> float:
        real_delay = max(
            0.0,
            (
                current - previous
            ).total_seconds(),
        )

        return real_delay / self._speed
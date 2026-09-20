import asyncio
import hashlib
import inspect
import json
from bisect import bisect_right
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from app.domain.entities import ReplayContext
from app.domain.events import (
    RaceEvent,
    sort_events,
)
from app.domain.race_state import (
    RaceState,
    apply_event,
    build_initial_state,
)
from app.replay.clock import ReplayClock
from app.replay.snapshots import SnapshotStore

ReplayCallback = Callable[
    [RaceState, RaceEvent],
    Awaitable[None] | None,
]


class ReplayEngine:
    def __init__(
        self,
        context: ReplayContext,
        events: list[RaceEvent],
        snapshot_interval: int = 500,
    ) -> None:
        self.context = context

        session_start = (
            context.session.date_start
        )

        self.events = sort_events(
            [
                event
                for event in events
                if event.timestamp
                >= session_start
            ]
        )
        self.timestamps = [
            event.timestamp
            for event in self.events
        ]

        self.snapshot_interval = (
            snapshot_interval
        )

        self.clock = ReplayClock()

        self.snapshots = SnapshotStore()

        self.state = build_initial_state(
            context
        )

        self.current_index = -1

        self.is_playing = False

        self.snapshots.save(
            -1,
            self.state,
        )

    def reset(self) -> RaceState:
        self.state = build_initial_state(
            self.context
        )

        self.current_index = -1
        self.is_playing = False

        return self.state

    def set_speed(
        self,
        speed: float,
    ) -> None:
        self.clock.set_speed(
            speed
        )

    def pause(self) -> None:
        self.is_playing = False

    def step(self) -> RaceState:
        next_index = (
            self.current_index + 1
        )

        if next_index >= len(
            self.events
        ):
            return self.state

        event = self.events[
            next_index
        ]

        apply_event(
            self.state,
            event,
        )

        self.current_index = (
            next_index
        )

        if (
            self.current_index
            % self.snapshot_interval
            == 0
        ):
            self.snapshots.save(
                self.current_index,
                self.state,
            )

        return self.state

    def run_to_end(self) -> RaceState:
        while (
            self.current_index + 1
            < len(self.events)
        ):
            self.step()

        return self.state

    def seek_index(
        self,
        target_index: int,
    ) -> RaceState:
        if target_index < -1:
            raise ValueError(
                "target_index cannot be < -1"
            )

        if target_index >= len(
            self.events
        ):
            raise ValueError(
                "target_index exceeds event count"
            )

        snapshot = (
            self.snapshots
            .nearest_at_or_before(
                target_index
            )
        )

        if snapshot is None:
            self.reset()
        else:
            (
                self.current_index,
                self.state,
            ) = snapshot

        while (
            self.current_index
            < target_index
        ):
            self.step()

        return self.state

    def seek_time(
        self,
        timestamp: datetime,
    ) -> RaceState:
        target_index = (
            bisect_right(
                self.timestamps,
                timestamp,
            )
            - 1
        )

        self.seek_index(target_index)
        # Preserve the requested cursor between events, within available history.
        end = self.timestamps[-1] if self.timestamps else self.context.session.date_start
        self.state.replay_timestamp = max(
            self.context.session.date_start, min(timestamp, end)
        )
        return self.state

    async def play(
        self,
        callback: ReplayCallback | None = None,
        on_tick: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.is_playing = True
        loop = asyncio.get_running_loop()
        previous_wall_time = loop.time()
        try:
            while self.is_playing and self.current_index + 1 < len(self.events):
                # Sample speed for this interval; changes take effect on the next tick.
                speed = self.clock.speed
                await asyncio.sleep(0.05)
                if not self.is_playing:
                    break

                now = loop.time()
                target = min(
                    self.state.replay_timestamp
                    + timedelta(seconds=(now - previous_wall_time) * speed),
                    self.timestamps[-1],
                )
                previous_wall_time = now

                while (
                    self.is_playing
                    and self.current_index + 1 < len(self.events)
                    and self.events[self.current_index + 1].timestamp <= target
                ):
                    event = self.events[self.current_index + 1]
                    self.step()
                    if callback is not None:
                        result = callback(self.state, event)
                        if inspect.isawaitable(result):
                            await result

                if not self.is_playing:
                    break
                self.state.replay_timestamp = target
                if on_tick is not None:
                    await on_tick()
        finally:
            self.is_playing = False


def state_fingerprint(
    state: RaceState,
) -> str:
    encoded = json.dumps(
        state.model_dump(
            mode="json"
        ),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    return hashlib.sha256(
        encoded
    ).hexdigest()
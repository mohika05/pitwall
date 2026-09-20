import asyncio
import time
from datetime import datetime

from app.cache.race_state_cache import (
    RaceStateCache,
)
from app.persistence.database import (
    AsyncSessionLocal,
)
from app.persistence.repositories.event_repository import (
    EventRepository,
)
from app.persistence.repositories.session_repository import (
    SessionRepository,
)
from app.realtime.manager import (
    connection_manager,
)
from app.realtime.messages import (
    race_state_message,
)
from app.replay.engine import (
    ReplayEngine,
)


class ReplayController:
    MAX_BROADCAST_HZ = 10.0

    def __init__(
        self,
        session_key: int,
        engine: ReplayEngine,
    ) -> None:
        self.session_key = (
            session_key
        )

        self.engine = engine
        self.revision = 0

        self.cache = (
            RaceStateCache()
        )

        self._play_task: (
            asyncio.Task | None
        ) = None

        self._last_broadcast_wall_time = (
            0.0
        )

        self._operation_lock = (
            asyncio.Lock()
        )

    # -----------------------------------------------------
    # STATE
    # -----------------------------------------------------

    @property
    def playing(self) -> bool:
        return (
            self._play_task
            is not None
            and not self._play_task.done()
            and self.engine.is_playing
        )

    @property
    def speed(self) -> float:
        return self.engine.clock.speed

    def status(self) -> dict:
        return {
            "revision": self.revision,
            "session_key": (
                self.session_key
            ),
            "playing": self.playing,
            "speed": self.speed,
            "event_index": (
                self.engine.current_index
            ),
            "total_events": len(
                self.engine.events
            ),
            "replay_timestamp": (
                self.engine.state
                .replay_timestamp
                .isoformat()
            ),
            "current_lap": (
                self.engine.state
                .current_lap
            ),
        }

    # -----------------------------------------------------
    # BROADCASTING
    # -----------------------------------------------------

    async def _broadcast_state(
        self,
        force: bool = False,
    ) -> None:
        now = time.monotonic()

        minimum_interval = (
            1.0
            / self.MAX_BROADCAST_HZ
        )

        if (
            not force
            and (
                now
                - self._last_broadcast_wall_time
            )
            < minimum_interval
        ):
            return

        self._last_broadcast_wall_time = (
            now
        )

        await self.cache.set(
            self.engine.state
        )

        message = race_state_message(
            session_key=(
                self.session_key
            ),
            state=(
                self.engine.state.model_dump(
                    mode="json"
                )
            ),
            event_index=(
                self.engine.current_index
            ),
            total_events=len(
                self.engine.events
            ),
            playing=self.playing,
            speed=self.speed,
            revision=self.revision,
        )

        await connection_manager.broadcast(
            self.session_key,
            message,
        )

    async def _on_event(
        self,
        _state,
        _event,
    ) -> None:
        await self._broadcast_state(
            force=False
        )

    # -----------------------------------------------------
    # PLAYBACK
    # -----------------------------------------------------

    async def _run_playback(
        self,
    ) -> None:
        try:
            await self.engine.play(
                on_tick=self._broadcast_state
            )

        finally:
            await self._broadcast_state(
                force=True
            )

    async def play(
        self,
    ) -> dict:
        async with self._operation_lock:
            if self.playing:
                return self.status()

            if (
                self.engine.current_index + 1
                >= len(
                    self.engine.events
                )
            ):
                self.engine.reset()
                self.revision += 1

            self.engine.is_playing = True
            self._play_task = (
                asyncio.create_task(
                    self._run_playback()
                )
            )

            await self._broadcast_state(
                force=True
            )

            return self.status()

    async def _stop_playback(self) -> None:
        # Caller holds the operation lock, including across a seek or reset.
        self.engine.pause()
        task = self._play_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._play_task = None

    async def pause(self) -> dict:
        async with self._operation_lock:
            await self._stop_playback()
            await self._broadcast_state(force=True)
            return self.status()

    async def reset(self) -> dict:
        async with self._operation_lock:
            await self._stop_playback()
            self.engine.reset()
            self.revision += 1
            await self._broadcast_state(force=True)
            return self.status()

    async def set_speed(
        self,
        speed: float,
    ) -> dict:
        if speed <= 0:
            raise ValueError(
                "Replay speed must be > 0"
            )

        if speed > 100:
            raise ValueError(
                
                    "Replay speed must be "
                    "<= 100"
                
            )

        self.engine.set_speed(
            speed
        )

        await self._broadcast_state(
            force=True
        )

        return self.status()

    async def seek_index(
        self,
        event_index: int,
    ) -> dict:
        async with self._operation_lock:
            await self._stop_playback()
            self.engine.seek_index(
                event_index
            )

            self.revision += 1

            await self._broadcast_state(
                force=True
            )

            return self.status()

    async def seek_time(
        self,
        timestamp: datetime,
    ) -> dict:
        async with self._operation_lock:
            await self._stop_playback()
            self.engine.seek_time(
                timestamp
            )

            self.revision += 1

            await self._broadcast_state(
                force=True
            )

            return self.status()


class ReplayRegistry:
    def __init__(self) -> None:
        self._controllers: dict[
            int,
            ReplayController,
        ] = {}

        self._lock = asyncio.Lock()

    async def get(
        self,
        session_key: int,
    ) -> ReplayController:
        existing = (
            self._controllers.get(
                session_key
            )
        )

        if existing is not None:
            return existing

        async with self._lock:
            existing = (
                self._controllers.get(
                    session_key
                )
            )

            if existing is not None:
                return existing

            async with (
                AsyncSessionLocal()
                as db
            ):
                context = (
                    await SessionRepository(
                        db
                    ).get_replay_context(
                        session_key
                    )
                )

                events = (
                    await EventRepository(
                        db
                    ).get_for_session(
                        session_key
                    )
                )

            if not events:
                raise ValueError(
                    
                        "No replay events "
                        f"for session "
                        f"{session_key}"
                    
                )

            controller = (
                ReplayController(
                    session_key=(
                        session_key
                    ),
                    engine=(
                        ReplayEngine(
                            context,
                            events,
                        )
                    ),
                )
            )

            self._controllers[
                session_key
            ] = controller

            await controller.cache.set(
                controller.engine.state
            )

            return controller


replay_registry = ReplayRegistry()
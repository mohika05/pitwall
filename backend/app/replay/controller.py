import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from datetime import datetime

from redis.exceptions import RedisError

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
from app.persistence.repositories.workspace_repository import workspace_repository
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
        workspace_id: str | None = None,
        dataset_version: str | None = None,
    ) -> None:
        self.session_key = session_key

        self.engine = engine
        self.revision = 0
        self.last_access = time.monotonic()
        self.workspace_id = workspace_id
        self.channel = workspace_id or session_key
        self._last_checkpoint = 0.0
        self._broadcast_lock = asyncio.Lock()
        self.dataset_version = dataset_version or _dataset_version(
            engine.context,
            engine.events,
        )

        self.cache = RaceStateCache(workspace_id)

        self._play_task: asyncio.Task | None = None

        self._last_broadcast_wall_time = 0.0

        self._operation_lock = asyncio.Lock()

    # -----------------------------------------------------
    # STATE
    # -----------------------------------------------------

    @property
    def playing(self) -> bool:
        return self._play_task is not None and not self._play_task.done() and self.engine.is_playing

    @property
    def speed(self) -> float:
        return self.engine.clock.speed

    def status(self) -> dict:
        return {
            "revision": self.revision,
            "workspace_id": self.workspace_id,
            "dataset_version": self.dataset_version,
            "session_key": (self.session_key),
            "playing": self.playing,
            "speed": self.speed,
            "event_index": (self.engine.current_index),
            "total_events": len(self.engine.events),
            "replay_timestamp": (self.engine.state.replay_timestamp.isoformat()),
            "current_lap": (self.engine.state.current_lap),
        }

    # -----------------------------------------------------
    # BROADCASTING
    # -----------------------------------------------------

    async def _broadcast_state(
        self,
        force: bool = False,
    ) -> None:
        now = time.monotonic()

        minimum_interval = 1.0 / self.MAX_BROADCAST_HZ

        if not force and (now - self._last_broadcast_wall_time) < minimum_interval:
            return

        self._last_broadcast_wall_time = now

        async with self._broadcast_lock:
            message = race_state_message(
                session_key=self.session_key,
                state=self.engine.state.model_dump(mode="json"),
                event_index=self.engine.current_index,
                total_events=len(self.engine.events),
                playing=self.playing,
                speed=self.speed,
                revision=self.revision,
            )
            try:
                await self.cache.set(self.engine.state)
            except RedisError:
                logging.getLogger(__name__).warning("Replay cache unavailable", exc_info=True)
            await connection_manager.broadcast(self.channel, message)
            if self.workspace_id and (force or now - self._last_checkpoint >= 5):
                await workspace_repository.put("replay", self.workspace_id, self.status())
                self._last_checkpoint = now

    async def _on_event(
        self,
        _state,
        _event,
    ) -> None:
        await self._broadcast_state(force=False)

    # -----------------------------------------------------
    # PLAYBACK
    # -----------------------------------------------------

    async def _run_playback(
        self,
    ) -> None:
        try:
            await self.engine.play(on_tick=self._broadcast_state)

        finally:
            await self._broadcast_state(force=True)

    async def play(
        self,
    ) -> dict:
        async with self._operation_lock:
            if self.playing:
                return self.status()

            if self.engine.current_index + 1 >= len(self.engine.events):
                self.engine.reset()
                self.revision += 1

            self.engine.is_playing = True
            self._play_task = asyncio.create_task(self._run_playback())

            await self._broadcast_state(force=True)

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
            raise ValueError("Replay speed must be > 0")

        if speed > 100:
            raise ValueError("Replay speed must be <= 100")

        self.engine.set_speed(speed)

        await self._broadcast_state(force=True)

        return self.status()

    async def seek_index(
        self,
        event_index: int,
    ) -> dict:
        async with self._operation_lock:
            await self._stop_playback()
            self.engine.seek_index(event_index)

            self.revision += 1

            await self._broadcast_state(force=True)

            return self.status()

    async def seek_time(
        self,
        timestamp: datetime,
    ) -> dict:
        async with self._operation_lock:
            await self._stop_playback()
            self.engine.seek_time(timestamp)

            self.revision += 1

            await self._broadcast_state(force=True)

            return self.status()


class ReplayRegistry:
    MAX_CACHED_DATASETS = 2

    def __init__(self) -> None:
        self._controllers: dict[str, ReplayController] = {}
        self._datasets: OrderedDict[int, tuple] = OrderedDict()
        self._lock = asyncio.Lock()

    async def _dataset(self, session_key: int) -> tuple:
        cached = self._datasets.get(session_key)
        if cached is not None:
            self._datasets.move_to_end(session_key)
            return cached

        async with AsyncSessionLocal() as db:
            context = await SessionRepository(db).get_replay_context(session_key)
            events = await EventRepository(db).get_for_session(session_key)
        if not events:
            raise ValueError(f"No replay events for session {session_key}")

        dataset = (context, events, _dataset_version(context, events))
        self._datasets[session_key] = dataset
        while len(self._datasets) > self.MAX_CACHED_DATASETS:
            self._datasets.popitem(last=False)
        return dataset

    async def get(self, session_key: int, viewer_id: str | None = None) -> ReplayController:
        key = f"{viewer_id or 'legacy'}:{session_key}"
        async with self._lock:
            if key in self._controllers:
                self._controllers[key].last_access = time.monotonic()
                return self._controllers[key]
            context, events, dataset_version = await self._dataset(session_key)
            controller = ReplayController(
                session_key,
                ReplayEngine(context, events),
                key if viewer_id else None,
                dataset_version,
            )
            if viewer_id:
                saved = await workspace_repository.get("replay", key)
                if saved and saved.get("dataset_version") == controller.dataset_version:
                    controller.engine.seek_time(datetime.fromisoformat(saved["replay_timestamp"]))
                    controller.engine.set_speed(saved["speed"])
                    controller.revision = saved.get("revision", 0) + 1
                    # Recovery is deliberately paused so reopening does not move the cursor.
            self._controllers[key] = controller
            return controller

    async def collect_idle(self) -> None:
        async with self._lock:
            for key, controller in list(self._controllers.items()):
                if (
                    time.monotonic() - controller.last_access > 120
                    and await connection_manager.count(controller.channel) == 0
                ):
                    await controller.pause()
                    self._controllers.pop(key)

    async def close(self) -> None:
        for controller in list(self._controllers.values()):
            await controller.pause()
        self._controllers.clear()
        self._datasets.clear()


def _dataset_version(context, events) -> str:
    """Hash a replay dataset without constructing a second full serialized copy."""
    digest = hashlib.sha256()
    digest.update(
        json.dumps(context.model_dump(mode="json"), sort_keys=True).encode()
    )
    for event in events:
        digest.update(event.model_dump_json().encode())
    return digest.hexdigest()


replay_registry = ReplayRegistry()

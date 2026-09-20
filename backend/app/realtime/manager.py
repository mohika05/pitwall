import asyncio
import logging

from fastapi import WebSocket

from app.realtime.messages import (
    RealtimeMessage,
)

logger = logging.getLogger(
    __name__
)

class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[
            int,
            set[WebSocket],
        ] = {}

        self._lock = asyncio.Lock()

    async def connect(
        self,
        session_key: int,
        websocket: WebSocket,
    ) -> None:
        await websocket.accept()

        async with self._lock:
            self._connections.setdefault(
                session_key,
                set(),
            ).add(
                websocket
            )

        logger.info(
            (
                "WebSocket connected "
                "to session %s"
            ),
            session_key,
        )

    async def disconnect(
        self,
        session_key: int,
        websocket: WebSocket,
    ) -> None:
        async with self._lock:
            connections = (
                self._connections.get(
                    session_key
                )
            )

            if connections is None:
                return

            connections.discard(
                websocket
            )

            if not connections:
                self._connections.pop(
                    session_key,
                    None,
                )

        logger.info(
            (
                "WebSocket disconnected "
                "from session %s"
            ),
            session_key,
        )

    async def broadcast(
        self,
        session_key: int,
        message: RealtimeMessage,
    ) -> None:
        async with self._lock:
            connections = list(
                self._connections.get(
                    session_key,
                    set(),
                )
            )

        dead: list[
            WebSocket
        ] = []

        payload = message.model_dump(
            mode="json"
        )

        for websocket in connections:
            try:
                await websocket.send_json(
                    payload
                )

            except Exception:
                dead.append(
                    websocket
                )

        for websocket in dead:
            await self.disconnect(
                session_key,
                websocket,
            )

    async def count(
        self,
        session_key: int,
    ) -> int:
        async with self._lock:
            return len(
                self._connections.get(
                    session_key,
                    set(),
                )
            )

connection_manager = (
    ConnectionManager()
)
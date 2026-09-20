from uuid import UUID
from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
)

from app.realtime.manager import (
    connection_manager,
)
from app.realtime.messages import (
    race_state_message,
)
from app.replay.controller import (
    replay_registry,
)

router = APIRouter(
    tags=["websocket"]
)


@router.websocket(
    "/ws/replay/{session_key}"
)
async def replay_websocket(
    websocket: WebSocket,
    session_key: int,
    viewer_id: UUID | None = None,
) -> None:
    controller = (
        await replay_registry.get(
            session_key, str(viewer_id) if viewer_id else None
        )
    )

    await connection_manager.connect(
        controller.channel,
        websocket,
    )

    try:
        initial_message = (
            race_state_message(
                session_key=(
                    session_key
                ),
                state=(
                    controller.engine.state
                    .model_dump(
                        mode="json"
                    )
                ),
                event_index=(
                    controller.engine
                    .current_index
                ),
                total_events=len(
                    controller.engine.events
                ),
                playing=(
                    controller.playing
                ),
                speed=(
                    controller.speed
                ),
                revision=controller.revision,
            )
        )

        await websocket.send_json(
            initial_message.model_dump(
                mode="json"
            )
        )

        while True:
            message = (
                await websocket.receive_text()
            )

            if message == "ping":
                await websocket.send_json(
                    {
                        "type": "pong",
                        "session_key": (
                            session_key
                        ),
                    }
                )

    except WebSocketDisconnect:
        pass

    finally:
        await connection_manager.disconnect(
            controller.channel,
            websocket,
        )
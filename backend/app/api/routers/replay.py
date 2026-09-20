from uuid import UUID
from fastapi import (
    APIRouter,
    HTTPException,
)

from app.replay.controller import (
    replay_registry,
)
from app.schemas.replay import (
    ReplaySeekIndexRequest,
    ReplaySeekTimeRequest,
    ReplaySpeedRequest,
)


router = APIRouter(
    prefix="/replay",
    tags=["replay"],
)


async def _controller(
    session_key: int,
    viewer_id: UUID | None = None,
):
    try:
        return await replay_registry.get(
            session_key, str(viewer_id) if viewer_id else None
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@router.get(
    "/{session_key}/status"
)
async def replay_status(
    session_key: int,
    viewer_id: UUID | None = None,
):
    controller = await _controller(
        session_key, viewer_id
    )

    return controller.status()


@router.get(
    "/{session_key}/state"
)
async def replay_state(
    session_key: int,
    viewer_id: UUID | None = None,
):
    controller = await _controller(
        session_key, viewer_id
    )

    return {
        "status": controller.status(),
        "state": (
            controller.engine.state
            .model_dump(
                mode="json"
            )
        ),
    }


@router.post(
    "/{session_key}/play"
)
async def replay_play(
    session_key: int,
    viewer_id: UUID | None = None,
):
    controller = await _controller(
        session_key, viewer_id
    )

    return await controller.play()


@router.post(
    "/{session_key}/pause"
)
async def replay_pause(
    session_key: int,
    viewer_id: UUID | None = None,
):
    controller = await _controller(
        session_key, viewer_id
    )

    return await controller.pause()


@router.post(
    "/{session_key}/reset"
)
async def replay_reset(
    session_key: int,
    viewer_id: UUID | None = None,
):
    controller = await _controller(
        session_key, viewer_id
    )

    return await controller.reset()


@router.post(
    "/{session_key}/speed"
)
async def replay_speed(
    session_key: int,
    request: ReplaySpeedRequest,
    viewer_id: UUID | None = None,
):
    controller = await _controller(
        session_key, viewer_id
    )

    try:
        return await controller.set_speed(
            request.speed
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.post(
    "/{session_key}/seek/index"
)
async def replay_seek_index(
    session_key: int,
    request: ReplaySeekIndexRequest,
    viewer_id: UUID | None = None,
):
    controller = await _controller(
        session_key, viewer_id
    )

    try:
        return await controller.seek_index(
            request.event_index
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.post(
    "/{session_key}/seek/time"
)
async def replay_seek_time(
    session_key: int,
    request: ReplaySeekTimeRequest,
    viewer_id: UUID | None = None,
):
    controller = await _controller(
        session_key, viewer_id
    )

    return await controller.seek_time(
        request.timestamp
    )
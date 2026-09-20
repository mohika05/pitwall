from fastapi import APIRouter, HTTPException

from app.services.live import live_service

router = APIRouter(prefix="/live", tags=["live"])


@router.get("/{session_key}")
async def status(session_key: int):
    return live_service.feeds.get(
        session_key,
        {
            "session_key": session_key,
            "status": "stopped",
            "state": None,
            "telemetry": None,
            "updated_at": None,
            "error": None,
        },
    )


@router.post("/{session_key}/start")
async def start(session_key: int):
    try:
        return await live_service.start(session_key)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{session_key}/stop")
async def stop(session_key: int):
    return await live_service.stop(session_key)

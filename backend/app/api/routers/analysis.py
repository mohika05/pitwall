from fastapi import APIRouter, HTTPException

from app.services.analysis import session_analysis

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/{session_key}")
async def analysis(session_key: int):
    try:
        return await session_analysis(session_key)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc

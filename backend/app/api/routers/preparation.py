from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.persistence.repositories.workspace_repository import workspace_repository
from app.services.preparation import preparation_service

router = APIRouter(prefix="/preparation", tags=["preparation"])


class PrepareRequest(BaseModel):
    telemetry: bool = True


@router.get("")
async def jobs():
    return await workspace_repository.list("preparation")


@router.get("/{session_key}")
async def job(session_key: int):
    result = await workspace_repository.get("preparation", str(session_key))
    if result is None:
        raise HTTPException(404, "No preparation job for this session")
    return result


@router.post("/{session_key}", status_code=202)
async def prepare(session_key: int, request: PrepareRequest):
    if session_key <= 0:
        raise HTTPException(400, "Invalid session key")
    return await preparation_service.start(session_key, request.telemetry)

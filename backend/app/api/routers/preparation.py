from hmac import compare_digest
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.persistence.repositories.workspace_repository import workspace_repository
from app.services.preparation import preparation_service


async def require_preparation_admin(
    x_pitwall_admin: Annotated[str | None, Header()] = None,
) -> None:
    expected = settings.pitwall_admin_token
    if not expected:
        if settings.app_env.lower() == "production":
            raise HTTPException(503, "Preparation administration is not configured")
        return
    if x_pitwall_admin is None or not compare_digest(x_pitwall_admin, expected):
        raise HTTPException(401, "Invalid preparation administrator token")


router = APIRouter(
    prefix="/preparation",
    tags=["preparation"],
    dependencies=[Depends(require_preparation_admin)],
)


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

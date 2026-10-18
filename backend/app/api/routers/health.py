from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.cache.redis import ping_redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/db")
async def database_health(
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    try:
        await db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is temporarily unavailable",
        ) from exc

    return {
        "status": "ok",
        "database": "reachable",
    }


@router.get("/health/redis")
async def redis_health() -> dict[str, str]:
    reachable = await ping_redis()

    return {
        "status": ("ok" if reachable else "error"),
        "redis": ("reachable" if reachable else "unreachable"),
    }

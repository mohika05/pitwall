from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.cache.redis import ping_redis


router = APIRouter(
    tags=["health"]
)


@router.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok"
    }


@router.get("/health/db")
async def database_health(
    db: AsyncSession = Depends(
        get_db_session
    ),
) -> dict[str, str]:
    await db.execute(
        text("SELECT 1")
    )

    return {
        "status": "ok",
        "database": "reachable",
    }


@router.get("/health/redis")
async def redis_health() -> dict[str, str]:
    reachable = await ping_redis()

    return {
        "status": (
            "ok"
            if reachable
            else "error"
        ),
        "redis": (
            "reachable"
            if reachable
            else "unreachable"
        ),
    }
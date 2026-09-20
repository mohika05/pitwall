import redis.asyncio as redis

from app.core.config import settings

redis_client = redis.from_url(
    settings.redis_url,
    encoding="utf-8",
    decode_responses=True,
)

async def ping_redis() -> bool:
    return bool(
        await redis_client.ping()
    )

async def close_redis() -> None:
    await redis_client.aclose()
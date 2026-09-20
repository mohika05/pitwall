from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import (
    CORSMiddleware,
)

from app.api.routers.health import (
    router as health_router,
)
from app.cache.redis import (
    close_redis,
)
from app.core.config import settings

from app.core.logging import (
    configure_logging,
)
from app.persistence.database import (
    engine,
)

from app.api.routers.replay import (
    router as replay_router,
)
from app.api.routers.websocket import (
    router as websocket_router,
)

from app.api.routers.telemetry import (
    router as telemetry_router,
)

from app.api.routers.sessions import (
    router as sessions_router,
)

from app.api.routers.catalog import (
    router as catalog_router,
)

configure_logging()

@asynccontextmanager
async def lifespan(_: FastAPI):
    yield

    await close_redis()
    await engine.dispose()

app = FastAPI(
    title="Pitwall API",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_origin
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    health_router
)

app.include_router(
    replay_router
)

app.include_router(
    websocket_router
)

app.include_router(
    telemetry_router
)

app.include_router(
    sessions_router
)

app.include_router(
    catalog_router
)
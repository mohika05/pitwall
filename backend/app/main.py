import asyncio
import logging
import time
from collections import Counter
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.api.routers import (
    analysis,
    catalog,
    health,
    live,
    preparation,
    replay,
    sessions,
    strategy,
    telemetry,
    websocket,
)
from app.cache.redis import close_redis
from app.core.config import settings
from app.core.logging import configure_logging
from app.persistence.database import engine
from app.replay.controller import replay_registry
from app.services.live import live_service
from app.services.preparation import preparation_service

configure_logging()
logger = logging.getLogger(__name__)
requests = Counter()
request_seconds = Counter()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await preparation_service.recover()

    async def maintain():
        while True:
            await asyncio.sleep(60)
            await replay_registry.collect_idle()

    maintenance = asyncio.create_task(maintain())
    try:
        yield
    finally:
        maintenance.cancel()
        await asyncio.gather(maintenance, return_exceptions=True)
        await live_service.close()
        await preparation_service.close()
        await replay_registry.close()
        await close_redis()
        await engine.dispose()


app = FastAPI(title="Pitwall API", version="0.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def observe(request: Request, call_next):
    started = time.monotonic()
    response = await call_next(request)
    route = getattr(request.scope.get("route"), "path", "unmatched")
    key = (request.method, route, response.status_code)
    duration = time.monotonic() - started
    requests[key] += 1
    request_seconds[key] += duration
    logger.info("request method=%s route=%s status=%s seconds=%.3f", *key, duration)
    return response


@app.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
async def metrics():
    lines = [
        "# TYPE pitwall_requests_total counter",
        "# TYPE pitwall_request_seconds_total counter",
    ]
    for (method, route, status), count in requests.items():
        labels = f'method="{method}",route="{route}",status="{status}"'
        lines.append(f"pitwall_requests_total{{{labels}}} {count}")
        lines.append(
            f"pitwall_request_seconds_total{{{labels}}} {request_seconds[(method, route, status)]}"
        )
    return "\n".join(lines) + "\n"


for module in (
    health,
    replay,
    websocket,
    telemetry,
    sessions,
    catalog,
    preparation,
    analysis,
    strategy,
    live,
):
    app.include_router(module.router)

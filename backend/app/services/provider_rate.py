import asyncio
import time

from app.core.config import settings

_lock = asyncio.Lock()
_last = 0.0


async def request_slot():
    """Shared budget across catalogue, historical preparation and live polling."""
    global _last
    async with _lock:
        minimum = max(
            settings.openf1_min_request_interval_seconds,
            1.1 if settings.openf1_access_token else 2.1,
        )
        await asyncio.sleep(max(0, minimum - (time.monotonic() - _last)))
        _last = time.monotonic()

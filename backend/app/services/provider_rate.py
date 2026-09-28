import asyncio
import time

from app.core.config import settings

_lock = asyncio.Lock()
_last = 0.0


async def request_slot():
    """Shared anonymous-request budget across catalogue and preparation."""
    global _last
    async with _lock:
        minimum = max(settings.openf1_min_request_interval_seconds, 2.1)
        await asyncio.sleep(max(0, minimum - (time.monotonic() - _last)))
        _last = time.monotonic()

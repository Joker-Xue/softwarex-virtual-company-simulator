"""
endpoint level rate limit tool

Simple counter rate limit based on Redis，Redis Demotes to memory counter when unavailable.
Formulation FastAPI Depends use.
"""
import time
import logging
from collections import defaultdict
from fastapi import HTTPException, Request

from app.utils.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

# memory fallback：key -> (count, window_start)
_memory_counters: dict[str, tuple[int, float]] = {}


async def check_rate_limit(key: str, max_calls: int, window_seconds: int):
    """
    Check the rate limit. If the limit is exceeded, HTTP 429 will be thrown.

    :param key: rate limit unique identifier（like "rl:generate:{user_id}"）
    :param max_calls: Maximum number of calls within the window
    :param window_seconds: Window duration（Second）
    """
    cache_key = f"rl:{key}"

    # try Redis
    current = await cache_get(cache_key)
    if current is not None:
        count = int(current.get("count", 0))
        if count >= max_calls:
            raise HTTPException(
                status_code=429,
                detail=f"Operating too frequently，{window_seconds}Try again in seconds",
            )
        await cache_set(cache_key, {"count": count + 1}, ttl=window_seconds)
        return

    # Redis Not available -> try to write new Redis msgs directory
    set_ok = await cache_set(cache_key, {"count": 1}, ttl=window_seconds)
    if set_ok:
        return

    # Redis completely unavailable，downgraded to memory counter
    now = time.time()
    entry = _memory_counters.get(cache_key)
    if entry:
        count, window_start = entry
        if now - window_start > window_seconds:
            # window expired，reset
            _memory_counters[cache_key] = (1, now)
        elif count >= max_calls:
            raise HTTPException(
                status_code=429,
                detail=f"Operating too frequently，{window_seconds}Try again in seconds",
            )
        else:
            _memory_counters[cache_key] = (count + 1, window_start)
    else:
        _memory_counters[cache_key] = (1, now)

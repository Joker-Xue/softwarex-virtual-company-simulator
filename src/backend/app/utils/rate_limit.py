"""
端点级别限流工具

基于 Redis 的简单计数器限流，Redis 不可用时降级为内存计数器。
配合 FastAPI Depends 使用。
"""
import time
import logging
from collections import defaultdict
from fastapi import HTTPException, Request

from app.utils.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

# 内存 fallback：key -> (count, window_start)
_memory_counters: dict[str, tuple[int, float]] = {}


async def check_rate_limit(key: str, max_calls: int, window_seconds: int):
    """
    检查限流。超限则抛出 HTTP 429。

    :param key: 限流唯一标识（如 "rl:generate:{user_id}"）
    :param max_calls: 窗口内最大调用次数
    :param window_seconds: 窗口时长（秒）
    """
    cache_key = f"rl:{key}"

    # 尝试 Redis
    current = await cache_get(cache_key)
    if current is not None:
        count = int(current.get("count", 0))
        if count >= max_calls:
            raise HTTPException(
                status_code=429,
                detail=f"操作过于频繁，请{window_seconds}秒后再试",
            )
        await cache_set(cache_key, {"count": count + 1}, ttl=window_seconds)
        return

    # Redis 不可用 -> 尝试写入新的 Redis 条目
    set_ok = await cache_set(cache_key, {"count": 1}, ttl=window_seconds)
    if set_ok:
        return

    # Redis 完全不可用，降级为内存计数器
    now = time.time()
    entry = _memory_counters.get(cache_key)
    if entry:
        count, window_start = entry
        if now - window_start > window_seconds:
            # 窗口过期，重置
            _memory_counters[cache_key] = (1, now)
        elif count >= max_calls:
            raise HTTPException(
                status_code=429,
                detail=f"操作过于频繁，请{window_seconds}秒后再试",
            )
        else:
            _memory_counters[cache_key] = (count + 1, window_start)
    else:
        _memory_counters[cache_key] = (1, now)

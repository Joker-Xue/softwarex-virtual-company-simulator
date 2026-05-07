"""
Redis Cache tool module

Function：
- Encapsulate Redis connection and Cache reading and writing
- Support TTL settings（default1Hour）
- Supports JSON serialization/deserialization
"""
import json
import hashlib
import os
import logging
from typing import Optional, Any

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DEFAULT_TTL = int(os.getenv("CACHE_TTL", "3600"))  # default1Hour

# Redis client（Lazy initialization）
_redis_client = None
logger = logging.getLogger(__name__)


async def get_redis():
    """GetRedisclient"""
    global _redis_client
    if not REDIS_AVAILABLE:
        return None
    if _redis_client is None:
        client = None
        try:
            client = aioredis.from_url(
                REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
            # TestsConnection
            await client.ping()
            _redis_client = client
        except Exception:
            if client is not None:
                try:
                    await client.aclose()
                except Exception:
                    pass
            _redis_client = None
            return None
    return _redis_client


async def close_redis():
    """Close overall situation Redis client（Called when the application exits）。"""
    global _redis_client
    client = _redis_client
    _redis_client = None
    if client is None:
        return
    try:
        await client.aclose()
    except Exception as exc:
        logger.debug("close_redis ignored error: %s", exc)


def make_cache_key(prefix: str, *args, **kwargs) -> str:
    """Generate Cachekey"""
    raw = f"{prefix}:{':'.join(str(a) for a in args)}"
    if kwargs:
        sorted_kwargs = sorted(kwargs.items())
        raw += ":" + ":".join(f"{k}={v}" for k, v in sorted_kwargs)
    return raw


def make_hash_key(prefix: str, data: str) -> str:
    """Generate hash-based Cachekey（for LLMCache）"""
    data_hash = hashlib.md5(data.encode()).hexdigest()
    return f"{prefix}:{data_hash}"


async def cache_get(key: str) -> Optional[Any]:
    """GetCache"""
    client = await get_redis()
    if client is None:
        return None
    try:
        value = await client.get(key)
        if value:
            return json.loads(value)
        return None
    except Exception:
        return None


async def cache_set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> bool:
    """Set up Cache"""
    client = await get_redis()
    if client is None:
        return False
    try:
        await client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
        return True
    except Exception:
        return False


async def cache_delete(key: str) -> bool:
    """Delete Cache"""
    client = await get_redis()
    if client is None:
        return False
    try:
        await client.delete(key)
        return True
    except Exception:
        return False


async def cache_clear_prefix(prefix: str) -> int:
    """Clear all Cache for the specified prefix"""
    client = await get_redis()
    if client is None:
        return 0
    try:
        keys = []
        async for key in client.scan_iter(match=f"{prefix}:*"):
            keys.append(key)
        if keys:
            await client.delete(*keys)
        return len(keys)
    except Exception:
        return 0

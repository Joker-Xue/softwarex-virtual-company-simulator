"""
Redis 缓存工具模块

功能：
- 封装Redis连接和缓存读写
- 支持TTL设置（默认1小时）
- 支持JSON序列化/反序列化
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

# Redis 配置
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DEFAULT_TTL = int(os.getenv("CACHE_TTL", "3600"))  # 默认1小时

# Redis 客户端（延迟初始化）
_redis_client = None
logger = logging.getLogger(__name__)


async def get_redis():
    """获取Redis客户端"""
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
            # 测试连接
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
    """关闭全局 Redis 客户端（应用退出时调用）。"""
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
    """生成缓存key"""
    raw = f"{prefix}:{':'.join(str(a) for a in args)}"
    if kwargs:
        sorted_kwargs = sorted(kwargs.items())
        raw += ":" + ":".join(f"{k}={v}" for k, v in sorted_kwargs)
    return raw


def make_hash_key(prefix: str, data: str) -> str:
    """生成基于哈希的缓存key（用于LLM缓存）"""
    data_hash = hashlib.md5(data.encode()).hexdigest()
    return f"{prefix}:{data_hash}"


async def cache_get(key: str) -> Optional[Any]:
    """获取缓存"""
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
    """设置缓存"""
    client = await get_redis()
    if client is None:
        return False
    try:
        await client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
        return True
    except Exception:
        return False


async def cache_delete(key: str) -> bool:
    """删除缓存"""
    client = await get_redis()
    if client is None:
        return False
    try:
        await client.delete(key)
        return True
    except Exception:
        return False


async def cache_clear_prefix(prefix: str) -> int:
    """清除指定前缀的所有缓存"""
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

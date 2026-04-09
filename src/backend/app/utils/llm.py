"""
大模型调用封装

功能：
- 支持OpenAI兼容接口（如DeepSeek、通义千问、智谱GLM等）
- 多模型轮询调度，分散单一供应商压力
- 故障自动切换：超时/限流/错误时自动跳到下一个模型
- 统一请求/响应格式
- 错误重试（指数退避）
- 结果缓存到Redis（相同输入hash做key，TTL=24h）
- 全局并发控制（asyncio.Semaphore）
"""
import os
import json
import asyncio
import hashlib
import logging
import time
from typing import Optional, Dict, Any, List, AsyncGenerator

import httpx
from dotenv import load_dotenv

from app.utils.cache import cache_get, cache_set, make_hash_key

logger = logging.getLogger(__name__)


def get_llm_settings() -> Dict[str, Any]:
    """Read LLM settings at call time so import order does not break env loading."""
    load_dotenv()
    return {
        "api_key": os.getenv("LLM_API_KEY", ""),
        "base_url": os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1"),
        "model": os.getenv("LLM_MODEL", "deepseek-chat"),
        "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "4096")),
        "temperature": float(os.getenv("LLM_TEMPERATURE", "0.7")),
    }


# ---------------------------------------------------------------------------
# 多模型池：轮询 + 故障切换
# ---------------------------------------------------------------------------
# 环境变量 LLM_POOL 可配置逗号分隔的模型列表，留空则只用 LLM_MODEL
# 例: LLM_POOL=DeepSeek-V3.2,GLM-4.5-Air,Qwen3-32B,ERNIE-4.5-300B-A47B,Hunyuan-A13B-Instruct

def _parse_model_pool() -> List[str]:
    """Parse model pool from env. Returns list of model IDs."""
    load_dotenv()
    pool_str = os.getenv("LLM_POOL", "").strip()
    if pool_str:
        return [m.strip() for m in pool_str.split(",") if m.strip()]
    return []


class ModelRouter:
    """Round-robin model selector with health tracking."""

    def __init__(self) -> None:
        self._index = 0
        self._lock = asyncio.Lock()
        # model_id -> timestamp when it was marked unhealthy (0 = healthy)
        self._cooldowns: Dict[str, float] = {}
        # How long to cool down a failing model (seconds)
        self.cooldown_seconds = float(os.getenv("LLM_POOL_COOLDOWN", "60"))

    def get_pool(self) -> List[str]:
        """Return current model pool (re-read each time for hot reload)."""
        pool = _parse_model_pool()
        if not pool:
            settings = get_llm_settings()
            pool = [settings["model"]]
        return pool

    async def next_model(self, caller_model: Optional[str] = None) -> str:
        """Pick the next healthy model via round-robin.

        If *caller_model* is explicitly set (not None), use it directly
        without rotation — this preserves backward compatibility when a
        caller pins a specific model.
        """
        if caller_model is not None:
            return caller_model

        pool = self.get_pool()
        if len(pool) == 1:
            return pool[0]

        now = time.monotonic()
        async with self._lock:
            # Try up to len(pool) candidates
            for _ in range(len(pool)):
                candidate = pool[self._index % len(pool)]
                self._index += 1
                # Check cooldown
                cooldown_start = self._cooldowns.get(candidate, 0)
                if cooldown_start and (now - cooldown_start) < self.cooldown_seconds:
                    continue  # skip this model, it's cooling down
                # Clear expired cooldown
                self._cooldowns.pop(candidate, None)
                return candidate

            # All models are cooling down — pick the one whose cooldown
            # started earliest (closest to recovery)
            self._index += 1
            oldest = min(pool, key=lambda m: self._cooldowns.get(m, 0))
            self._cooldowns.pop(oldest, None)
            return oldest

    async def get_fallback_models(self, failed_model: str) -> List[str]:
        """Return other models to try after *failed_model* fails."""
        pool = self.get_pool()
        return [m for m in pool if m != failed_model]

    def mark_unhealthy(self, model_id: str) -> None:
        """Mark a model as temporarily unhealthy."""
        self._cooldowns[model_id] = time.monotonic()
        logger.warning(f"模型 {model_id} 标记为不健康，冷却 {self.cooldown_seconds}s")

    def mark_healthy(self, model_id: str) -> None:
        """Clear cooldown for a model that succeeded."""
        self._cooldowns.pop(model_id, None)


# Singleton router
_router = ModelRouter()

# 重试配置
MAX_RETRIES = 2  # per-model retries (total attempts = retries × models)
RETRY_BASE_DELAY = 1  # 秒

# 全局并发控制：限制同时在飞的 LLM 请求数
_LLM_CONCURRENCY = int(os.getenv("LLM_MAX_CONCURRENCY", "5"))
_semaphore = asyncio.Semaphore(_LLM_CONCURRENCY)

# 缓存TTL
LLM_CACHE_TTL = int(os.getenv("LLM_CACHE_TTL", "86400"))  # 24小时


# ---------------------------------------------------------------------------
# 内部：对单个模型发起请求（含重试）
# ---------------------------------------------------------------------------

async def _call_single_model(
    model: str,
    messages: List[Dict[str, str]],
    temperature: float,
    max_tokens: int,
    pii_mapping: Any,
    request_timeout_s: float = 90.0,
    max_retries: int = MAX_RETRIES,
) -> Dict[str, Any]:
    """Call a single model with retries. Raises on total failure."""
    settings = get_llm_settings()

    request_body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings['api_key']}",
    }

    last_error = None
    for attempt in range(max_retries):
        try:
            async with _semaphore:
                async with httpx.AsyncClient(timeout=request_timeout_s) as client:
                    response = await client.post(
                        f"{settings['base_url']}/chat/completions",
                        json=request_body,
                        headers=headers,
                    )

            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                if pii_mapping:
                    from app.security.llm_gateway import restore_from_llm
                    content = restore_from_llm(content, pii_mapping)
                _router.mark_healthy(model)
                return {
                    "content": content,
                    "usage": data.get("usage", {}),
                    "model": data.get("model", model),
                    "cached": False,
                }

            elif response.status_code == 429:
                last_error = f"HTTP 429: Rate limited ({model})"
                logger.warning(f"[{model}] 限流，尝试 {attempt + 1}/{max_retries}")
                await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))

            else:
                last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                logger.error(f"[{model}] API错误: {last_error}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))

        except httpx.TimeoutException:
            last_error = f"请求超时 ({model})"
            logger.warning(f"[{model}] 超时，尝试 {attempt + 1}/{max_retries}")
            if attempt < max_retries - 1:
                await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))

        except Exception as e:
            last_error = f"{e.__class__.__name__}: {e} ({model})"
            logger.error(f"[{model}] 异常: {e}，尝试 {attempt + 1}/{max_retries}")
            if attempt < max_retries - 1:
                await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))

    # This model exhausted its retries
    _router.mark_unhealthy(model)
    raise RuntimeError(last_error)


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------

async def call_llm(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    use_cache: bool = True,
    cache_prefix: str = "llm",
    request_timeout_s: Optional[float] = None,
    max_retries: Optional[int] = None,
    max_fallback_models: Optional[int] = None,
) -> Dict[str, Any]:
    """
    调用大模型（支持多模型轮询 + 故障切换）

    Args:
        messages: 对话消息列表 [{"role": "system/user/assistant", "content": "..."}]
        model: 指定模型名称。为 None 时使用模型池轮询
        temperature: 温度参数
        max_tokens: 最大生成token数
        use_cache: 是否使用缓存
        cache_prefix: 缓存key前缀

    Returns:
        {
            "content": "模型回复内容",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "model": "model_name",
            "cached": False
        }
    """
    settings = get_llm_settings()
    temperature = temperature if temperature is not None else settings["temperature"]
    max_tokens = max_tokens or settings["max_tokens"]
    request_timeout_s = float(request_timeout_s or 90.0)
    retries = int(MAX_RETRIES if max_retries is None else max_retries)
    retries = max(1, retries)

    # ── LLM 隐私网关拦截 ──
    from app.security.llm_gateway import gateway_intercept, restore_from_llm
    pii_mapping = None
    try:
        messages, pii_mapping = await gateway_intercept(messages)
    except ValueError as e:
        return {"content": "", "error": str(e), "usage": {}, "model": model or "", "cached": False}

    # 检查缓存（用 messages hash，不含 model 名——任何模型的缓存都可命中）
    cache_key = None
    if use_cache:
        cache_input = json.dumps({"messages": messages}, ensure_ascii=False)
        cache_key = make_hash_key(cache_prefix, cache_input)
        cached = await cache_get(cache_key)
        if cached:
            cached["cached"] = True
            return cached

    # 选主模型
    primary = await _router.next_model(caller_model=model)

    # 尝试主模型
    try:
        result = await _call_single_model(
            primary,
            messages,
            temperature,
            max_tokens,
            pii_mapping,
            request_timeout_s=request_timeout_s,
            max_retries=retries,
        )
        if use_cache and cache_key:
            await cache_set(cache_key, result, ttl=LLM_CACHE_TTL)
        return result
    except RuntimeError as primary_err:
        logger.warning(f"主模型 {primary} 失败: {primary_err}，尝试备选模型")

    # 故障切换：尝试其他模型
    fallbacks = await _router.get_fallback_models(primary)
    if max_fallback_models is not None:
        fallbacks = fallbacks[: max(0, int(max_fallback_models))]
    for fb_model in fallbacks:
        try:
            logger.info(f"切换到备选模型: {fb_model}")
            result = await _call_single_model(
                fb_model,
                messages,
                temperature,
                max_tokens,
                pii_mapping,
                request_timeout_s=request_timeout_s,
                max_retries=retries,
            )
            if use_cache and cache_key:
                await cache_set(cache_key, result, ttl=LLM_CACHE_TTL)
            return result
        except RuntimeError as fb_err:
            logger.warning(f"备选模型 {fb_model} 也失败: {fb_err}")
            continue

    # 所有模型都失败
    pool = _router.get_pool()
    return {
        "content": "",
        "error": f"所有模型均调用失败（尝试了 {', '.join(pool)}）",
        "usage": {},
        "model": primary,
        "cached": False,
    }


async def call_llm_stream(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    request_timeout_s: Optional[float] = None,
    max_fallback_models: Optional[int] = None,
) -> AsyncGenerator[str, None]:
    """
    流式调用大模型（用于SSE输出，支持多模型故障切换）

    Args:
        messages: 对话消息列表
        model: 模型名称，为 None 时使用模型池轮询
        temperature: 温度参数
        max_tokens: 最大token数

    Yields:
        逐段返回的文本内容
    """
    settings = get_llm_settings()
    temperature = temperature if temperature is not None else settings["temperature"]
    max_tokens = max_tokens or settings["max_tokens"]
    request_timeout_s = float(request_timeout_s or 120.0)

    # Build candidate list: primary first, then fallbacks
    primary = await _router.next_model(caller_model=model)
    candidates = [primary] + await _router.get_fallback_models(primary)
    if max_fallback_models is not None:
        max_fb = max(0, int(max_fallback_models))
        candidates = [primary] + candidates[1 : 1 + max_fb]

    for candidate in candidates:
        request_body = {
            "model": candidate,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings['api_key']}",
        }

        try:
            got_content = False
            async with _semaphore:
                async with httpx.AsyncClient(timeout=request_timeout_s) as client:
                    async with client.stream(
                        "POST",
                        f"{settings['base_url']}/chat/completions",
                        json=request_body,
                        headers=headers,
                    ) as response:
                        if response.status_code != 200:
                            raise RuntimeError(f"HTTP {response.status_code}")
                        async for line in response.aiter_lines():
                            if not line.startswith("data: "):
                                continue
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                delta = data["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    got_content = True
                                    yield content
                            except (json.JSONDecodeError, KeyError, IndexError):
                                continue

            if got_content:
                _router.mark_healthy(candidate)
                return  # success, stop trying other models

        except Exception as e:
            logger.warning(f"[{candidate}] 流式调用失败: {e}，尝试下一个模型")
            _router.mark_unhealthy(candidate)
            continue

    # All models failed
    yield "\n[错误: 所有模型流式调用均失败]"


async def call_llm_json(
    prompt: str,
    system_prompt: str = "你是一个专业的职业规划助手。请严格按照要求输出JSON格式的结果。",
    model: Optional[str] = None,
    use_cache: bool = True,
    cache_prefix: str = "llm_json",
    max_tokens: Optional[int] = None,
    request_timeout_s: Optional[float] = None,
    max_retries: Optional[int] = None,
    max_fallback_models: Optional[int] = None,
) -> Dict[str, Any]:
    """
    调用大模型并解析JSON响应（便捷方法）

    Args:
        prompt: 用户提示词
        system_prompt: 系统提示词
        model: 模型名称，为 None 时使用模型池轮询
        use_cache: 是否使用缓存
        cache_prefix: 缓存前缀

    Returns:
        解析后的JSON字典，失败则返回包含error字段的字典
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    result = await call_llm(
        messages=messages,
        model=model,
        temperature=0.3,  # JSON输出用低温度
        max_tokens=max_tokens,
        use_cache=use_cache,
        cache_prefix=cache_prefix,
        request_timeout_s=request_timeout_s,
        max_retries=max_retries,
        max_fallback_models=max_fallback_models,
    )

    if result.get("error"):
        return {"error": result["error"]}

    content = result.get("content", "")

    # 尝试提取JSON
    try:
        # 尝试直接解析
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 尝试从markdown代码块中提取
    if "```json" in content:
        start = content.index("```json") + 7
        end = content.index("```", start)
        try:
            return json.loads(content[start:end].strip())
        except json.JSONDecodeError:
            pass
    elif "```" in content:
        start = content.index("```") + 3
        end = content.index("```", start)
        try:
            return json.loads(content[start:end].strip())
        except json.JSONDecodeError:
            pass

    return {"error": "无法解析LLM输出为JSON", "raw_content": content}

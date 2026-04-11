"""
Large Model call encapsulation

Function：
- Support OpenAIcompatible interface（Such as DeepSeek, Tongyi Qianwen, GLM, etc.）
- Multi-model polling scheduling，Distribute pressure to a single supplier
- failover：Automatically jump to the next Model when timeout/rate limit/error occurs
- Unify ask/response format
- Retry on error（Exponential save）
- Results Cache to Redis（Use the same input hash as key，TTL=24h）
- Global concurrency control（asyncio.Semaphore）
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
# Multiple Model Pool：poll + failover
# ---------------------------------------------------------------------------
# Environment variable LLM_POOL Configurable comma separated list of models，Leave blank to use only LLM_MODEL
# : LLM_POOL=DeepSeek-V3.2,GLM-4.5-Air,Qwen3-32B,ERNIE-4.5-300B-A47B,Hunyuan-A13B-Instruct

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
        logger.warning(f"Model {model_id} mark is unhealthy，cooling {self.cooldown_seconds}s")

    def mark_healthy(self, model_id: str) -> None:
        """Clear cooldown for a model that succeeded."""
        self._cooldowns.pop(model_id, None)


# Singleton router
_router = ModelRouter()

# Retry configuration
MAX_RETRIES = 2  # per-model retries (total attempts = retries × models)
RETRY_BASE_DELAY = 1  # Second

# Global concurrency control：limit the number of LLM asks flying at the same time
_LLM_CONCURRENCY = int(os.getenv("LLM_MAX_CONCURRENCY", "5"))
_semaphore = asyncio.Semaphore(_LLM_CONCURRENCY)

# CacheTTL
LLM_CACHE_TTL = int(os.getenv("LLM_CACHE_TTL", "86400"))  # 24Hour


# ---------------------------------------------------------------------------
# internal：Initiate an ask for a single Model（With retry）
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
                logger.warning(f"[{model}] rate limit，try {attempt + 1}/{max_retries}")
                await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))

            else:
                last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                logger.error(f"[{model}] APImistake: {last_error}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))

        except httpx.TimeoutException:
            last_error = f"ask timeout ({model})"
            logger.warning(f"[{model}] time out，try {attempt + 1}/{max_retries}")
            if attempt < max_retries - 1:
                await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))

        except Exception as e:
            last_error = f"{e.__class__.__name__}: {e} ({model})"
            logger.error(f"[{model}] abnormal: {e}，try {attempt + 1}/{max_retries}")
            if attempt < max_retries - 1:
                await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))

    # This model exhausted its retries
    _router.mark_unhealthy(model)
    raise RuntimeError(last_error)


# ---------------------------------------------------------------------------
# public interface
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
    Call large Model（Support multi-model polling + failover）

    Args:
        messages: Conversation message list [{"role": "system/user/assistant", "content": "..."}]
        model: Specify Model name. is None When using model pool polling
        temperature: Temperature parameters
        max_tokens: Maximum number of generated tokens
        use_cache: Whether to use Cache
        cache_prefix: Cachekeyprefix

    Returns:
        {
            "content": "Model reply content",
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

    # ── LLM privacy gateway interception ──
    from app.security.llm_gateway import gateway_intercept, restore_from_llm
    pii_mapping = None
    try:
        messages, pii_mapping = await gateway_intercept(messages)
    except ValueError as e:
        return {"content": "", "error": str(e), "usage": {}, "model": model or "", "cached": False}

    # Check Cache（for messages hash，Does not contain model name - Cache of any model can be hit）
    cache_key = None
    if use_cache:
        cache_input = json.dumps({"messages": messages}, ensure_ascii=False)
        cache_key = make_hash_key(cache_prefix, cache_input)
        cached = await cache_get(cache_key)
        if cached:
            cached["cached"] = True
            return cached

    # Select the main model
    primary = await _router.next_model(caller_model=model)

    # try main Model
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
        logger.warning(f"Primary Model {primary} failed: {primary_err}，try alternative Model")

    # failover：try other models
    fallbacks = await _router.get_fallback_models(primary)
    if max_fallback_models is not None:
        fallbacks = fallbacks[: max(0, int(max_fallback_models))]
    for fb_model in fallbacks:
        try:
            logger.info(f"Switch to alternative Model: {fb_model}")
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
            logger.warning(f"Alternative Model {fb_model} also failed: {fb_err}")
            continue

    # All models fail
    pool = _router.get_pool()
    return {
        "content": "",
        "error": f"All Model calls failed（Try {', '.join(pool)}）",
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
    Streaming call to large Model（for SSE output，Support multiple Modelfailover）

    Args:
        messages: Conversation message list
        model: Model name，None When using model pool polling
        temperature: Temperature parameters
        max_tokens: Maximum number of tokens

    Yields:
        Text content of Back paragraph by paragraph
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
            logger.warning(f"[{candidate}] Streaming call failed: {e}，try next Model")
            _router.mark_unhealthy(candidate)
            continue

    # All models failed
    yield "\n[mistake: All Model streaming calls fail]"


async def call_llm_json(
    prompt: str,
    system_prompt: str = "You are a professional career planning assistant. Please strictly follow the requirements to output the results in JSON format..",
    model: Optional[str] = None,
    use_cache: bool = True,
    cache_prefix: str = "llm_json",
    max_tokens: Optional[int] = None,
    request_timeout_s: Optional[float] = None,
    max_retries: Optional[int] = None,
    max_fallback_models: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Call the big Model and parse the JSON response（Convenience method）

    Args:
        prompt: User prompt words
        system_prompt: System prompt word
        model: Model name，None When using model pool polling
        use_cache: Whether to use Cache
        cache_prefix: Cacheprefix

    Returns:
        Parsed JSON dictionary，On failure, Back is a dictionary containing the error field.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    result = await call_llm(
        messages=messages,
        model=model,
        temperature=0.3,  # JSON output with low temperature
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

    # try to extract JSON
    try:
        # try to parse directly
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try to extract from markdown code block
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

    return {"error": "Unable to parse LLM output into JSON", "raw_content": content}

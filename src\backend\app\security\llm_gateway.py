"""
支柱5：LLM 隐私网关

核心创新：可逆 PII 脱敏。
- 调用 LLM 前扫描 prompt 中的 PII，替换为占位符
- LLM 返回后将占位符还原为真实值
- 用户体验无损，但第三方 LLM 永远看不到真实 PII
- TOP_SECRET 级数据直接拒绝发送
"""
import re
import logging
from typing import Optional
from app.security.classification import DataLevel

logger = logging.getLogger(__name__)

# PII 模式与占位符模板
_PII_PATTERNS = [
    (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "ID_CARD", "身份证号"),
    (re.compile(r"(?<!\d)\d{16,19}(?!\d)"), "BANK_CARD", "银行卡号"),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "PHONE", "手机号"),
    (re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"), "EMAIL", "邮箱"),
]

# 中文姓名模式（2-4个汉字，前后非汉字）
_NAME_RE = re.compile(r"(?<![一-龥])[一-龥]{2,4}(?![一-龥])")

# TOP_SECRET 关键词（检测到则拒绝发送）
_TOP_SECRET_KEYWORDS = ["身份证号", "银行卡号", "密码"]


class PIIMapping:
    """会话级 PII 替换映射表"""

    def __init__(self):
        self._map: dict[str, str] = {}  # 占位符 -> 原始值
        self._reverse: dict[str, str] = {}  # 原始值 -> 占位符
        self._counters: dict[str, int] = {}

    def add(self, original: str, pii_type: str) -> str:
        """注册一个 PII 值，返回对应的占位符"""
        if original in self._reverse:
            return self._reverse[original]
        self._counters.setdefault(pii_type, 0)
        self._counters[pii_type] += 1
        placeholder = f"[{pii_type}_{self._counters[pii_type]:03d}]"
        self._map[placeholder] = original
        self._reverse[original] = placeholder
        return placeholder

    def restore(self, text: str) -> str:
        """将文本中的占位符还原为真实值"""
        for placeholder, original in self._map.items():
            text = text.replace(placeholder, original)
        return text

    @property
    def summary(self) -> dict:
        """返回脱敏摘要（不含原始值），用于审计"""
        return {pii_type: count for pii_type, count in self._counters.items()}


def check_top_secret(text: str) -> bool:
    """检测文本是否包含 TOP_SECRET 级数据"""
    for kw in _TOP_SECRET_KEYWORDS:
        if kw in text:
            return True
    # 检测身份证号模式
    if re.search(r"(?<!\d)\d{17}[\dXx](?!\d)", text):
        return True
    return False


def sanitize_for_llm(text: str, mapping: Optional[PIIMapping] = None) -> tuple[str, PIIMapping]:
    """
    对发送给 LLM 的文本进行可逆 PII 脱敏。

    Returns:
        (脱敏后的文本, PII映射表)
    """
    if mapping is None:
        mapping = PIIMapping()

    if not text:
        return text, mapping

    # 按优先级替换 PII（长模式优先）
    for pattern, pii_type, label in _PII_PATTERNS:
        for match in pattern.finditer(text):
            original = match.group()
            placeholder = mapping.add(original, pii_type)
            text = text.replace(original, placeholder)

    return text, mapping


def restore_from_llm(text: str, mapping: PIIMapping) -> str:
    """将 LLM 返回的文本中的占位符还原为真实值"""
    if not text or not mapping:
        return text
    return mapping.restore(text)


async def gateway_intercept(
    messages: list[dict],
) -> tuple[list[dict], PIIMapping]:
    """
    LLM 隐私网关拦截入口。

    在调用 LLM 前处理所有消息：
    1. 检测 TOP_SECRET 数据 → 拒绝
    2. 替换 PII → 返回脱敏后的消息和映射表
    """
    mapping = PIIMapping()
    sanitized_messages = []

    for msg in messages:
        content = msg.get("content", "")

        # TOP_SECRET 检测
        if check_top_secret(content):
            logger.warning("LLM 网关拦截: 检测到 TOP_SECRET 级数据，拒绝发送")
            raise ValueError("检测到绝密级数据，禁止发送至第三方 LLM")

        # PII 脱敏
        sanitized_content, mapping = sanitize_for_llm(content, mapping)
        sanitized_messages.append({**msg, "content": sanitized_content})

    if mapping.summary:
        logger.info("LLM 网关: PII 脱敏摘要 %s", mapping.summary)

    return sanitized_messages, mapping

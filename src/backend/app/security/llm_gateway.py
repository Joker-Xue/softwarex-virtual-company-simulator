"""
Pillar 5：LLM privacy gateway

core innovation：Reversible PII Desensitization.
- Scan prompt for PII before calling LLM，Replace with placeholder
- LLM Return the placeholder to its true value after Back
- No loss of user experience，But third-party LLMs never see real PII
- TOP_SECRET Level data directly rejectSend
"""
import re
import logging
from typing import Optional
from app.security.classification import DataLevel

logger = logging.getLogger(__name__)

# PII Patterns and placeholder templates
_PII_PATTERNS = [
    (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "ID_CARD", "ID number"),
    (re.compile(r"(?<!\d)\d{16,19}(?!\d)"), "BANK_CARD", "bank card number"),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "PHONE", "Phone number"),
    (re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"), "EMAIL", "email"),
]

# Chinese name pattern（2-4 Chinese characters，Non-Chinese characters before and after）
_NAME_RE = re.compile(r"(?<![-])[-]{2,4}(?![-])")

# TOP_SECRET keywords（Detection then rejectSend）
_TOP_SECRET_KEYWORDS = ["ID number", "bank card number", "password"]


class PIIMapping:
    """Session-level PII replacement mapping table"""

    def __init__(self):
        self._map: dict[str, str] = {}  # placeholder -> original value
        self._reverse: dict[str, str] = {}  # original value -> placeholder
        self._counters: dict[str, int] = {}

    def add(self, original: str, pii_type: str) -> str:
        """register a PII value，The placeholder corresponding to Back"""
        if original in self._reverse:
            return self._reverse[original]
        self._counters.setdefault(pii_type, 0)
        self._counters[pii_type] += 1
        placeholder = f"[{pii_type}_{self._counters[pii_type]:03d}]"
        self._map[placeholder] = original
        self._reverse[original] = placeholder
        return placeholder

    def restore(self, text: str) -> str:
        """Restore placeholders in text to real values"""
        for placeholder, original in self._map.items():
            text = text.replace(placeholder, original)
        return text

    @property
    def summary(self) -> dict:
        """BackDesensitization summary（Does not contain original value），for audit"""
        return {pii_type: count for pii_type, count in self._counters.items()}


def check_top_secret(text: str) -> bool:
    """Whether the Detection text includes TOP_SECRET level data"""
    for kw in _TOP_SECRET_KEYWORDS:
        if kw in text:
            return True
    # DetectionID number mode
    if re.search(r"(?<!\d)\d{17}[\dXx](?!\d)", text):
        return True
    return False


def sanitize_for_llm(text: str, mapping: Optional[PIIMapping] = None) -> tuple[str, PIIMapping]:
    """
    Perform reversible PII Desensitization on text sent to LLM.

    Returns:
        (Text after Desensitization, PII mapping table)
    """
    if mapping is None:
        mapping = PIIMapping()

    if not text:
        return text, mapping

    # Replace PII by priority（long mode first）
    for pattern, pii_type, label in _PII_PATTERNS:
        for match in pattern.finditer(text):
            original = match.group()
            placeholder = mapping.add(original, pii_type)
            text = text.replace(original, placeholder)

    return text, mapping


def restore_from_llm(text: str, mapping: PIIMapping) -> str:
    """Restore placeholder in text of LLM Back to real value"""
    if not text or not mapping:
        return text
    return mapping.restore(text)


async def gateway_intercept(
    messages: list[dict],
) -> tuple[list[dict], PIIMapping]:
    """
    LLM privacy gateway intercept entry。

    Process all information before calling LLM：
    1. Detection TOP_SECRET data → reject
    2. Replace PII  information and mapping table after BackDesensitization
    """
    mapping = PIIMapping()
    sanitized_messages = []

    for msg in messages:
        content = msg.get("content", "")

        # TOP_SECRET Detection
        if check_top_secret(content):
            logger.warning("LLM Gateway interception: Detection to TOP_SECRET level data，rejectSend")
            raise ValueError("Detection to top secret level data，Send to third-party LLM is prohibited")

        # PII Desensitization
        sanitized_content, mapping = sanitize_for_llm(content, mapping)
        sanitized_messages.append({**msg, "content": sanitized_content})

    if mapping.summary:
        logger.info("LLM Gateway: PII Desensitization summary %s", mapping.summary)

    return sanitized_messages, mapping

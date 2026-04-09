"""
输入清洗与验证工具
"""
import re
import html


def sanitize_text(text: str) -> str:
    """基础 XSS 和注入防护：转义 HTML 实体并移除残留标签"""
    text = html.escape(text)
    text = re.sub(r'<[^>]+>', '', text)  # 移除残留 HTML 标签
    return text.strip()


def validate_mbti(mbti: str) -> str:
    """
    校验 MBTI 必须是合法的 4 字母组合。
    返回大写标准形式，不合法则抛出 ValueError。
    """
    valid_chars = [('E', 'I'), ('S', 'N'), ('T', 'F'), ('J', 'P')]
    if len(mbti) != 4:
        raise ValueError("MBTI必须是4个字母")
    for i, (a, b) in enumerate(valid_chars):
        if mbti[i].upper() not in (a, b):
            raise ValueError(f"MBTI第{i+1}位必须是{a}或{b}")
    return mbti.upper()


def clamp_affinity(value: int | float) -> int:
    """将亲密度夹紧到 [0, 100]"""
    return min(100, max(0, int(value)))

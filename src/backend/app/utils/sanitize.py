"""
Input Cleaning and Validation Tools
"""
import re
import html


def sanitize_text(text: str) -> str:
    """Base XSS and injection protection：Escape HTML entities and remove residual tags"""
    text = html.escape(text)
    text = re.sub(r'<[^>]+>', '', text)  # Remove residual HTML tags
    return text.strip()


def validate_mbti(mbti: str) -> str:
    """
    Verification MBTI must be a legal 4-letter combination.
    Back capital standard form，If it is illegal, a ValueError will be thrown.
    """
    valid_chars = [('E', 'I'), ('S', 'N'), ('T', 'F'), ('J', 'P')]
    if len(mbti) != 4:
        raise ValueError("MBTI must be 4 letters")
    for i, (a, b) in enumerate(valid_chars):
        if mbti[i].upper() not in (a, b):
            raise ValueError(f"MBTI digit {i+1} must be {a} or {b}")
    return mbti.upper()


def clamp_affinity(value: int | float) -> int:
    """Clamp affinity to [0, 100]"""
    return min(100, max(0, int(value)))

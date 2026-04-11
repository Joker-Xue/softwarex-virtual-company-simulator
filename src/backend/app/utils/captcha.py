"""
SVG Verification code generation + memory storage（Get the scoop with signed tokens）
Pure Python implementation，No additional image library dependencies required
"""
import uuid
import time
import random
import string
import os

from jose import jwt, ExpiredSignatureError, JWTError

# Exclude confusing characters 0OIl1
CHARSET = "".join(
    c for c in string.ascii_uppercase + string.digits
    if c not in "OIL01"
)

# Memory storage: captcha_id -> (answer, expire_timestamp)
_store: dict[str, tuple[str, float]] = {}

CAPTCHA_LENGTH = 4
CAPTCHA_TTL = 300  # 5 minutes
CAPTCHA_TOKEN_TYPE = "captcha"
CAPTCHA_SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here-change-in-production")
CAPTCHA_ALGORITHM = os.getenv("ALGORITHM", "HS256")


def _cleanup() -> None:
    """Clear expired verification codes"""
    now = time.time()
    expired = [k for k, (_, exp) in _store.items() if exp < now]
    for k in expired:
        _store.pop(k, None)


def _build_signed_token(captcha_uuid: str, answer: str, expire_ts: float) -> str:
    """Build signed tokens that can be verified across processes."""
    payload = {
        "cid": captcha_uuid,
        "ans": answer,
        "exp": int(expire_ts),
        "typ": CAPTCHA_TOKEN_TYPE,
    }
    return jwt.encode(payload, CAPTCHA_SECRET_KEY, algorithm=CAPTCHA_ALGORITHM)


def _verify_signed_token(captcha_id: str, code: str) -> bool:
    """On local memory miss，fallback to signed token verification."""
    try:
        payload = jwt.decode(
            captcha_id,
            CAPTCHA_SECRET_KEY,
            algorithms=[CAPTCHA_ALGORITHM],
        )
    except (ExpiredSignatureError, JWTError):
        return False

    if payload.get("typ") != CAPTCHA_TOKEN_TYPE:
        return False

    answer = str(payload.get("ans", ""))
    if not answer:
        return False
    return code.strip().upper() == answer.upper()


def generate_captcha() -> tuple[str, str]:
    """
    Generate SVG verification code。
    Back (captcha_id, svg_string)
    """
    _cleanup()

    answer = "".join(random.choices(CHARSET, k=CAPTCHA_LENGTH))
    captcha_uuid = uuid.uuid4().hex
    expire_ts = time.time() + CAPTCHA_TTL
    captcha_id = _build_signed_token(captcha_uuid, answer, expire_ts)
    # Keep memory records for one-time consumption by a single process；Cross-process fallback signature verification。
    _store[captcha_id] = (answer, expire_ts)

    width, height = 160, 50
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"'
        f' viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#f1f5f9"/>',
    ]

    # interference line
    for _ in range(5):
        x1, y1 = random.randint(0, width), random.randint(0, height)
        x2, y2 = random.randint(0, width), random.randint(0, height)
        color = f"rgb({random.randint(160,220)},{random.randint(160,220)},{random.randint(160,220)})"
        parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"'
            f' stroke="{color}" stroke-width="{random.uniform(1,2):.1f}"/>'
        )

    # Noise
    for _ in range(30):
        cx, cy = random.randint(0, width), random.randint(0, height)
        r = random.uniform(0.5, 1.5)
        color = f"rgb({random.randint(150,210)},{random.randint(150,210)},{random.randint(150,210)})"
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}"/>')

    # character
    spacing = width / (CAPTCHA_LENGTH + 1)
    for i, ch in enumerate(answer):
        x = spacing * (i + 1) + random.randint(-5, 5)
        y = height / 2 + random.randint(-3, 3)
        angle = random.randint(-25, 25)
        size = random.randint(22, 28)
        color = f"rgb({random.randint(30,100)},{random.randint(30,100)},{random.randint(30,100)})"
        parts.append(
            f'<text x="{x}" y="{y}" font-size="{size}" font-weight="bold"'
            f' fill="{color}" text-anchor="middle" dominant-baseline="central"'
            f' transform="rotate({angle},{x},{y})">{ch}</text>'
        )

    parts.append("</svg>")
    return captcha_id, "".join(parts)


def verify_captcha(captcha_id: str, code: str) -> bool:
    """
    Verify verification code（Disposable，Delete immediately after verification）。
    """
    if not code:
        return False

    entry = _store.pop(captcha_id, None)
    if entry is None:
        return _verify_signed_token(captcha_id, code)
    answer, expire = entry
    if time.time() > expire:
        return False
    return code.strip().upper() == answer.upper()

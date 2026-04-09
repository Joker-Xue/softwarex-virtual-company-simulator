"""
SVG 验证码生成 + 内存存储（带签名令牌兜底）
纯 Python 实现，无需额外图片库依赖
"""
import uuid
import time
import random
import string
import os

from jose import jwt, ExpiredSignatureError, JWTError

# 排除易混淆字符 0OIl1
CHARSET = "".join(
    c for c in string.ascii_uppercase + string.digits
    if c not in "OIL01"
)

# 内存存储: captcha_id -> (answer, expire_timestamp)
_store: dict[str, tuple[str, float]] = {}

CAPTCHA_LENGTH = 4
CAPTCHA_TTL = 300  # 5 分钟
CAPTCHA_TOKEN_TYPE = "captcha"
CAPTCHA_SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here-change-in-production")
CAPTCHA_ALGORITHM = os.getenv("ALGORITHM", "HS256")


def _cleanup() -> None:
    """清理过期验证码"""
    now = time.time()
    expired = [k for k, (_, exp) in _store.items() if exp < now]
    for k in expired:
        _store.pop(k, None)


def _build_signed_token(captcha_uuid: str, answer: str, expire_ts: float) -> str:
    """构建可跨进程校验的签名令牌。"""
    payload = {
        "cid": captcha_uuid,
        "ans": answer,
        "exp": int(expire_ts),
        "typ": CAPTCHA_TOKEN_TYPE,
    }
    return jwt.encode(payload, CAPTCHA_SECRET_KEY, algorithm=CAPTCHA_ALGORITHM)


def _verify_signed_token(captcha_id: str, code: str) -> bool:
    """在本地内存未命中时，回退到签名令牌校验。"""
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
    生成 SVG 验证码。
    返回 (captcha_id, svg_string)
    """
    _cleanup()

    answer = "".join(random.choices(CHARSET, k=CAPTCHA_LENGTH))
    captcha_uuid = uuid.uuid4().hex
    expire_ts = time.time() + CAPTCHA_TTL
    captcha_id = _build_signed_token(captcha_uuid, answer, expire_ts)
    # 保留内存记录用于单进程一次性消费；跨进程则回退签名验签。
    _store[captcha_id] = (answer, expire_ts)

    width, height = 160, 50
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"'
        f' viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#f1f5f9"/>',
    ]

    # 干扰线
    for _ in range(5):
        x1, y1 = random.randint(0, width), random.randint(0, height)
        x2, y2 = random.randint(0, width), random.randint(0, height)
        color = f"rgb({random.randint(160,220)},{random.randint(160,220)},{random.randint(160,220)})"
        parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"'
            f' stroke="{color}" stroke-width="{random.uniform(1,2):.1f}"/>'
        )

    # 噪点
    for _ in range(30):
        cx, cy = random.randint(0, width), random.randint(0, height)
        r = random.uniform(0.5, 1.5)
        color = f"rgb({random.randint(150,210)},{random.randint(150,210)},{random.randint(150,210)})"
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}"/>')

    # 字符
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
    验证验证码（一次性，验证后立即删除）。
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

"""
CORS origin parsing and loopback normalization helpers.
"""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlsplit

LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")


def _normalize_origin(origin: str) -> str:
    value = origin.strip().rstrip("/")
    if not value or value == "*":
        return value

    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.hostname:
        return value

    host = parsed.hostname.lower()
    host_display = f"[{host}]" if ":" in host and not host.startswith("[") else host
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme.lower()}://{host_display}{port}"


def _expand_loopback_aliases(origin: str) -> list[str]:
    normalized = _normalize_origin(origin)
    if not normalized or normalized == "*":
        return [normalized]

    parsed = urlsplit(normalized)
    if not parsed.scheme or not parsed.hostname:
        return [normalized]

    host = parsed.hostname.lower()
    if host not in LOOPBACK_HOSTS:
        return [normalized]

    port = f":{parsed.port}" if parsed.port else ""
    expanded: list[str] = []
    for loopback_host in LOOPBACK_HOSTS:
        host_display = f"[{loopback_host}]" if ":" in loopback_host else loopback_host
        expanded.append(f"{parsed.scheme.lower()}://{host_display}{port}")
    return expanded


def build_cors_allowed_origins(origins: Iterable[str]) -> list[str]:
    """Build deduplicated CORS origin list with loopback aliases expanded."""
    result: list[str] = []
    seen: set[str] = set()
    for origin in origins:
        for candidate in _expand_loopback_aliases(origin):
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            result.append(candidate)
    return result


def parse_cors_origins_from_env(cors_env: str) -> list[str]:
    """Parse comma-separated CORS_ORIGINS with loopback compatibility expansion."""
    origins = [item for item in (part.strip() for part in cors_env.split(",")) if item]
    return build_cors_allowed_origins(origins)

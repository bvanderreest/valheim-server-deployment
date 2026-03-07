import secrets
import time
from collections import defaultdict

from fastapi import Header, HTTPException, Request

from .config import settings

# In-memory rate limiter — stores timestamps of failed auth attempts per IP.
# NOTE: This resets on process restart and only works correctly with --workers 1.
# If you need multi-worker support, replace this with a Redis-backed store.
_auth_failures: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 900   # 15 minutes
_RATE_LIMIT_MAX = 5        # max failed attempts per window


def _get_client_ip(request: Request) -> str:
    # Trust X-Real-IP set by nginx; fall back to direct connection address
    return request.headers.get("X-Real-IP") or (
        request.client.host if request.client else "unknown"
    )


def _check_rate_limit(ip: str) -> None:
    now = time.time()
    cutoff = now - _RATE_LIMIT_WINDOW
    _auth_failures[ip] = [t for t in _auth_failures[ip] if t > cutoff]
    if len(_auth_failures[ip]) >= _RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail="Too many failed authentication attempts. Try again later.",
        )


async def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str:
    ip = _get_client_ip(request)
    _check_rate_limit(ip)

    if not x_api_key:
        _auth_failures[ip].append(time.time())
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Provide it via the X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Constant-time comparison to prevent timing attacks
    valid = any(
        secrets.compare_digest(x_api_key, k) for k in settings.api_keys_list
    )
    if not valid:
        _auth_failures[ip].append(time.time())
        raise HTTPException(
            status_code=401,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return x_api_key

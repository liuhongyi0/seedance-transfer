"""
In-memory sliding window rate limiter middleware.

Tiers:
  - auth   (login/register):      10 req / 60s per IP
  - gen    (image/video/music):    5 req / 60s per IP
  - admin  (init-db):             2 req / 60s per IP
  - default:                       60 req / 60s per IP

Excluded: /health, /api/sse/*
"""

import time
import asyncio
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


# ── Tier config ───────────────────────────────────────────────────
TIER_LIMITS: dict[str, tuple[int, int]] = {
    "auth":   (10, 60),
    "gen":    (5,  60),
    "admin":  (2,  60),
}

DEFAULT_LIMIT = (60, 60)

TIER_PREFIXES: dict[str, list[str]] = {
    "auth":  ["/api/auth/"],
    "gen":   ["/api/image/", "/api/video-draft/", "/api/final-video/", "/api/music/"],
    "admin": ["/admin/"],
}

EXCLUDED: list[str] = ["/health", "/api/sse/"]


def _get_tier(path: str) -> str | None:
    for tier, prefixes in TIER_PREFIXES.items():
        for pfx in prefixes:
            if path.startswith(pfx):
                return tier
    return None


# ── Sliding window store ──────────────────────────────────────────
# { (ip, tier) -> list[timestamp] }
_windows: dict[tuple[str, str], list[float]] = defaultdict(list)

_cleanup_lock = asyncio.Lock()
_last_cleanup = time.monotonic()


async def _cleanup_old():
    """Remove expired entries periodically (max every 120s)."""
    global _last_cleanup
    now = time.monotonic()
    if now - _last_cleanup < 120:
        return
    async with _cleanup_lock:
        if now - _last_cleanup < 120:
            return
        stale = []
        cutoff = now - max(max_t for _, max_t in TIER_LIMITS.values()) - 10
        for key, stamps in _windows.items():
            stamps[:] = [s for s in stamps if s > cutoff]
            if not stamps:
                stale.append(key)
        for key in stale:
            del _windows[key]
        _last_cleanup = now


# ── Middleware ────────────────────────────────────────────────────

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path

        # Excluded paths
        for ex in EXCLUDED:
            if path.startswith(ex):
                return await call_next(request)

        tier = _get_tier(path)
        max_req, window = TIER_LIMITS.get(tier, DEFAULT_LIMIT)

        ip = request.client.host if request.client else "127.0.0.1"
        key = (ip, tier or "default")

        now = time.monotonic()
        stamps = _windows[key]

        # Drop expired stamps
        cutoff = now - window
        stamps[:] = [s for s in stamps if s > cutoff]

        if len(stamps) >= max_req:
            # Calculate retry-after
            oldest = stamps[0]
            retry_after = int(oldest + window - now) + 1
            if retry_after < 1:
                retry_after = 1
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests. Please try again later.",
                    "retry_after_seconds": retry_after,
                    "tier": tier or "default",
                },
                headers={
                    "Retry-After": str(retry_after),
                    "Access-Control-Allow-Origin": "*",
                },
            )

        stamps.append(now)
        await _cleanup_old()

        return await call_next(request)

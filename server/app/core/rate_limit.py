"""Rate limiting facade – selects Redis (distributed) or in-memory backend.

Existing synchronous `check_rate_limit()` remains unchanged for backward
compatibility. New async callers should prefer `check_rate_limit_async()`.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

Window = deque[float]

_buckets: dict[str, Window] = defaultdict(deque)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RateLimitResult:
    """Outcome of a rate limit check."""

    allowed: bool
    remaining: int
    reset_after: int  # seconds until window resets


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit_headers(result: RateLimitResult) -> dict[str, str]:
    """Generate standard rate-limit response headers."""
    headers: dict[str, str] = {
        "X-RateLimit-Remaining": str(result.remaining),
        "X-RateLimit-Reset-After": str(result.reset_after),
    }
    if not result.allowed:
        headers["Retry-After"] = str(result.reset_after)
    return headers


# ---------------------------------------------------------------------------
# Synchronous in-memory implementation (original – kept for compatibility)
# ---------------------------------------------------------------------------

def check_rate_limit(
    key: str,
    *,
    limit: int,
    window_seconds: int = 60,
    now_fn: Callable[[], float] = time.monotonic,
) -> None:
    """Original synchronous rate limiter. Raises HTTP 429 if limit exceeded."""
    if limit <= 0:
        return
    now = now_fn()
    bucket = _buckets[key]
    cutoff = now - window_seconds
    while bucket and bucket[0] <= cutoff:
        bucket.popleft()
    if len(bucket) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )
    bucket.append(now)


# ---------------------------------------------------------------------------
# In-memory implementation returning RateLimitResult
# ---------------------------------------------------------------------------

def _check_memory(
    key: str,
    *,
    limit: int,
    window_seconds: int = 60,
) -> RateLimitResult:
    """In-memory sliding window that returns a result instead of raising."""
    if limit <= 0:
        return RateLimitResult(allowed=True, remaining=limit, reset_after=window_seconds)

    now = time.monotonic()
    bucket = _buckets[key]
    cutoff = now - window_seconds
    while bucket and bucket[0] <= cutoff:
        bucket.popleft()

    current_count = len(bucket)
    if current_count >= limit:
        return RateLimitResult(allowed=False, remaining=0, reset_after=window_seconds)

    bucket.append(now)
    return RateLimitResult(allowed=True, remaining=limit - current_count - 1, reset_after=window_seconds)


# ---------------------------------------------------------------------------
# Async facade – uses Redis when available, falls back to memory
# ---------------------------------------------------------------------------

async def check_rate_limit_async(
    key: str,
    *,
    limit: int,
    window_seconds: int = 60,
) -> RateLimitResult:
    """Async rate limit check with automatic backend selection.

    - When redis_url is configured and Redis is reachable: uses distributed limiter.
    - Otherwise: falls back to in-memory limiter.

    Returns RateLimitResult (never raises HTTP exceptions directly).
    """
    from .redis_rate_limit import _RedisUnavailable, check_rate_limit_redis

    try:
        meta = await check_rate_limit_redis(key, limit=limit, window_seconds=window_seconds)
        return RateLimitResult(
            allowed=meta["allowed"],
            remaining=meta["remaining"],
            reset_after=meta["reset_after"],
        )
    except _RedisUnavailable:
        # Graceful degradation to memory limiter
        return _check_memory(key, limit=limit, window_seconds=window_seconds)


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def reset_rate_limits() -> None:
    _buckets.clear()

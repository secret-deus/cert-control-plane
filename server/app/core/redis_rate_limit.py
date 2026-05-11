"""Redis-backed distributed sliding window rate limiter.

Uses Redis Sorted Sets (ZADD + ZREMRANGEBYSCORE + ZCARD) for an accurate
sliding window implementation that works across multiple application instances.

Falls back to the in-memory limiter when Redis is unavailable.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

_redis_pool: "Redis | None" = None
_initialized: bool = False


async def get_redis() -> "Redis | None":
    """Return a shared Redis connection (lazy singleton). Returns None if not configured."""
    global _redis_pool, _initialized

    if _initialized:
        return _redis_pool

    _initialized = True

    from ..config import get_settings

    settings = get_settings()
    if not settings.redis_url:
        logger.debug("redis_url not configured; distributed rate limiting disabled")
        return None

    try:
        import redis.asyncio as aioredis

        _redis_pool = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        # Verify connectivity
        await _redis_pool.ping()
        logger.info("Redis connected for distributed rate limiting")
    except Exception as exc:
        logger.warning("Failed to connect to Redis, falling back to memory limiter: %s", exc)
        _redis_pool = None

    return _redis_pool


async def check_rate_limit_redis(
    key: str,
    *,
    limit: int,
    window_seconds: int = 60,
) -> dict:
    """Check rate limit using Redis sorted set sliding window.

    Returns a metadata dict with:
        - allowed: bool
        - remaining: int (requests remaining in current window)
        - reset_after: int (seconds until window resets)

    Raises nothing on Redis failure – returns a fallback-permissive result
    and logs a warning. The caller (facade) handles actual fallback logic.
    """
    redis = await get_redis()
    if redis is None:
        raise _RedisUnavailable()

    now = time.time()
    window_start = now - window_seconds

    pipe_key = f"ratelimit:{key}"

    try:
        async with redis.pipeline(transaction=True) as pipe:
            # Remove expired entries
            pipe.zremrangebyscore(pipe_key, "-inf", window_start)
            # Add current request (score = timestamp, member = unique)
            pipe.zadd(pipe_key, {f"{now}": now})
            # Count entries in window
            pipe.zcard(pipe_key)
            # Set TTL so keys auto-expire
            pipe.expire(pipe_key, window_seconds + 1)
            results = await pipe.execute()

        current_count = results[2]  # ZCARD result
        allowed = current_count <= limit
        remaining = max(0, limit - current_count)
        reset_after = window_seconds

        if not allowed:
            # Remove the entry we just added since request is denied
            await redis.zrem(pipe_key, f"{now}")
            remaining = 0

        return {
            "allowed": allowed,
            "remaining": remaining,
            "reset_after": reset_after,
        }
    except Exception as exc:
        logger.warning("Redis rate limit check failed, falling back: %s", exc)
        raise _RedisUnavailable() from exc


class _RedisUnavailable(Exception):
    """Internal signal that Redis is not available and fallback should be used."""

    pass


async def close_redis() -> None:
    """Close Redis connection pool (for graceful shutdown)."""
    global _redis_pool, _initialized
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None
    _initialized = False

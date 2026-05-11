"""Small in-process rate limiter for single-instance safety rails.

This is intentionally simple. Production deployments that run multiple app
instances should still enforce distributed limits at the gateway or ingress.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request, status

Window = deque[float]

_buckets: dict[str, Window] = defaultdict(deque)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(
    key: str,
    *,
    limit: int,
    window_seconds: int = 60,
    now_fn: Callable[[], float] = time.monotonic,
) -> None:
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


def reset_rate_limits() -> None:
    _buckets.clear()

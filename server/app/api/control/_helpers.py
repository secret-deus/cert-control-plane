"""Shared helpers for control API sub-modules."""

from fastapi import Request


def _actor(request: Request) -> str:
    api_key = request.headers.get("X-Admin-API-Key", "")
    if api_key and len(api_key) >= 8:
        return f"admin:{api_key[:8]}"
    return "admin"


def _ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None

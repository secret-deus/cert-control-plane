"""Admin API key validation and agent token generation."""

import secrets

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from app.config import get_settings
from app.core.rate_limit import check_rate_limit, client_ip

_api_key_header = APIKeyHeader(name="X-Admin-API-Key", auto_error=False)


def generate_agent_token() -> str:
    """Generate a cryptographically random agent token (48-byte hex)."""
    return secrets.token_hex(48)


def verify_admin_key(
    request: Request,
    api_key: str | None = Security(_api_key_header),
) -> str:
    """FastAPI dependency – validates X-Admin-API-Key header."""
    settings = get_settings()
    if settings.dev_mode:
        return api_key or "dev-mode"
    if not api_key or not secrets.compare_digest(api_key, settings.admin_api_key):
        check_rate_limit(
            f"admin-auth-failure:{client_ip(request)}",
            limit=settings.rate_limit_admin_auth_failures_per_minute,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Admin API key",
        )
    return api_key

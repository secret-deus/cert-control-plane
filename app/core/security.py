"""Bootstrap token generation and Admin API key validation."""

import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.config import get_settings

_api_key_header = APIKeyHeader(name="X-Admin-API-Key", auto_error=False)


def generate_bootstrap_token() -> str:
    """Cryptographically random 48-byte hex token."""
    return secrets.token_hex(48)


def verify_admin_key(api_key: str | None = Security(_api_key_header)) -> str:
    """FastAPI dependency – validates X-Admin-API-Key header."""
    settings = get_settings()
    if not api_key or not secrets.compare_digest(api_key, settings.admin_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Admin API key",
        )
    return api_key


def extract_client_cn(client_cn_header: str | None) -> str | None:
    """Extract agent CN from X-Client-CN header injected by nginx after mTLS."""
    return client_cn_header or None

"""Admin API key validation, agent token generation and permission utilities."""

import hashlib
import secrets

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from app.config import get_settings
from app.core.rate_limit import check_rate_limit, client_ip

_api_key_header = APIKeyHeader(name="X-Admin-API-Key", auto_error=False)


def hash_token(token: str) -> str:
    """Compute SHA-256 hash of an agent token."""
    return hashlib.sha256(token.encode()).hexdigest()


def generate_agent_token() -> tuple[str, str]:
    """Generate a cryptographically random agent token (48-byte hex) and its SHA-256 hash.

    Returns:
        (plaintext_token, token_hash) tuple
    """
    token = secrets.token_hex(48)
    return token, hash_token(token)


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


class ForbiddenError(HTTPException):
    """权限不足异常 - 用于未来 RBAC 权限检查"""

    def __init__(self, detail: str = "Permission denied"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )


def require_permission(permission: str):
    """预留的权限检查依赖 - 当前仅验证 admin key，未来扩展为 RBAC。

    Usage: @router.get("/...", dependencies=[Depends(require_permission("agents:write"))])
    """

    def _check(api_key: str = Depends(verify_admin_key)):
        # 当前阶段：通过 admin key 验证即可
        # 未来 RBAC：根据 api_key 查询角色，检查 permission
        return api_key

    return Depends(_check)

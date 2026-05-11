from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = ""

    # External certificate key encryption (Fernet key) – required
    ca_key_encryption_key: str = ""

    # Admin API key – no default; must be configured
    admin_api_key: str = ""

    # CORS allowed origins (default: [] — must be explicitly configured)
    cors_origins: list[str] = []

    # Development mode (bypass agent token auth for local testing)
    dev_mode: bool = False

    # Basic in-process rate limits. Use an upstream gateway for distributed limits.
    rate_limit_agent_register_per_minute: int = 10
    rate_limit_register_status_per_minute: int = 60
    rate_limit_admin_auth_failures_per_minute: int = 20

    # Orchestrator
    rollout_interval_seconds: int = 30
    default_batch_size: int = 10
    rollout_item_timeout_minutes: int = 10

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # "json" or "text"

    @model_validator(mode="after")
    def _check_required(self):
        if not self.database_url:
            raise ValueError("DATABASE_URL must be set")
        if not self.admin_api_key:
            raise ValueError(
                "ADMIN_API_KEY must be set – "
                "generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        if not self.ca_key_encryption_key:
            raise ValueError(
                "CA_KEY_ENCRYPTION_KEY must be set – "
                "generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        if self.dev_mode and not str(self.database_url).startswith("sqlite"):
            raise ValueError("DEV_MODE=true is only allowed with SQLite development databases")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

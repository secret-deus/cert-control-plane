from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/certcp"

    # CA key encryption (Fernet key) – required in production
    ca_key_encryption_key: str = ""

    # Admin API key – no default; must be configured
    admin_api_key: str = ""

    # CORS allowed origins (default: [] — must be explicitly configured)
    cors_origins: list[str] = []

    # CA paths
    ca_cert_path: str = "/certs/ca.crt"
    ca_key_path: str = "/certs/ca.key"

    # Cert defaults
    cert_validity_days: int = 365

    # Bootstrap token expiry (hours)
    bootstrap_token_expire_hours: int = 24

    # Startup behavior
    strict_ca_startup: bool = True  # Fail-fast if CA files missing at startup

    # Orchestrator
    rollout_interval_seconds: int = 30
    default_batch_size: int = 10
    rollout_item_timeout_minutes: int = 10  # IN_PROGRESS 超时时间

    @model_validator(mode="after")
    def _check_required(self):
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
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

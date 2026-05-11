"""Production configuration guardrail tests."""

import pytest
from pydantic import ValidationError

from app.config import Settings


def _base_settings(**overrides):
    values = {
        "database_url": "sqlite+aiosqlite:///:memory:",
        "admin_api_key": "test-admin-key",
        "ca_key_encryption_key": "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXQ9PQ==",
    }
    values.update(overrides)
    return Settings(**values)


def test_database_url_is_required():
    with pytest.raises(ValidationError, match="DATABASE_URL must be set"):
        _base_settings(database_url="")


def test_dev_mode_allowed_for_sqlite():
    settings = _base_settings(dev_mode=True)

    assert settings.dev_mode is True


def test_dev_mode_rejected_for_postgresql():
    with pytest.raises(ValidationError, match="DEV_MODE=true is only allowed"):
        _base_settings(
            database_url="postgresql+asyncpg://certcp:secret@db:5432/certcp",
            dev_mode=True,
        )

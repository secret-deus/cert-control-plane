"""Shared fixtures for cert-control-plane tests.

Tests are designed to run WITHOUT a real database.
DB interactions are mocked at the SQLAlchemy session level.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

# Set required env vars BEFORE importing anything from app.
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-for-pytest")
os.environ.setdefault(
    "CA_KEY_ENCRYPTION_KEY",
    # Valid Fernet key for testing only (base64-encoded 32 bytes).
    "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXQ9PQ==",
)
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
# Disable dev mode so auth is enforced during tests
os.environ["DEV_MODE"] = "false"

from app.models import Agent, AgentStatus, ExternalCertificate  # noqa: E402


@pytest.fixture()
def mock_agent() -> Agent:
    """An ACTIVE agent with a valid agent_token (post-approval state)."""
    agent = MagicMock(spec=Agent)
    agent.id = uuid.uuid4()
    agent.name = "test-agent-01"
    agent.status = AgentStatus.ACTIVE
    agent.fingerprint = "a" * 64   # SHA-256 hex
    agent.agent_token = "test-agent-token-secret"
    agent.last_seen = None
    return agent


@pytest.fixture()
def mock_ext_cert() -> ExternalCertificate:
    """An active ExternalCertificate for use in fetch-certs tests."""
    cert = MagicMock(spec=ExternalCertificate)
    cert.id = uuid.uuid4()
    cert.name = "prod-api-cert"
    cert.subject_cn = "api.example.com"
    cert.serial_hex = "aabbccddeeff0011"
    cert.is_active = True
    cert.cert_pem = "-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----"
    cert.chain_pem = "-----BEGIN CERTIFICATE-----\nMOCK_CHAIN\n-----END CERTIFICATE-----"
    cert.key_pem_encrypted = None  # Tests that need decryption will patch decrypt_key
    cert.not_before = datetime.now(tz=timezone.utc) - timedelta(days=1)
    cert.not_after = datetime.now(tz=timezone.utc) + timedelta(days=364)
    return cert


@pytest.fixture()
def mock_db(mock_agent, mock_ext_cert):
    """AsyncSession mock returning mock_agent and mock_ext_cert for standard queries."""
    session = AsyncMock()

    def _make_result(value):
        result = MagicMock()
        result.scalar_one_or_none.return_value = value
        return result

    session.execute.side_effect = [
        _make_result(mock_agent),
        _make_result(mock_ext_cert),
    ]
    return session

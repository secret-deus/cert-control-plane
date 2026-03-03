"""Shared fixtures for cert-control-plane tests.

These tests are designed to run WITHOUT a real PostgreSQL database.
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
    # Fernet key for testing only.
    "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXQ9PQ==",
)
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("STRICT_CA_STARTUP", "false")

from app.models import Agent, AgentStatus, Certificate  # noqa: E402


@pytest.fixture()
def mock_agent() -> Agent:
    """An ACTIVE agent with a valid certificate."""
    agent = MagicMock(spec=Agent)
    agent.id = uuid.uuid4()
    agent.name = "test-agent-01"
    agent.status = AgentStatus.ACTIVE
    agent.last_seen = None
    return agent


@pytest.fixture()
def mock_cert(mock_agent: Agent) -> Certificate:
    """A non-revoked current certificate for mock_agent."""
    cert = MagicMock(spec=Certificate)
    cert.id = uuid.uuid4()
    cert.agent_id = mock_agent.id
    cert.serial_hex = "abcdef1234567890"
    cert.subject_cn = mock_agent.name
    cert.is_current = True
    cert.revoked_at = None
    cert.not_before = datetime.now(tz=timezone.utc) - timedelta(days=1)
    cert.not_after = datetime.now(tz=timezone.utc) + timedelta(days=364)
    cert.cert_pem = "-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----"
    cert.chain_pem = "-----BEGIN CERTIFICATE-----\nMOCK_CA\n-----END CERTIFICATE-----"
    cert.key_pem_encrypted = None
    return cert


@pytest.fixture()
def mock_db(mock_agent, mock_cert):
    """AsyncSession mock that returns mock_agent and mock_cert for standard queries."""
    session = AsyncMock()

    # Helper to create chained execute -> scalar_one_or_none results
    def _make_result(value):
        result = MagicMock()
        result.scalar_one_or_none.return_value = value
        return result

    # Default: first execute returns agent, second returns cert
    session.execute.side_effect = [
        _make_result(mock_agent),
        _make_result(mock_cert),
    ]
    return session

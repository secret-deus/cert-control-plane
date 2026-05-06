"""Tests for app/registry/store.py helpers.

These tests verify the certificate registry functions:
- get_current_cert: Retrieve the active non-revoked certificate for an agent
- revoke_cert: Mark a certificate as revoked
- record_deployed_cert: Persist certificate deployment and mark old certs as revoked
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.database import Base
from app.models import (
    Agent,
    AgentStatus,
    Certificate,
    ExternalCertificate,
)
from app.registry.store import get_current_cert, revoke_cert, record_deployed_cert


@pytest.fixture
async def db_session(tmp_path: Path):
    """Real SQLite database session for registry/store tests."""
    os.environ["CA_KEY_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    get_settings.cache_clear()

    db_path = tmp_path / "registry-test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def setup_agent_and_cert(db_session):
    """Create test agent and external certificate."""
    agent_id = uuid.uuid4()
    agent = Agent(
        id=agent_id,
        name="test-registry-agent",
        status=AgentStatus.ACTIVE,
        fingerprint="a" * 64,
        agent_token="test-token",
    )
    db_session.add(agent)

    now = datetime.now(tz=timezone.utc)
    external_cert = ExternalCertificate(
        id=uuid.uuid4(),
        name="test-cert",
        subject_cn="test.example.com",
        serial_hex="abc123",
        cert_pem="-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
        key_pem_encrypted="encrypted",
        not_before=now - timedelta(days=1),
        not_after=now + timedelta(days=30),
    )
    db_session.add(external_cert)
    await db_session.flush()

    yield {
        "agent_id": agent_id,
        "agent": agent,
        "external_cert": external_cert,
    }


@pytest.mark.asyncio
class TestGetCurrentCert:
    """Tests for get_current_cert function."""

    async def test_returns_none_when_no_certificates(self, db_session, setup_agent_and_cert):
        """Should return None if agent has no certificates."""
        result = await get_current_cert(
            db_session,
            setup_agent_and_cert["agent_id"],
        )
        assert result is None

    async def test_returns_none_when_all_revoked(self, db_session, setup_agent_and_cert):
        """Should return None if all certificates are revoked."""
        agent_id = setup_agent_and_cert["agent_id"]

        # Create a revoked certificate
        cert = Certificate(
            agent_id=agent_id,
            local_path="/etc/nginx/ssl/test.crt",
            is_current=False,
            revoked_at=datetime.now(tz=timezone.utc),
            serial_hex="revoked123",
            subject_cn="revoked.example.com",
            not_before=datetime.now(tz=timezone.utc) - timedelta(days=10),
            not_after=datetime.now(tz=timezone.utc) + timedelta(days=30),
            cert_pem="-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
        )
        db_session.add(cert)
        await db_session.flush()

        result = await get_current_cert(db_session, agent_id)
        assert result is None

    async def test_returns_current_non_revoked_cert(self, db_session, setup_agent_and_cert):
        """Should return the current non-revoked certificate."""
        agent_id = setup_agent_and_cert["agent_id"]

        cert = Certificate(
            agent_id=agent_id,
            local_path="/etc/nginx/ssl/test.crt",
            is_current=True,
            revoked_at=None,
            serial_hex="current123",
            subject_cn="current.example.com",
            not_before=datetime.now(tz=timezone.utc) - timedelta(days=1),
            not_after=datetime.now(tz=timezone.utc) + timedelta(days=30),
            cert_pem="-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
        )
        db_session.add(cert)
        await db_session.flush()

        result = await get_current_cert(db_session, agent_id)
        assert result is not None
        assert result.serial_hex == "current123"

    async def test_filters_by_local_path(self, db_session, setup_agent_and_cert):
        """Should filter by local_path when provided."""
        agent_id = setup_agent_and_cert["agent_id"]

        cert1 = Certificate(
            agent_id=agent_id,
            local_path="/etc/nginx/ssl/a.crt",
            is_current=True,
            serial_hex="cert-a",
            subject_cn="a.example.com",
            not_before=datetime.now(tz=timezone.utc) - timedelta(days=1),
            not_after=datetime.now(tz=timezone.utc) + timedelta(days=30),
            cert_pem="-----BEGIN CERTIFICATE-----\ntest-a\n-----END CERTIFICATE-----",
        )
        cert2 = Certificate(
            agent_id=agent_id,
            local_path="/etc/nginx/ssl/b.crt",
            is_current=True,
            serial_hex="cert-b",
            subject_cn="b.example.com",
            not_before=datetime.now(tz=timezone.utc) - timedelta(days=1),
            not_after=datetime.now(tz=timezone.utc) + timedelta(days=30),
            cert_pem="-----BEGIN CERTIFICATE-----\ntest-b\n-----END CERTIFICATE-----",
        )
        db_session.add_all([cert1, cert2])
        await db_session.flush()

        result = await get_current_cert(
            db_session,
            agent_id,
            local_path="/etc/nginx/ssl/a.crt",
        )
        assert result is not None
        assert result.serial_hex == "cert-a"


@pytest.mark.asyncio
class TestRevokeCert:
    """Tests for revoke_cert function."""

    async def test_marks_cert_as_revoked(self, db_session, setup_agent_and_cert):
        """Should mark certificate as revoked with timestamp."""
        agent_id = setup_agent_and_cert["agent_id"]

        cert = Certificate(
            agent_id=agent_id,
            local_path="/etc/nginx/ssl/test.crt",
            is_current=True,
            serial_hex="to-revoke",
            subject_cn="revoke.example.com",
            not_before=datetime.now(tz=timezone.utc) - timedelta(days=1),
            not_after=datetime.now(tz=timezone.utc) + timedelta(days=30),
            cert_pem="-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
        )
        db_session.add(cert)
        await db_session.flush()

        before_revoke = datetime.now(tz=timezone.utc)
        result = await revoke_cert(db_session, cert)

        assert result.is_current is False
        assert result.revoked_at is not None
        assert result.revoked_at >= before_revoke

    async def test_revoke_cert_is_idempotent(self, db_session, setup_agent_and_cert):
        """Calling revoke_cert on already revoked cert should update timestamp."""
        agent_id = setup_agent_and_cert["agent_id"]

        cert = Certificate(
            agent_id=agent_id,
            local_path="/etc/nginx/ssl/test.crt",
            is_current=False,
            revoked_at=datetime.now(tz=timezone.utc) - timedelta(days=1),
            serial_hex="already-revoked",
            subject_cn="revoked.example.com",
            not_before=datetime.now(tz=timezone.utc) - timedelta(days=10),
            not_after=datetime.now(tz=timezone.utc) + timedelta(days=30),
            cert_pem="-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
        )
        db_session.add(cert)
        await db_session.flush()

        old_revoked_at = cert.revoked_at
        result = await revoke_cert(db_session, cert)

        assert result.is_current is False
        assert result.revoked_at > old_revoked_at


@pytest.mark.asyncio
class TestRecordDeployedCert:
    """Tests for record_deployed_cert function."""

    async def test_creates_new_certificate_record(self, db_session, setup_agent_and_cert):
        """Should create new Certificate entry when none exists."""
        agent_id = setup_agent_and_cert["agent_id"]
        external_cert = setup_agent_and_cert["external_cert"]

        result = await record_deployed_cert(
            db_session,
            agent_id=agent_id,
            local_path="/etc/nginx/ssl/new.crt",
            external_cert=external_cert,
        )

        assert result is not None
        assert result.is_current is True
        assert result.revoked_at is None
        assert result.external_cert_id == external_cert.id
        assert result.serial_hex == external_cert.serial_hex

    async def test_marks_old_certs_as_revoked(self, db_session, setup_agent_and_cert):
        """Should mark previous current cert as revoked when deploying new one."""
        agent_id = setup_agent_and_cert["agent_id"]
        external_cert = setup_agent_and_cert["external_cert"]
        local_path = "/etc/nginx/ssl/rotate.crt"

        # Create initial certificate
        old_cert = Certificate(
            agent_id=agent_id,
            local_path=local_path,
            is_current=True,
            serial_hex="old-serial",
            subject_cn="old.example.com",
            not_before=datetime.now(tz=timezone.utc) - timedelta(days=10),
            not_after=datetime.now(tz=timezone.utc) - timedelta(days=5),  # Expired
            cert_pem="-----BEGIN CERTIFICATE-----\nold\n-----END CERTIFICATE-----",
        )
        db_session.add(old_cert)
        await db_session.flush()

        # Deploy new certificate
        result = await record_deployed_cert(
            db_session,
            agent_id=agent_id,
            local_path=local_path,
            external_cert=external_cert,
        )

        assert result.is_current is True
        assert result.serial_hex == external_cert.serial_hex

        # Check old cert is revoked
        await db_session.refresh(old_cert)
        assert old_cert.is_current is False
        assert old_cert.revoked_at is not None

    async def test_returns_existing_if_same_cert_deployed(self, db_session, setup_agent_and_cert):
        """Should return existing cert if same external cert is already deployed."""
        agent_id = setup_agent_and_cert["agent_id"]
        external_cert = setup_agent_and_cert["external_cert"]
        local_path = "/etc/nginx/ssl/same.crt"

        # First deployment
        first = await record_deployed_cert(
            db_session,
            agent_id=agent_id,
            local_path=local_path,
            external_cert=external_cert,
        )

        # Second deployment with same cert
        second = await record_deployed_cert(
            db_session,
            agent_id=agent_id,
            local_path=local_path,
            external_cert=external_cert,
        )

        assert second.id == first.id
        assert second.is_current is True

        # Verify only one Certificate record exists
        count = await db_session.execute(
            select(Certificate).where(
                Certificate.agent_id == agent_id,
                Certificate.local_path == local_path,
            )
        )
        certs = count.scalars().all()
        assert len(certs) == 1

    async def test_different_paths_have_separate_certs(self, db_session, setup_agent_and_cert):
        """Each local_path should have its own certificate record."""
        agent_id = setup_agent_and_cert["agent_id"]
        external_cert = setup_agent_and_cert["external_cert"]

        cert_a = await record_deployed_cert(
            db_session,
            agent_id=agent_id,
            local_path="/etc/nginx/ssl/a.crt",
            external_cert=external_cert,
        )

        cert_b = await record_deployed_cert(
            db_session,
            agent_id=agent_id,
            local_path="/etc/nginx/ssl/b.crt",
            external_cert=external_cert,
        )

        assert cert_a.id != cert_b.id
        assert cert_a.local_path != cert_b.local_path

        # Both should be current
        assert cert_a.is_current is True
        assert cert_b.is_current is True

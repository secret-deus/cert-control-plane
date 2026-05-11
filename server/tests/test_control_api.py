"""Control API endpoint tests.

Tests for admin-facing endpoints with X-Admin-API-Key authentication:
- Agents CRUD
- External certificates
- Rollouts
- Audit logs
"""

import io
import zipfile
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from httpx import ASGITransport, AsyncClient

from app.core.security import hash_token
from app.models import (
    Agent,
    AgentStatus,
    AuditLog,
    Certificate,
    ExternalCertificate,
    Rollout,
    RolloutStatus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    """Create a fresh FastAPI app for each test."""
    from app.main import create_app
    return create_app()


@pytest.fixture()
async def client(app):
    """Async client with admin API key header."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        c.headers["X-Admin-API-Key"] = "test-admin-key-for-pytest"
        yield c


def _make_result(value):
    """Create a mock SQLAlchemy result."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    r.scalar_one.return_value = value
    r.scalars.return_value.all.return_value = value if isinstance(value, list) else []
    return r


def _make_agent(
    name: str = "test-agent",
    *,
    status: AgentStatus = AgentStatus.ACTIVE,
    agent_token: str | None = "test-token",
) -> Agent:
    """Create a mock Agent."""
    agent = MagicMock(spec=Agent)
    agent.id = uuid.uuid4()
    agent.name = name
    agent.description = None
    agent.status = status
    agent.fingerprint = "a" * 64
    agent.agent_token_hash = hash_token(agent_token) if agent_token else None
    agent.last_seen = None
    agent.created_at = datetime.now(tz=timezone.utc)
    return agent


def _make_ext_cert(
    name: str = "test-cert",
    *,
    is_active: bool = True,
    not_after: datetime | None = None,
) -> ExternalCertificate:
    """Create a mock ExternalCertificate."""
    cert = MagicMock(spec=ExternalCertificate)
    cert.id = uuid.uuid4()
    cert.name = name
    cert.description = None
    cert.subject_cn = "example.com"
    cert.serial_hex = "aabbccddeeff"
    cert.is_active = is_active
    cert.cert_pem = "-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----"
    cert.chain_pem = None
    cert.key_pem_encrypted = "encrypted"
    cert.not_before = datetime.now(tz=timezone.utc) - timedelta(days=1)
    cert.not_after = not_after or (datetime.now(tz=timezone.utc) + timedelta(days=365))
    cert.provider = "manual"
    cert.external_id = None
    cert.created_at = datetime.now(tz=timezone.utc)
    return cert


def _make_rollout(
    name: str = "test-rollout",
    *,
    status: RolloutStatus = RolloutStatus.PENDING,
    batch_size: int = 5,
) -> Rollout:
    """Create a mock Rollout."""
    r = MagicMock(spec=Rollout)
    r.id = uuid.uuid4()
    r.name = name
    r.description = None
    r.status = status
    r.batch_size = batch_size
    r.current_batch = 0
    r.total_batches = 1
    r.target_filter = None
    r.created_by = "admin"
    r.created_at = datetime.now(tz=timezone.utc)
    r.updated_at = datetime.now(tz=timezone.utc)
    r.items = []
    return r


def _build_cert_zip_bundle(common_name: str = "example.com") -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(tz=timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(tz=timezone.utc) + timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("server.crt", cert_pem)
        zf.writestr("server.key", key_pem)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Agents API Tests
# ---------------------------------------------------------------------------


class TestAgentsAPI:
    """Tests for /api/control/agents endpoints."""

    @pytest.mark.asyncio
    async def test_list_agents_success(self, client):
        """GET /agents returns paginated list."""
        agents = [_make_agent(name=f"agent-{i}") for i in range(3)]
        mock_db = AsyncMock()
        # count query
        count_result = MagicMock()
        count_result.scalar_one.return_value = 3
        # list query
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = agents
        # cert count query (for each agent)
        cert_count_result = MagicMock()
        cert_count_result.scalar_one.return_value = 0
        # expiring count query (for each agent)
        expiring_count_result = MagicMock()
        expiring_count_result.scalar_one.return_value = 0

        mock_db.execute.side_effect = [count_result, list_result] + \
            [cert_count_result, expiring_count_result] * 3

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.get("/api/control/agents")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3

    @pytest.mark.asyncio
    async def test_list_agents_filter_by_status(self, client):
        """GET /agents?status=active filters by status."""
        active_agents = [_make_agent(name="active-agent", status=AgentStatus.ACTIVE)]
        mock_db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = active_agents
        # cert count and expiring count queries
        cert_count_result = MagicMock()
        cert_count_result.scalar_one.return_value = 0
        expiring_count_result = MagicMock()
        expiring_count_result.scalar_one.return_value = 0
        mock_db.execute.side_effect = [count_result, list_result, cert_count_result, expiring_count_result]

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        # Use lowercase enum value as per FastAPI query param serialization
        resp = await client.get("/api/control/agents?status=active")

        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1

    @pytest.mark.asyncio
    async def test_get_agent_success(self, client):
        """GET /agents/{id} returns single agent."""
        agent = _make_agent()
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=agent)

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.get(f"/api/control/agents/{agent.id}")

        assert resp.status_code == 200
        assert resp.json()["name"] == agent.name

    @pytest.mark.asyncio
    async def test_get_agent_not_found(self, client):
        """GET /agents/{id} with invalid ID returns 404."""
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.get(f"/api/control/agents/{uuid.uuid4()}")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_agent_success(self, client):
        """POST /agents creates new agent."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = _make_result(None)  # No existing agent
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.add = MagicMock()

        # Simulate the agent getting an ID after flush
        created_agent_id = uuid.uuid4()
        created_agent_created_at = datetime.now(tz=timezone.utc)

        def mock_refresh(agent):
            agent.id = created_agent_id
            agent.created_at = created_agent_created_at
        mock_db.refresh.side_effect = mock_refresh

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        with patch("app.api.control.agents.write_audit", new_callable=AsyncMock):
            resp = await client.post("/api/control/agents", json={
                "name": "new-agent",
                "description": "Test agent",
            })

        assert resp.status_code == 201
        assert resp.json()["name"] == "new-agent"

    @pytest.mark.asyncio
    async def test_create_agent_duplicate_name(self, client):
        """POST /agents with existing name returns 409."""
        existing = _make_agent(name="existing-agent")
        mock_db = AsyncMock()
        mock_db.execute.return_value = _make_result(existing)

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.post("/api/control/agents", json={
            "name": "existing-agent",
        })

        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_delete_agent_success(self, client):
        """DELETE /agents/{id} removes agent."""
        agent = _make_agent()
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=agent)
        mock_db.delete = AsyncMock()
        mock_db.commit = AsyncMock()

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        with patch("app.api.control.agents.write_audit", new_callable=AsyncMock):
            resp = await client.delete(f"/api/control/agents/{agent.id}")

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_agent_not_found(self, client):
        """DELETE /agents/{id} with invalid ID returns 404."""
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.delete(f"/api/control/agents/{uuid.uuid4()}")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_approve_agent_success(self, client):
        """POST /agents/{id}/approve generates token and activates."""
        agent = _make_agent(status=AgentStatus.PENDING_APPROVAL, agent_token=None)
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=agent)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.add = MagicMock()

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        with patch("app.api.control.agents.write_audit", new_callable=AsyncMock):
            resp = await client.post(f"/api/control/agents/{agent.id}/approve")

        assert resp.status_code == 200
        data = resp.json()
        # Status enum value is lowercase
        assert data["status"] == "active"
        # agent_token is not exposed in AgentRead schema for security

    @pytest.mark.asyncio
    async def test_approve_already_active_agent(self, client):
        """POST /agents/{id}/approve on ACTIVE agent returns 409."""
        agent = _make_agent(status=AgentStatus.ACTIVE)
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=agent)

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.post(f"/api/control/agents/{agent.id}/approve")

        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_approve_agent_without_fingerprint_returns_409(self, client):
        """Pre-created slot cannot be approved before self-registration."""
        agent = _make_agent(status=AgentStatus.PENDING_APPROVAL, agent_token=None)
        agent.fingerprint = None
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=agent)

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.post(f"/api/control/agents/{agent.id}/approve")

        assert resp.status_code == 409
        assert "self-registered" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_reject_agent_success(self, client):
        """POST /agents/{id}/reject sets status to REVOKED."""
        agent = _make_agent(status=AgentStatus.PENDING_APPROVAL)
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=agent)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.add = MagicMock()

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        with patch("app.api.control.agents.write_audit", new_callable=AsyncMock):
            resp = await client.post(f"/api/control/agents/{agent.id}/reject")

        assert resp.status_code == 200
        # Status enum value is lowercase
        assert resp.json()["status"] == "revoked"


class TestAgentAuth:
    """Tests for admin API key authentication."""

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_401(self, app):
        """Request without X-Admin-API-Key returns 401."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # No X-Admin-API-Key header
            resp = await client.get("/api/control/agents")
            assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_api_key_returns_401(self, app):
        """Request with wrong API key returns 401."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.headers["X-Admin-API-Key"] = "wrong-key"
            resp = await client.get("/api/control/agents")
            assert resp.status_code == 401


# ---------------------------------------------------------------------------
# External Certificates API Tests
# ---------------------------------------------------------------------------


class TestExternalCertsAPI:
    """Tests for /api/control/external-certs endpoints."""

    @pytest.mark.asyncio
    async def test_list_external_certs(self, client):
        """GET /external-certs returns paginated list."""
        certs = [_make_ext_cert(name=f"cert-{i}") for i in range(2)]
        mock_db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 2
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = certs
        mock_db.execute.side_effect = [count_result, list_result]

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.get("/api/control/external-certs")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    @pytest.mark.asyncio
    async def test_get_external_cert_success(self, client):
        """GET /external-certs/{id} returns cert detail."""
        cert = _make_ext_cert()
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=cert)

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.get(f"/api/control/external-certs/{cert.id}")

        assert resp.status_code == 200
        assert resp.json()["name"] == cert.name

    @pytest.mark.asyncio
    async def test_get_external_cert_not_found(self, client):
        """GET /external-certs/{id} with invalid ID returns 404."""
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.get(f"/api/control/external-certs/{uuid.uuid4()}")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_external_cert_invalid_pem(self, client):
        """POST /external-certs with invalid PEM returns 400."""
        mock_db = AsyncMock()

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.post("/api/control/external-certs", json={
            "name": "test",
            "cert_pem": "not a valid pem",
            "key_pem": "key",
        })

        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Rollouts API Tests
# ---------------------------------------------------------------------------


class TestRolloutsAPI:
    """Tests for /api/control/rollouts endpoints."""

    @pytest.mark.asyncio
    async def test_list_rollouts(self, client):
        """GET /rollouts returns paginated list."""
        rollouts = [_make_rollout(name=f"rollout-{i}") for i in range(2)]
        mock_db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 2
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = rollouts
        mock_db.execute.side_effect = [count_result, list_result]

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.get("/api/control/rollouts")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    @pytest.mark.asyncio
    async def test_get_rollout_success(self, client):
        """GET /rollouts/{id} returns rollout detail."""
        rollout = _make_rollout()
        mock_db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = rollout
        mock_db.execute.return_value = result

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.get(f"/api/control/rollouts/{rollout.id}")

        assert resp.status_code == 200
        assert resp.json()["name"] == rollout.name

    @pytest.mark.asyncio
    async def test_get_rollout_not_found(self, client):
        """GET /rollouts/{id} with invalid ID returns 404."""
        mock_db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = result

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.get(f"/api/control/rollouts/{uuid.uuid4()}")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_start_rollout_success(self, client):
        """POST /rollouts/{id}/start transitions PENDING to RUNNING."""
        rollout = _make_rollout(status=RolloutStatus.PENDING)
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=rollout)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.add = MagicMock()

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        with patch("app.api.control.rollouts.write_audit", new_callable=AsyncMock):
            resp = await client.post(f"/api/control/rollouts/{rollout.id}/start")

        assert resp.status_code == 200
        # Status enum value is lowercase
        assert resp.json()["status"] == "running"

    @pytest.mark.asyncio
    async def test_start_rollout_invalid_status(self, client):
        """POST /rollouts/{id}/start on non-PENDING returns 409."""
        rollout = _make_rollout(status=RolloutStatus.RUNNING)
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=rollout)

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.post(f"/api/control/rollouts/{rollout.id}/start")

        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_pause_rollout_success(self, client):
        """POST /rollouts/{id}/pause transitions RUNNING to PAUSED."""
        rollout = _make_rollout(status=RolloutStatus.RUNNING)
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=rollout)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        with patch("app.api.control.rollouts.pause_rollout") as mock_pause:
            mock_pause.return_value = rollout
            with patch("app.api.control.rollouts.write_audit", new_callable=AsyncMock):
                resp = await client.post(f"/api/control/rollouts/{rollout.id}/pause")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_resume_rollout_success(self, client):
        """POST /rollouts/{id}/resume transitions PAUSED to RUNNING."""
        rollout = _make_rollout(status=RolloutStatus.PAUSED)
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=rollout)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        with patch("app.api.control.rollouts.resume_rollout") as mock_resume:
            mock_resume.return_value = rollout
            with patch("app.api.control.rollouts.write_audit", new_callable=AsyncMock):
                resp = await client.post(f"/api/control/rollouts/{rollout.id}/resume")

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Audit API Tests
# ---------------------------------------------------------------------------


class TestAuditAPI:
    """Tests for /api/control/audit endpoint."""

    @pytest.mark.asyncio
    async def test_list_audit_logs(self, client):
        """GET /audit returns paginated list."""
        log = MagicMock(spec=AuditLog)
        log.id = uuid.uuid4()
        log.action = "agent_created"
        log.entity_type = "agent"
        log.entity_id = str(uuid.uuid4())
        log.actor = "admin"
        log.details = {"name": "test"}
        log.ip_address = "127.0.0.1"
        log.created_at = datetime.now(tz=timezone.utc)

        mock_db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [log]
        mock_db.execute.side_effect = [count_result, list_result]

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.get("/api/control/audit")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    @pytest.mark.asyncio
    async def test_list_audit_logs_filter_by_entity_type(self, client):
        """GET /audit?entity_type=agent filters results."""
        mock_db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [count_result, list_result]

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.get("/api/control/audit?entity_type=agent")

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Certificates API Tests
# ---------------------------------------------------------------------------


class TestCertificatesAPI:
    """Tests for /api/control/certs endpoints."""

    @pytest.mark.asyncio
    async def test_list_agent_certs(self, client):
        """GET /agents/{id}/certs returns certificate list."""
        agent = _make_agent()
        cert = MagicMock(spec=Certificate)
        cert.id = uuid.uuid4()
        cert.agent_id = agent.id
        cert.external_cert_id = None  # Self-signed cert, not from external source
        cert.local_path = "/etc/nginx/certs/api.example.com.crt"
        cert.serial_hex = "aabbccdd"
        cert.subject_cn = "example.com"
        cert.not_before = datetime.now(tz=timezone.utc) - timedelta(days=1)
        cert.not_after = datetime.now(tz=timezone.utc) + timedelta(days=365)
        cert.is_current = True
        cert.revoked_at = None
        cert.created_at = datetime.now(tz=timezone.utc)

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=agent)
        result = MagicMock()
        result.scalars.return_value.all.return_value = [cert]
        mock_db.execute.return_value = result

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.get(f"/api/control/agents/{agent.id}/certs")

        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["local_path"] == "/etc/nginx/certs/api.example.com.crt"

    @pytest.mark.asyncio
    async def test_get_cert_success(self, client):
        """GET /certs/{id} returns certificate detail."""
        cert = MagicMock(spec=Certificate)
        cert.id = uuid.uuid4()
        cert.agent_id = uuid.uuid4()
        cert.external_cert_id = None  # Self-signed cert, not from external source
        cert.local_path = "/etc/nginx/certs/api.example.com.crt"
        cert.serial_hex = "aabbccdd"
        cert.subject_cn = "example.com"
        cert.cert_pem = "-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----"
        cert.chain_pem = None
        cert.not_before = datetime.now(tz=timezone.utc) - timedelta(days=1)
        cert.not_after = datetime.now(tz=timezone.utc) + timedelta(days=365)
        cert.is_current = True
        cert.revoked_at = None
        cert.created_at = datetime.now(tz=timezone.utc)

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=cert)

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.get(f"/api/control/certs/{cert.id}")

        assert resp.status_code == 200
        assert resp.json()["serial_hex"] == "aabbccdd"

    @pytest.mark.asyncio
    async def test_get_cert_not_found(self, client):
        """GET /certs/{id} with invalid ID returns 404."""
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.get(f"/api/control/certs/{uuid.uuid4()}")

        assert resp.status_code == 404

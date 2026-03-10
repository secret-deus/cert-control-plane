"""End-to-end tests for Agent API endpoints.

Uses FastAPI TestClient with mocked DB and crypto layers.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.models import Agent, AgentStatus, Certificate, RolloutItem, RolloutItemStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(
    name: str = "test-agent-01",
    *,
    status: AgentStatus = AgentStatus.PENDING,
    bootstrap_token: str | None = "valid-token",
    token_created_at: datetime | None = None,
) -> Agent:
    agent = MagicMock(spec=Agent)
    agent.id = uuid.uuid4()
    agent.name = name
    agent.status = status
    agent.bootstrap_token = bootstrap_token
    agent.bootstrap_token_created_at = token_created_at or datetime.now(tz=timezone.utc)
    agent.fingerprint = None
    agent.last_seen = None
    return agent


def _make_cert(agent_id: uuid.UUID, serial: str = "aabb001122") -> Certificate:
    cert = MagicMock(spec=Certificate)
    cert.id = uuid.uuid4()
    cert.agent_id = agent_id
    cert.serial_hex = serial
    cert.subject_cn = "test-agent-01"
    cert.is_current = True
    cert.revoked_at = None
    cert.cert_pem = "-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----"
    cert.chain_pem = "-----BEGIN CERTIFICATE-----\nMOCK_CA\n-----END CERTIFICATE-----"
    cert.not_before = datetime.now(tz=timezone.utc) - timedelta(days=1)
    cert.not_after = datetime.now(tz=timezone.utc) + timedelta(days=364)
    cert.key_pem_encrypted = None
    return cert


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    """Create a fresh FastAPI app for each test, bypassing CA loading."""
    with patch("app.main.load_ca"), \
         patch("app.main.AsyncIOScheduler"):
        from app.main import create_app
        return create_app()


@pytest.fixture()
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Tests: /api/agent/register
# ---------------------------------------------------------------------------


class TestRegister:

    @pytest.mark.asyncio
    async def test_register_with_valid_token(self, client):
        agent = _make_agent(status=AgentStatus.PENDING)
        cert = _make_cert(agent.id)

        def mock_execute_side_effect(*args, **kwargs):
            result = MagicMock()
            result.scalar_one_or_none.return_value = agent
            return result

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=mock_execute_side_effect)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        with patch("app.api.agent.get_db") as mock_get_db, \
             patch("app.api.agent.registry") as mock_reg, \
             patch("app.api.agent.write_audit", new_callable=AsyncMock):
            mock_get_db.return_value = mock_db
            # Override the FastAPI dependency
            from app.database import get_db
            client._transport.app.dependency_overrides[get_db] = lambda: mock_db

            mock_reg.issue_from_csr = AsyncMock(return_value=cert)

            resp = await client.post("/api/agent/register", json={
                "bootstrap_token": "valid-token",
                "csr_pem": "-----BEGIN CERTIFICATE REQUEST-----\nMOCK\n-----END CERTIFICATE REQUEST-----",
            })

        assert resp.status_code == 201
        data = resp.json()
        assert "cert_pem" in data
        assert "agent_id" in data

    @pytest.mark.asyncio
    async def test_register_expired_token(self, client):
        agent = _make_agent(
            status=AgentStatus.PENDING,
            token_created_at=datetime.now(tz=timezone.utc) - timedelta(hours=48),
        )

        def mock_execute(*args, **kwargs):
            result = MagicMock()
            result.scalar_one_or_none.return_value = agent
            return result

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=mock_execute)

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.post("/api/agent/register", json={
            "bootstrap_token": "valid-token",
            "csr_pem": "-----BEGIN CERTIFICATE REQUEST-----\nMOCK\n-----END CERTIFICATE REQUEST-----",
        })

        assert resp.status_code == 401
        assert "expired" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_register_consumes_token(self, client):
        agent = _make_agent(status=AgentStatus.PENDING)
        cert = _make_cert(agent.id)

        def mock_execute(*args, **kwargs):
            result = MagicMock()
            result.scalar_one_or_none.return_value = agent
            return result

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=mock_execute)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        with patch("app.api.agent.registry") as mock_reg, \
             patch("app.api.agent.write_audit", new_callable=AsyncMock):
            mock_reg.issue_from_csr = AsyncMock(return_value=cert)

            await client.post("/api/agent/register", json={
                "bootstrap_token": "valid-token",
                "csr_pem": "-----BEGIN CERTIFICATE REQUEST-----\nMOCK\n-----END CERTIFICATE REQUEST-----",
            })

        # Token should be consumed (set to None)
        assert agent.bootstrap_token is None


# ---------------------------------------------------------------------------
# Tests: /api/agent/heartbeat
# ---------------------------------------------------------------------------


class TestHeartbeat:

    @pytest.mark.asyncio
    async def test_heartbeat_returns_pending_action(self, client):
        agent = _make_agent(status=AgentStatus.ACTIVE)
        cert = _make_cert(agent.id, serial="aabb001122")

        pending_item = MagicMock(spec=RolloutItem)
        pending_item.status = RolloutItemStatus.IN_PROGRESS

        call_count = 0

        def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # Agent lookup
                result.scalar_one_or_none.return_value = agent
            elif call_count == 2:
                # Cert lookup
                result.scalar_one_or_none.return_value = cert
            elif call_count == 3:
                # Rollout item lookup
                result.scalar_one_or_none.return_value = pending_item
            else:
                result.scalar_one_or_none.return_value = None
            return result

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=mock_execute)
        mock_db.commit = AsyncMock()

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.post(
            "/api/agent/heartbeat",
            json={"status": "ok"},
            headers={
                "X-Client-CN": "test-agent-01",
                "X-Client-Serial": "AA:BB:00:11:22",
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["acknowledged"] is True
        assert data["pending_action"] == "renew"


# ---------------------------------------------------------------------------
# Tests: /api/agent/renew
# ---------------------------------------------------------------------------


class TestRenew:

    @pytest.mark.asyncio
    async def test_renew_marks_rollout_item_completed(self, client):
        agent = _make_agent(status=AgentStatus.ACTIVE)
        cert = _make_cert(agent.id, serial="aabb001122")
        new_cert = _make_cert(agent.id, serial="ccdd002233")

        rollout_item = MagicMock(spec=RolloutItem)
        rollout_item.status = RolloutItemStatus.IN_PROGRESS
        rollout_item.new_cert_id = None
        rollout_item.completed_at = None

        call_count = 0

        def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # _resolve_agent: agent lookup
                result.scalar_one_or_none.return_value = agent
            elif call_count == 2:
                # _resolve_agent: cert lookup
                result.scalar_one_or_none.return_value = cert
            elif call_count == 3:
                # renew_cert: rollout item lookup
                result.scalar_one_or_none.return_value = rollout_item
            else:
                result.scalar_one_or_none.return_value = None
            return result

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=mock_execute)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        with patch("app.api.agent.registry") as mock_reg, \
             patch("app.api.agent.write_audit", new_callable=AsyncMock):
            mock_reg.issue_from_csr = AsyncMock(return_value=new_cert)

            resp = await client.post(
                "/api/agent/renew",
                json={"csr_pem": "-----BEGIN CERTIFICATE REQUEST-----\nMOCK\n-----END CERTIFICATE REQUEST-----"},
                headers={
                    "X-Client-CN": "test-agent-01",
                    "X-Client-Serial": "AA:BB:00:11:22",
                },
            )

        assert resp.status_code == 200
        assert rollout_item.status == RolloutItemStatus.COMPLETED
        assert rollout_item.new_cert_id == new_cert.id

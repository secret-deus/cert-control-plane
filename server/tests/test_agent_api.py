"""End-to-end tests for the new TOFU-based Agent API endpoints.

Tests: /api/agent/register, /api/agent/register/status,
       /api/agent/heartbeat, /api/agent/fetch-certs
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.models import Agent, AgentCertAssignment, AgentStatus, ExternalCertificate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _make_agent(
    name: str = "test-agent-01",
    *,
    status: AgentStatus = AgentStatus.PENDING_APPROVAL,
    fingerprint: str | None = "aabbcc" * 10 + "aabb",  # 64 hex chars
    agent_token: str | None = None,
) -> Agent:
    agent = MagicMock(spec=Agent)
    agent.id = uuid.uuid4()
    agent.name = name
    agent.status = status
    agent.fingerprint = fingerprint
    agent.agent_token = agent_token
    agent.last_seen = None
    return agent


def _make_ext_cert(
    not_after: datetime | None = None,
    is_active: bool = True,
) -> ExternalCertificate:
    cert = MagicMock(spec=ExternalCertificate)
    cert.id = uuid.uuid4()
    cert.name = "prod-cert"
    cert.is_active = is_active
    cert.cert_pem = "-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----"
    cert.chain_pem = "-----BEGIN CERTIFICATE-----\nMOCK_CHAIN\n-----END CERTIFICATE-----"
    cert.key_pem_encrypted = "encrypted-key-data"
    cert.not_after = not_after or (datetime.now(tz=timezone.utc) + timedelta(days=365))
    return cert


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    """Create a fresh FastAPI app for each test (no CA loading needed)."""
    from app.main import create_app
    return create_app()


@pytest.fixture()
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Tests: POST /api/agent/register (TOFU)
# ---------------------------------------------------------------------------


class TestRegister:

    @pytest.mark.asyncio
    async def test_new_agent_returns_pending(self, client):
        """Brand-new name → creates agent, returns status=pending."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = _make_result(None)   # No existing agent
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock(side_effect=lambda a: None)
        mock_db.flush = AsyncMock()
        mock_db.add = MagicMock()

        # Inject a fresh agent after flush
        new_agent = _make_agent(status=AgentStatus.PENDING_APPROVAL)
        mock_db.refresh.side_effect = lambda a: setattr(a, 'id', new_agent.id)

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        fingerprint = "a" * 64

        with patch("app.api.agent.write_audit", new_callable=AsyncMock):
            resp = await client.post("/api/agent/register", json={
                "name": "brand-new-agent",
                "fingerprint": fingerprint,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["agent_token"] is None

    @pytest.mark.asyncio
    async def test_existing_approved_agent_returns_token(self, client):
        """Matching fingerprint + active agent → returns approved + token."""
        token = "secret-agent-token"
        agent = _make_agent(status=AgentStatus.ACTIVE, agent_token=token)

        mock_db = AsyncMock()
        mock_db.execute.return_value = _make_result(agent)  # Existing agent found

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.post("/api/agent/register", json={
            "name": agent.name,
            "fingerprint": agent.fingerprint,
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"
        assert data["agent_token"] == token

    @pytest.mark.asyncio
    async def test_fingerprint_mismatch_returns_403(self, client):
        """Existing agent, different fingerprint → 403 (impersonation attempt)."""
        agent = _make_agent(fingerprint="a" * 64)

        mock_db = AsyncMock()
        mock_db.execute.return_value = _make_result(agent)

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.post("/api/agent/register", json={
            "name": agent.name,
            "fingerprint": "b" * 64,   # Different fingerprint
        })

        assert resp.status_code == 403
        assert "fingerprint" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_pending_agent_returns_pending(self, client):
        """Existing agent still pending → returns status=pending (no token)."""
        agent = _make_agent(status=AgentStatus.PENDING_APPROVAL, agent_token=None)

        mock_db = AsyncMock()
        mock_db.execute.return_value = _make_result(agent)

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.post("/api/agent/register", json={
            "name": agent.name,
            "fingerprint": agent.fingerprint,
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["agent_token"] is None

    @pytest.mark.asyncio
    async def test_precreated_agent_slot_binds_first_fingerprint(self, client):
        """Pre-created agent slot should accept the first observed fingerprint."""
        agent = _make_agent(
            status=AgentStatus.PENDING_APPROVAL,
            fingerprint=None,
            agent_token=None,
        )

        mock_db = AsyncMock()
        mock_db.execute.return_value = _make_result(agent)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.add = MagicMock()

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        fingerprint = "c" * 64

        with patch("app.api.agent.write_audit", new_callable=AsyncMock):
            resp = await client.post("/api/agent/register", json={
                "name": agent.name,
                "fingerprint": fingerprint,
            })

        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"
        assert agent.fingerprint == fingerprint

    @pytest.mark.asyncio
    async def test_rejected_agent_returns_403(self, client):
        """Rejected agent cannot re-register with the same fingerprint."""
        agent = _make_agent(
            status=AgentStatus.REVOKED,
            fingerprint="d" * 64,
            agent_token=None,
        )

        mock_db = AsyncMock()
        mock_db.execute.return_value = _make_result(agent)

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.post("/api/agent/register", json={
            "name": agent.name,
            "fingerprint": agent.fingerprint,
        })

        assert resp.status_code == 403
        assert "rejected" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Tests: GET /api/agent/register/status
# ---------------------------------------------------------------------------


class TestRegisterStatus:

    @pytest.mark.asyncio
    async def test_approved_returns_token(self, client):
        """Approved agent → status=approved + agent_token."""
        token = "my-secret-token"
        agent = _make_agent(status=AgentStatus.ACTIVE, agent_token=token)

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=agent)

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.get(
            f"/api/agent/register/status",
            params={"agent_id": str(agent.id), "fingerprint": agent.fingerprint},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"
        assert data["agent_token"] == token

    @pytest.mark.asyncio
    async def test_pending_returns_pending(self, client):
        """Still-pending agent → status=pending_approval, no token."""
        agent = _make_agent(status=AgentStatus.PENDING_APPROVAL, agent_token=None)

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=agent)

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.get(
            "/api/agent/register/status",
            params={"agent_id": str(agent.id), "fingerprint": agent.fingerprint},
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "pending_approval"

    @pytest.mark.asyncio
    async def test_revoked_returns_rejected(self, client):
        """Revoked agent → status=rejected."""
        agent = _make_agent(status=AgentStatus.REVOKED, agent_token=None)

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=agent)

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.get(
            "/api/agent/register/status",
            params={"agent_id": str(agent.id), "fingerprint": agent.fingerprint},
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_fingerprint_mismatch_returns_403(self, client):
        """Fingerprint in query doesn't match DB → 403."""
        agent = _make_agent(fingerprint="a" * 64)

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=agent)

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.get(
            "/api/agent/register/status",
            params={"agent_id": str(agent.id), "fingerprint": "b" * 64},
        )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self, client):
        """Unknown agent_id → 404."""
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.get(
            "/api/agent/register/status",
            params={"agent_id": str(uuid.uuid4()), "fingerprint": "a" * 64},
        )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: POST /api/agent/heartbeat
# ---------------------------------------------------------------------------


class TestHeartbeat:

    @pytest.mark.asyncio
    async def test_heartbeat_with_valid_token(self, client):
        """Valid X-Agent-Token → 200, acknowledged=True."""
        token = "valid-agent-token"
        agent = _make_agent(status=AgentStatus.ACTIVE, agent_token=token)

        mock_db = AsyncMock()
        mock_db.execute.return_value = _make_result(agent)
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.post(
            "/api/agent/heartbeat",
            json={"status": "ok"},
            headers={"X-Agent-Token": token},
        )

        assert resp.status_code == 200
        assert resp.json()["acknowledged"] is True

    @pytest.mark.asyncio
    async def test_heartbeat_missing_token_returns_401(self, client):
        """No X-Agent-Token header → 401."""
        mock_db = AsyncMock()

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        # dev_mode off by default in tests
        resp = await client.post("/api/agent/heartbeat", json={"status": "ok"})

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_heartbeat_invalid_token_returns_403(self, client):
        """Invalid token (no matching active agent) → 403."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = _make_result(None)   # Token not found

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.post(
            "/api/agent/heartbeat",
            json={"status": "ok"},
            headers={"X-Agent-Token": "bad-token"},
        )

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Tests: POST /api/agent/fetch-certs
# ---------------------------------------------------------------------------


class TestFetchCerts:

    @pytest.mark.asyncio
    async def test_no_assignment_returns_no_update(self, client):
        """local_path has no assignment → has_update=False."""
        token = "agent-token"
        agent = _make_agent(status=AgentStatus.ACTIVE, agent_token=token)

        call_count = 0

        def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = agent   # token lookup
            else:
                result.scalar_one_or_none.return_value = None    # no assignment
            return result

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=mock_execute)
        mock_db.commit = AsyncMock()

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        with patch("app.api.agent.write_audit", new_callable=AsyncMock), \
             patch("app.api.agent._get_active_rollout_item", new_callable=AsyncMock, return_value=None), \
             patch("app.api.agent._complete_rollout_item_if_ready", new_callable=AsyncMock):
            resp = await client.post(
                "/api/agent/fetch-certs",
                json={"certs": [{"local_path": "/etc/nginx/ssl/a.crt"}]},
                headers={"X-Agent-Token": token},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["updates"]) == 1
        assert data["updates"][0]["has_update"] is False

    @pytest.mark.asyncio
    async def test_newer_cert_returns_update(self, client):
        """Assignment exists, server cert is newer → has_update=True with cert data."""
        token = "agent-token"
        agent = _make_agent(status=AgentStatus.ACTIVE, agent_token=token)

        ext_cert = _make_ext_cert(
            not_after=datetime.now(tz=timezone.utc) + timedelta(days=365)
        )

        assignment = MagicMock(spec=AgentCertAssignment)
        assignment.agent_id = agent.id
        assignment.external_cert_id = ext_cert.id
        assignment.local_path = "/etc/nginx/ssl/api.crt"

        call_count = 0

        def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = agent      # token lookup
            elif call_count == 2:
                result.scalar_one_or_none.return_value = assignment  # assignment lookup
            return result

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=mock_execute)
        mock_db.get = AsyncMock(return_value=ext_cert)
        mock_db.commit = AsyncMock()

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        # old not_after is a year ago → server cert is newer
        old_not_after = datetime.now(tz=timezone.utc) - timedelta(days=365)

        with patch("app.api.agent.write_audit", new_callable=AsyncMock), \
             patch("app.api.agent._get_active_rollout_item", new_callable=AsyncMock, return_value=None), \
             patch("app.api.agent._complete_rollout_item_if_ready", new_callable=AsyncMock), \
             patch("app.api.agent.decrypt_key", return_value=b"PLAINTEXT-KEY"):
            resp = await client.post(
                "/api/agent/fetch-certs",
                json={"certs": [
                    {"local_path": "/etc/nginx/ssl/api.crt",
                     "current_not_after": old_not_after.isoformat()}
                ]},
                headers={"X-Agent-Token": token},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["updates"][0]["has_update"] is True
        assert data["updates"][0]["cert_pem"] is not None
        assert data["updates"][0]["key_pem"] == "PLAINTEXT-KEY"

    @pytest.mark.asyncio
    async def test_up_to_date_cert_returns_no_update(self, client):
        """Current not_after matches or is newer than server → has_update=False."""
        token = "agent-token"
        agent = _make_agent(status=AgentStatus.ACTIVE, agent_token=token)

        server_not_after = datetime.now(tz=timezone.utc) + timedelta(days=365)
        ext_cert = _make_ext_cert(not_after=server_not_after)

        assignment = MagicMock(spec=AgentCertAssignment)
        assignment.agent_id = agent.id
        assignment.external_cert_id = ext_cert.id
        assignment.local_path = "/etc/nginx/ssl/api.crt"

        call_count = 0

        def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = agent
            else:
                result.scalar_one_or_none.return_value = assignment
            return result

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=mock_execute)
        mock_db.get = AsyncMock(return_value=ext_cert)
        mock_db.commit = AsyncMock()

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        with patch("app.api.agent.write_audit", new_callable=AsyncMock), \
             patch("app.api.agent._get_active_rollout_item", new_callable=AsyncMock, return_value=None), \
             patch("app.api.agent._complete_rollout_item_if_ready", new_callable=AsyncMock), \
             patch("app.api.agent.record_deployed_cert", new_callable=AsyncMock):
            resp = await client.post(
                "/api/agent/fetch-certs",
                json={"certs": [
                    {"local_path": "/etc/nginx/ssl/api.crt",
                     # Send same not_after as server → no update needed
                     "current_not_after": server_not_after.isoformat()}
                ]},
                headers={"X-Agent-Token": token},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["updates"][0]["has_update"] is False


class TestReportCerts:

    @pytest.mark.asyncio
    async def test_report_certs_records_deployment(self, client):
        """Agent reports deployed certs → records Certificate snapshots."""
        token = "agent-token"
        agent = _make_agent(status=AgentStatus.ACTIVE, agent_token=token)

        ext_cert = _make_ext_cert()
        assignment = MagicMock(spec=AgentCertAssignment)
        assignment.agent_id = agent.id
        assignment.external_cert_id = ext_cert.id
        assignment.local_path = "/etc/nginx/ssl/api.crt"

        call_count = 0

        def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = agent
            elif call_count == 2:
                result.scalar_one_or_none.return_value = assignment
            else:
                result.scalar_one_or_none.return_value = None
            return result

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=mock_execute)
        mock_db.get = AsyncMock(return_value=ext_cert)
        mock_db.commit = AsyncMock()
        mock_db.flush = AsyncMock()
        mock_db.add = MagicMock()

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        with patch("app.api.agent.write_audit", new_callable=AsyncMock), \
             patch("app.api.agent.record_deployed_cert", new_callable=AsyncMock) as mock_record, \
             patch("app.api.agent._get_active_rollout_item", new_callable=AsyncMock, return_value=None), \
             patch("app.api.agent._complete_rollout_item_if_ready", new_callable=AsyncMock):
            resp = await client.post(
                "/api/agent/report-certs",
                json={"certs": [
                    {
                        "local_path": "/etc/nginx/ssl/api.crt",
                        "cert_pem": "-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----",
                    }
                ]},
                headers={"X-Agent-Token": token},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["recorded"] == 1
        mock_record.assert_called_once()

    @pytest.mark.asyncio
    async def test_report_certs_skips_unassigned_paths(self, client):
        """Paths without assignments are skipped."""
        token = "agent-token"
        agent = _make_agent(status=AgentStatus.ACTIVE, agent_token=token)

        call_count = 0

        def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = agent
            else:
                result.scalar_one_or_none.return_value = None
            return result

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=mock_execute)
        mock_db.get = AsyncMock(return_value=None)
        mock_db.commit = AsyncMock()

        from app.database import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_db

        with patch("app.api.agent._get_active_rollout_item", new_callable=AsyncMock, return_value=None), \
             patch("app.api.agent._complete_rollout_item_if_ready", new_callable=AsyncMock):
            resp = await client.post(
                "/api/agent/report-certs",
                json={"certs": [
                    {
                        "local_path": "/etc/nginx/ssl/unassigned.crt",
                        "cert_pem": "-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----",
                    }
                ]},
                headers={"X-Agent-Token": token},
            )

        assert resp.status_code == 200
        assert resp.json()["recorded"] == 0

    @pytest.mark.asyncio
    async def test_report_certs_missing_token_returns_401(self, client):
        """Missing X-Agent-Token → 401."""
        resp = await client.post(
            "/api/agent/report-certs",
            json={"certs": []},
        )
        assert resp.status_code == 401

import pytest
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import uuid

# Admin key set in conftest.py: "test-admin-key-for-pytest"
HEADERS = {"X-Admin-API-Key": "test-admin-key-for-pytest"}


def _make_scalars_result(items):
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    return result

@pytest.mark.asyncio
async def test_dashboard_summary(mock_db):
    from app.main import app
    
    async def mock_scalar_one():
        return 5
        
    class MockResult:
        def scalar_one(self):
            return 5
            
    # Remove the side_effect from conftest.py's mock_db, which only has 2 items
    mock_db.execute.side_effect = None
    mock_db.execute.return_value = MockResult()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        # Provide the mock_db to the dependency override
        from app.database import get_db
        app.dependency_overrides[get_db] = lambda: mock_db
        
        response = await client.get("/api/control/dashboard/summary", headers=HEADERS)
        
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
        assert "certificates" in data
        assert "rollouts" in data

@pytest.mark.asyncio
async def test_dashboard_agents_health(mock_db):
    from app.main import app
    from app.models import Agent, Certificate
    
    agent = Agent(id=uuid.uuid4(), name="test-agent", status="active", last_seen=datetime.now(tz=timezone.utc))
    cert = Certificate(id=uuid.uuid4(), agent_id=agent.id, not_after=datetime.now(tz=timezone.utc))
    
    class MockResult:
        def all(self):
            return [(agent, cert)]
            
    mock_db.execute.side_effect = None
    mock_db.execute.return_value = MockResult()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        from app.database import get_db
        app.dependency_overrides[get_db] = lambda: mock_db
        
        response = await client.get("/api/control/dashboard/agents-health", headers=HEADERS)
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "test-agent"
        assert data[0]["liveness"] == "online"

@pytest.mark.asyncio
async def test_dashboard_unauthorized(mock_db):
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        response = await client.get("/api/control/dashboard/summary")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_external_certs_expiry(mock_db):
    from app.main import app

    now = datetime.now(tz=timezone.utc)
    critical = MagicMock()
    critical.id = uuid.uuid4()
    critical.name = "critical-cert"
    critical.subject_cn = "critical.example.com"
    critical.serial_hex = "critical01"
    critical.not_after = now + timedelta(days=5)
    critical.provider = "manual"

    notice = MagicMock()
    notice.id = uuid.uuid4()
    notice.name = "notice-cert"
    notice.subject_cn = "notice.example.com"
    notice.serial_hex = "notice01"
    notice.not_after = now + timedelta(days=20)
    notice.provider = "manual"

    mock_db.execute.side_effect = None
    mock_db.execute.return_value = _make_scalars_result([critical, notice])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        from app.database import get_db
        app.dependency_overrides[get_db] = lambda: mock_db

        response = await client.get("/api/control/dashboard/external-certs-expiry", headers=HEADERS)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["name"] == "critical-cert"
        assert data[0]["urgency"] == "critical"
        assert data[1]["name"] == "notice-cert"
        assert data[1]["urgency"] == "notice"


@pytest.mark.asyncio
async def test_dashboard_cert_alerts(mock_db):
    from app.main import app

    now = datetime.now(tz=timezone.utc)

    ext_expired = MagicMock()
    ext_expired.id = uuid.uuid4()
    ext_expired.name = "expired-ext"
    ext_expired.subject_cn = "expired-ext.example.com"
    ext_expired.serial_hex = "ext-expired"
    ext_expired.not_after = now - timedelta(days=1)
    ext_expired.provider = "manual"

    ext_warning = MagicMock()
    ext_warning.id = uuid.uuid4()
    ext_warning.name = "warning-ext"
    ext_warning.subject_cn = "warning-ext.example.com"
    ext_warning.serial_hex = "ext-warning"
    ext_warning.not_after = now + timedelta(days=10)
    ext_warning.provider = "manual"

    agent_critical = MagicMock()
    agent_critical.id = uuid.uuid4()
    agent_critical.agent_id = uuid.uuid4()
    agent_critical.subject_cn = "critical-agent.example.com"
    agent_critical.serial_hex = "agent-critical"
    agent_critical.not_after = now + timedelta(days=3)

    agent_notice = MagicMock()
    agent_notice.id = uuid.uuid4()
    agent_notice.agent_id = uuid.uuid4()
    agent_notice.subject_cn = "notice-agent.example.com"
    agent_notice.serial_hex = "agent-notice"
    agent_notice.not_after = now + timedelta(days=20)

    mock_db.execute.side_effect = [
        _make_scalars_result([ext_expired, ext_warning]),
        _make_scalars_result([agent_critical, agent_notice]),
    ]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        from app.database import get_db
        app.dependency_overrides[get_db] = lambda: mock_db

        response = await client.get("/api/control/dashboard/cert-alerts", headers=HEADERS)

        assert response.status_code == 200
        data = response.json()

        assert data["summary"]["external"]["total_alerts"] == 2
        assert data["summary"]["external"]["expired"] == 1
        assert data["summary"]["external"]["warning"] == 1
        assert data["summary"]["agent"]["total_alerts"] == 2
        assert data["summary"]["agent"]["critical"] == 1
        assert data["summary"]["agent"]["notice"] == 1

        assert len(data["external_certs"]["expired"]) == 1
        assert data["external_certs"]["expired"][0]["name"] == "expired-ext"
        assert len(data["agent_certs"]["critical"]) == 1
        assert data["agent_certs"]["critical"][0]["subject_cn"] == "critical-agent.example.com"

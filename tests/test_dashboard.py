import pytest
from httpx import AsyncClient, ASGITransport

# Admin key set in conftest.py: "test-admin-key-for-pytest"
HEADERS = {"X-Admin-API-Key": "test-admin-key-for-pytest"}

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
    from datetime import datetime, timezone
    import uuid
    
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

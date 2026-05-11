from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.mark.asyncio
async def test_healthz_not_shadowed_by_spa_fallback():
    app = create_app()

    with patch("app.main.check_db", new=AsyncMock(return_value=True)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readyz_reports_database_status():
    app = create_app()

    with patch("app.main.check_db", new=AsyncMock(return_value=True)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "connected"}


@pytest.mark.asyncio
async def test_metrics_not_shadowed_by_spa_fallback():
    app = create_app()

    with patch("app.main.check_db", new=AsyncMock(return_value=True)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/metrics")

    assert response.status_code == 200
    assert "certcp_up 1" in response.text
    assert "certcp_db_up 1" in response.text

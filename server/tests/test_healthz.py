from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


def test_security_headers_are_added_to_responses():
    app = create_app()

    transport = ASGITransport(app=app)

    async def run():
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/healthz")

    import anyio
    response = anyio.run(run)

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["permissions-policy"] == "geolocation=(), microphone=(), camera=()"
    assert "default-src 'self'" in response.headers["content-security-policy"]


@pytest.mark.asyncio
async def test_cors_preflight_is_restricted_to_required_methods_and_headers(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("CORS_ORIGINS", '["http://dashboard.test"]')
    get_settings.cache_clear()
    app = create_app()
    get_settings.cache_clear()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/api/control/agents",
            headers={
                "Origin": "http://dashboard.test",
                "Access-Control-Request-Method": "PATCH",
                "Access-Control-Request-Headers": "X-Admin-API-Key",
            },
        )

    assert response.status_code == 400
    assert "PATCH" not in response.headers["access-control-allow-methods"]
    assert "X-Admin-API-Key" in response.headers["access-control-allow-headers"]


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

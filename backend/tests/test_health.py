"""
backend/tests/test_health.py — Health endpoint smoke test.

Validates the GET /api/health endpoint returns the expected JSON shape.

Created: 2026-03-03
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_returns_ok() -> None:
    """GET /api/health should return 200 with status 'ok'."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    assert isinstance(body["solver_available"], bool)


@pytest.mark.asyncio
async def test_health_response_shape() -> None:
    """Health response must contain exactly the expected keys."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")

    body = resp.json()
    expected_keys = {"status", "solver_available", "version"}
    assert set(body.keys()) == expected_keys


@pytest.mark.asyncio
async def test_cors_preflight() -> None:
    """OPTIONS /api/health should return CORS headers for localhost:5173."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert resp.status_code == 200
    assert "http://localhost:5173" in resp.headers.get(
        "access-control-allow-origin", ""
    )

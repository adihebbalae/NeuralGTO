"""
backend/tests/test_analyze.py — Tests for POST /api/analyze endpoint.

Covers:
  1. Happy-path with mocked pipeline (solver source)
  2. Happy-path with mocked pipeline (LLM fallback source)
  3. Structured input (hero_hand instead of query)
  4. Empty body → 400 validation
  5. Pipeline ValueError → 400 parse error
  6. Pipeline unexpected exception → 500 internal error
  7. Response shape matches AnalyzeResponse contract
  8. Mode enum validation (rejects invalid modes)

All tests mock ``poker_gpt.main.analyze_hand`` so they run offline —
no Gemini API key or solver binary required.

Created: 2026-03-03
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

_MOCK_RESULT_SOLVER: dict[str, Any] = {
    "advice": "You should raise with QQ on the BTN.",
    "mode": "default",
    "scenario": None,
    "strategy": {
        "hand": "QhQd",
        "actions": {"Raise": 0.78, "Fold": 0.22},
        "best_action": "Raise",
        "best_action_freq": 0.78,
        "range_summary": {},
        "source": "solver",
    },
    "sanity_note": "",
    "cached": False,
    "solve_time": 2.5,
    "source": "solver",
    "confidence": "high",
    "parse_time": 1.2,
    "spot_frequency": None,
    "output_level": "advanced",
}

_MOCK_RESULT_LLM: dict[str, Any] = {
    "advice": "Based on your hand, consider raising.",
    "mode": "fast",
    "scenario": None,
    "strategy": None,
    "sanity_note": "",
    "cached": False,
    "solve_time": 0.0,
    "source": "gemini",
    "confidence": "medium",
    "parse_time": 0.8,
    "spot_frequency": None,
    "output_level": "advanced",
}


def _make_client() -> AsyncClient:
    """Build a test client for the app."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ──────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_analyze_happy_path_solver() -> None:
    """POST /api/analyze with valid query returns 200 + solver result."""
    with patch("app.api.analyze._analyze_hand", return_value=_MOCK_RESULT_SOLVER) as mock:
        async with _make_client() as client:
            resp = await client.post(
                "/api/analyze",
                json={"query": "I have QhQd on the BTN, 100bb deep"},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["advice"] == "You should raise with QQ on the BTN."
    assert body["source"] == "solver"
    assert body["confidence"] == "high"
    mock.assert_called_once()


@pytest.mark.asyncio
async def test_analyze_happy_path_llm_fallback() -> None:
    """POST /api/analyze in fast mode returns LLM-only result."""
    with patch("app.api.analyze._analyze_hand", return_value=_MOCK_RESULT_LLM):
        async with _make_client() as client:
            resp = await client.post(
                "/api/analyze",
                json={
                    "query": "I have AKs UTG, 100bb stacks",
                    "mode": "fast",
                },
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "gemini"
    assert body["solve_time"] == 0.0


@pytest.mark.asyncio
async def test_analyze_structured_input() -> None:
    """POST /api/analyze with structured fields (no query) works."""
    with patch("app.api.analyze._analyze_hand", return_value=_MOCK_RESULT_SOLVER) as mock:
        async with _make_client() as client:
            resp = await client.post(
                "/api/analyze",
                json={
                    "hero_hand": "QhQd",
                    "hero_position": "BTN",
                    "effective_stack_bb": 100.0,
                },
            )

    assert resp.status_code == 200
    # The assembled query should include hero_hand and position
    call_kwargs = mock.call_args
    # analyze_hand is called via partial — check the kwargs
    assert "QhQd" in str(call_kwargs)


@pytest.mark.asyncio
async def test_analyze_empty_body_returns_error() -> None:
    """POST /api/analyze with empty body (no query, no hero_hand) returns 400."""
    with patch("app.api.analyze._analyze_hand", return_value=_MOCK_RESULT_SOLVER):
        async with _make_client() as client:
            resp = await client.post("/api/analyze", json={})

    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_analyze_pipeline_value_error() -> None:
    """Pipeline raising ValueError → 400 with error details."""
    with patch(
        "app.api.analyze._analyze_hand",
        side_effect=ValueError("Could not parse hand"),
    ):
        async with _make_client() as client:
            resp = await client.post(
                "/api/analyze",
                json={"query": "some bad input that fails parsing"},
            )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "PARSE_FAILED"
    assert "parse" in body["detail"].lower() or "hand" in body["detail"].lower()


@pytest.mark.asyncio
async def test_analyze_pipeline_unexpected_error() -> None:
    """Pipeline raising unexpected exception → 500 internal error."""
    with patch(
        "app.api.analyze._analyze_hand",
        side_effect=RuntimeError("Unexpected crash"),
    ):
        async with _make_client() as client:
            resp = await client.post(
                "/api/analyze",
                json={"query": "I have AA, what do I do"},
            )

    assert resp.status_code == 500
    body = resp.json()
    assert body["error_code"] == "INTERNAL_ERROR"


@pytest.mark.asyncio
async def test_analyze_response_shape() -> None:
    """Response JSON must contain all AnalyzeResponse keys."""
    with patch("app.api.analyze._analyze_hand", return_value=_MOCK_RESULT_SOLVER):
        async with _make_client() as client:
            resp = await client.post(
                "/api/analyze",
                json={"query": "QQ on BTN, 100bb deep"},
            )

    body = resp.json()
    required_keys = {
        "advice", "source", "confidence", "mode", "cached",
        "solve_time", "parse_time", "output_level", "sanity_note",
        "scenario", "strategy", "structured_advice",
    }
    assert required_keys.issubset(set(body.keys())), (
        f"Missing keys: {required_keys - set(body.keys())}"
    )


@pytest.mark.asyncio
async def test_analyze_invalid_mode() -> None:
    """Invalid mode value → 422 validation error from Pydantic."""
    async with _make_client() as client:
        resp = await client.post(
            "/api/analyze",
            json={"query": "I have AA", "mode": "ultra_turbo"},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_analyze_with_opponent_notes() -> None:
    """Opponent notes are forwarded to analyze_hand."""
    with patch("app.api.analyze._analyze_hand", return_value=_MOCK_RESULT_SOLVER) as mock:
        async with _make_client() as client:
            resp = await client.post(
                "/api/analyze",
                json={
                    "query": "I have QhQd on the BTN",
                    "opponent_notes": "Villain folds too much to 3bets",
                },
            )

    assert resp.status_code == 200
    # Verify opponent_notes was forwarded
    assert "folds too much" in str(mock.call_args)


@pytest.mark.asyncio
async def test_analyze_cors_preflight() -> None:
    """OPTIONS /api/analyze should return CORS headers for localhost:5173."""
    async with _make_client() as client:
        resp = await client.options(
            "/api/analyze",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert resp.status_code == 200
    assert "http://localhost:5173" in resp.headers.get(
        "access-control-allow-origin", ""
    )


# ──────────────────────────────────────────────
# W5.0b (impl) — Structured advice in response
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_analyze_structured_advice_present() -> None:
    """Response must contain structured_advice with top plays when strategy exists."""
    with patch("app.api.analyze._analyze_hand", return_value=_MOCK_RESULT_SOLVER):
        async with _make_client() as client:
            resp = await client.post(
                "/api/analyze",
                json={"query": "I have QhQd on the BTN, 100bb deep"},
            )

    assert resp.status_code == 200
    body = resp.json()
    sa = body["structured_advice"]
    assert sa is not None
    assert len(sa["top_plays"]) > 0
    # Top play should be the highest-frequency action
    assert sa["top_plays"][0]["action"] == "Raise"
    assert sa["top_plays"][0]["frequency"] == 0.78
    # Should include raw_advice
    assert sa["raw_advice"] != ""


@pytest.mark.asyncio
async def test_analyze_structured_advice_llm_fallback() -> None:
    """LLM-only result should still populate structured_advice."""
    with patch("app.api.analyze._analyze_hand", return_value=_MOCK_RESULT_LLM):
        async with _make_client() as client:
            resp = await client.post(
                "/api/analyze",
                json={"query": "I have AKs UTG", "mode": "fast"},
            )

    assert resp.status_code == 200
    body = resp.json()
    sa = body["structured_advice"]
    assert sa is not None
    assert len(sa["top_plays"]) >= 1


@pytest.mark.asyncio
async def test_analyze_timeout_returns_504() -> None:
    """Pipeline raising TimeoutError → 504 with solver timeout message."""
    with (
        patch(
            "app.api.analyze._analyze_hand",
            side_effect=TimeoutError("Solver exceeded 120s limit"),
        ),
        patch(
            "app.api.analyze._limiter.enabled",
            False,
        ),
    ):
        async with _make_client() as client:
            resp = await client.post(
                "/api/analyze",
                json={"query": "I have QhQd on the BTN, 100bb deep"},
            )

    assert resp.status_code == 504
    body = resp.json()
    assert body["error_code"] == "SOLVER_TIMEOUT"
    assert "fast" in body["detail"].lower()


@pytest.mark.asyncio
async def test_analyze_solver_unavailable_degrades() -> None:
    """When pipeline returns llm_fallback source, response has low confidence."""
    fallback_result = dict(_MOCK_RESULT_LLM, source="llm_fallback", confidence="low")
    with (
        patch("app.api.analyze._analyze_hand", return_value=fallback_result),
        patch("app.api.analyze._limiter.enabled", False),
    ):
        async with _make_client() as client:
            resp = await client.post(
                "/api/analyze",
                json={"query": "I have QhQd on the BTN, 100bb deep"},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "gpt_fallback"  # llm_fallback → gpt_fallback via adapter
    assert body["confidence"] == "low"
    assert body["advice"] != ""

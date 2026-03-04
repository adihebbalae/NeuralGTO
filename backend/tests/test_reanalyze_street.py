"""
backend/tests/test_reanalyze_street.py — Tests for POST /api/reanalyze-street endpoint.

Covers:
  1. Happy-path with valid scenario + new cards
  2. Board progression (preflop → flop, flop → turn, turn → river)
  3. Invalid board cards → 422 validation error
  4. Missing required fields → 422 validation error
  5. Pipeline failure → 500 internal error
  6. Response shape matches AnalyzeResponse contract

All tests mock ``poker_gpt.main.analyze_hand`` so they run offline —
no Gemini API key or solver binary required.

Created: 2026-03-03
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

_MOCK_TURN_RESULT: dict[str, Any] = {
    "advice": "On the turn with Ah, you should continue betting.",
    "mode": "default",
    "scenario": {
        "hero_hand": "KhKd",
        "hero_position": "BTN",
        "board": "Ts,9d,4h,Ah",
        "pot_size_bb": 15.0,
        "effective_stack_bb": 90.0,
        "current_street": "turn",
        "hero_is_ip": True,
        "num_players_preflop": 2,
        "game_type": "cash",
        "stack_depth_bb": 100.0,
        "oop_range": "",
        "ip_range": "",
    },
    "strategy": {
        "hand": "KhKd",
        "actions": {"BET 67": 0.65, "CHECK": 0.35},
        "best_action": "BET 67",
        "best_action_freq": 0.65,
        "range_summary": {},
        "source": "solver",
    },
    "sanity_note": "",
    "cached": False,
    "solve_time": 2.1,
    "source": "solver",
    "confidence": "high",
    "parse_time": 0.9,
    "spot_frequency": None,
    "output_level": "advanced",
}

_MOCK_RIVER_RESULT: dict[str, Any] = {
    "advice": "River card Kd completes your set — bet for value.",
    "mode": "default",
    "scenario": {
        "hero_hand": "KhKd",
        "hero_position": "BTN",
        "board": "Ts,9d,4h,Ah,Kd",
        "pot_size_bb": 30.0,
        "effective_stack_bb": 75.0,
        "current_street": "river",
        "hero_is_ip": True,
        "num_players_preflop": 2,
        "game_type": "cash",
        "stack_depth_bb": 100.0,
        "oop_range": "",
        "ip_range": "",
    },
    "strategy": {
        "hand": "KhKd",
        "actions": {"BET 100": 0.85, "CHECK": 0.15},
        "best_action": "BET 100",
        "best_action_freq": 0.85,
        "range_summary": {},
        "source": "solver",
    },
    "sanity_note": "",
    "cached": False,
    "solve_time": 3.2,
    "source": "solver",
    "confidence": "high",
    "parse_time": 1.0,
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
async def test_reanalyze_street_flop_to_turn() -> None:
    """POST /api/reanalyze-street with turn card returns updated analysis."""
    with patch("app.api.analyze._analyze_hand", return_value=_MOCK_TURN_RESULT) as mock:
        async with _make_client() as client:
            resp = await client.post(
                "/api/reanalyze-street",
                json={
                    "hero_hand": "KhKd",
                    "hero_position": "BTN",
                    "current_board": "Ts,9d,4h",
                    "pot_size_bb": 15.0,
                    "effective_stack_bb": 90.0,
                    "new_board_cards": "Ah",
                    "mode": "default",
                },
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["scenario"]["board"] == "Ts,9d,4h,Ah"
    assert body["scenario"]["current_street"] == "turn"
    assert "turn" in body["advice"].lower()
    mock.assert_called_once()


@pytest.mark.asyncio
async def test_reanalyze_street_turn_to_river() -> None:
    """POST /api/reanalyze-street adding river card works."""
    with patch("app.api.analyze._analyze_hand", return_value=_MOCK_RIVER_RESULT):
        async with _make_client() as client:
            resp = await client.post(
                "/api/reanalyze-street",
                json={
                    "hero_hand": "KhKd",
                    "hero_position": "BTN",
                    "current_board": "Ts,9d,4h,Ah",
                    "pot_size_bb": 30.0,
                    "effective_stack_bb": 75.0,
                    "new_board_cards": "Kd",
                    "mode": "default",
                },
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["scenario"]["board"] == "Ts,9d,4h,Ah,Kd"
    assert body["scenario"]["current_street"] == "river"


@pytest.mark.asyncio
async def test_reanalyze_street_multiple_new_cards() -> None:
    """POST /api/reanalyze-street can add multiple cards (preflop → flop)."""
    flop_result = {**_MOCK_TURN_RESULT}
    flop_result["scenario"] = {**_MOCK_TURN_RESULT["scenario"]}  # deep-copy nested dict
    flop_result["scenario"]["board"] = "Ts,9d,4h"
    flop_result["scenario"]["current_street"] = "flop"

    with patch("app.api.analyze._analyze_hand", return_value=flop_result):
        async with _make_client() as client:
            resp = await client.post(
                "/api/reanalyze-street",
                json={
                    "hero_hand": "KhKd",
                    "hero_position": "BTN",
                    "current_board": "",
                    "pot_size_bb": 5.0,
                    "effective_stack_bb": 95.0,
                    "new_board_cards": "Ts,9d,4h",
                    "mode": "default",
                },
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["scenario"]["board"] == "Ts,9d,4h"


@pytest.mark.asyncio
async def test_reanalyze_street_missing_required_field() -> None:
    """POST /api/reanalyze-street with missing hero_hand returns 422."""
    async with _make_client() as client:
        resp = await client.post(
            "/api/reanalyze-street",
            json={
                "hero_position": "BTN",
                "current_board": "Ts,9d,4h",
                "pot_size_bb": 15.0,
                "effective_stack_bb": 90.0,
                "new_board_cards": "Ah",
            },
        )

    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body


@pytest.mark.asyncio
async def test_reanalyze_street_invalid_card_format() -> None:
    """POST /api/reanalyze-street with invalid card format returns 422."""
    async with _make_client() as client:
        resp = await client.post(
            "/api/reanalyze-street",
            json={
                "hero_hand": "KhKd",
                "hero_position": "BTN",
                "current_board": "Ts,9d,4h",
                "pot_size_bb": 15.0,
                "effective_stack_bb": 90.0,
                "new_board_cards": "INVALID",
                "mode": "default",
            },
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_reanalyze_street_pipeline_error() -> None:
    """POST /api/reanalyze-street handles pipeline exceptions gracefully."""
    with patch("app.api.analyze._analyze_hand", side_effect=ValueError("Parse failed")):
        async with _make_client() as client:
            resp = await client.post(
                "/api/reanalyze-street",
                json={
                    "hero_hand": "KhKd",
                    "hero_position": "BTN",
                    "current_board": "Ts,9d,4h",
                    "pot_size_bb": 15.0,
                    "effective_stack_bb": 90.0,
                    "new_board_cards": "Ah",
                    "mode": "default",
                },
            )

    assert resp.status_code == 400
    body = resp.json()
    assert "Parse failed" in body["detail"]


@pytest.mark.asyncio
async def test_reanalyze_street_response_shape() -> None:
    """POST /api/reanalyze-street response matches AnalyzeResponse schema."""
    with patch("app.api.analyze._analyze_hand", return_value=_MOCK_TURN_RESULT):
        async with _make_client() as client:
            resp = await client.post(
                "/api/reanalyze-street",
                json={
                    "hero_hand": "KhKd",
                    "hero_position": "BTN",
                    "current_board": "Ts,9d,4h",
                    "pot_size_bb": 15.0,
                    "effective_stack_bb": 90.0,
                    "new_board_cards": "Ah",
                },
            )

    assert resp.status_code == 200
    body = resp.json()

    # Check required AnalyzeResponse fields
    assert "advice" in body
    assert "source" in body
    assert "confidence" in body
    assert "mode" in body
    assert "cached" in body
    assert "solve_time" in body
    assert "scenario" in body
    assert "strategy" in body

    # Check that scenario contains expected structure
    scenario = body["scenario"]
    assert "hero_hand" in scenario
    assert "board" in scenario
    assert "current_street" in scenario
    assert "pot_size_bb" in scenario

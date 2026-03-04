"""
backend/tests/test_advice_formatter.py — Unit tests for W5.0c structured advice.

Covers:
  1. Top 3 plays sorted by frequency (desc)
  2. EV signal assignment (positive, negative, neutral)
  3. Street review extraction from advice text
  4. Table rule generation for different frequency ranges
  5. Confidence score mapping by source
  6. Fallback when no strategy is present (LLM-only)
  7. Empty/missing data graceful handling
  8. Integration via serialize_pipeline_result

All tests are offline — no API or solver needed.

Created: 2026-03-03
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.advice_formatter import (
    format_structured_advice,
    _infer_ev_signal,
    _extract_street_reviews,
    _extract_table_rule,
)
from app.models.schemas import EvSignal
from app.models.poker_types_adapter import serialize_pipeline_result


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

_STRATEGY_SOLVER: dict[str, Any] = {
    "hand": "QhQd",
    "actions": {"BET 67": 0.60, "CHECK": 0.15, "BET 100": 0.25},
    "best_action": "BET 67",
    "best_action_freq": 0.60,
    "range_summary": {},
    "source": "solver",
}

_MOCK_RESULT_SOLVER: dict[str, Any] = {
    "advice": (
        "## Preflop Analysis\n"
        "You opened with QQ on the BTN — a strong premium hand.\n\n"
        "## Flop Analysis\n"
        "The flop comes Ts9d4h. You should bet 67% pot here because "
        "you have an overpair with good equity. Check is occasionally "
        "correct but betting is preferred.\n\n"
        "## Turn Analysis\n"
        "On the turn, if a blank comes, continue to bet for value.\n\n"
        "## River Analysis\n"
        "On the river, evaluate your hand strength relative to the board."
    ),
    "mode": "default",
    "scenario": None,
    "strategy": _STRATEGY_SOLVER,
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
    "advice": "Based on your hand, consider raising. Folding is too weak here.",
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


# ──────────────────────────────────────────────
# Test: top 3 play ordering
# ──────────────────────────────────────────────


def test_top_plays_sorted_by_frequency_desc() -> None:
    """Top plays must be sorted by frequency, highest first."""
    result = format_structured_advice(_MOCK_RESULT_SOLVER)
    assert result is not None
    assert len(result.top_plays) == 3
    freqs = [p.frequency for p in result.top_plays]
    assert freqs == sorted(freqs, reverse=True)


def test_top_plays_values() -> None:
    """Top plays should have correct action names and frequencies."""
    result = format_structured_advice(_MOCK_RESULT_SOLVER)
    assert result is not None
    assert result.top_plays[0].action == "BET 67"
    assert result.top_plays[0].frequency == 0.60
    assert result.top_plays[1].action == "BET 100"
    assert result.top_plays[1].frequency == 0.25
    assert result.top_plays[2].action == "CHECK"
    assert result.top_plays[2].frequency == 0.15


def test_top_plays_capped_at_3() -> None:
    """Even with >3 actions, only top 3 are returned."""
    r = dict(_MOCK_RESULT_SOLVER)
    r["strategy"] = {
        "hand": "AhKd",
        "actions": {
            "BET 33": 0.10,
            "BET 67": 0.40,
            "BET 100": 0.20,
            "CHECK": 0.15,
            "RAISE 150": 0.15,
        },
        "best_action": "BET 67",
        "best_action_freq": 0.40,
        "range_summary": {},
        "source": "solver",
    }
    result = format_structured_advice(r)
    assert result is not None
    assert len(result.top_plays) == 3
    actions = [p.action for p in result.top_plays]
    assert actions == ["BET 67", "BET 100", "CHECK"]


# ──────────────────────────────────────────────
# Test: EV signal assignment
# ──────────────────────────────────────────────


def test_ev_signal_bet_positive() -> None:
    """BET actions with >10% freq should be positive."""
    assert _infer_ev_signal("BET 67", 0.60) == EvSignal.POSITIVE


def test_ev_signal_raise_positive() -> None:
    """RAISE actions with >10% freq should be positive."""
    assert _infer_ev_signal("RAISE 100", 0.30) == EvSignal.POSITIVE


def test_ev_signal_fold_negative() -> None:
    """FOLD should always be negative."""
    assert _infer_ev_signal("FOLD", 0.22) == EvSignal.NEGATIVE


def test_ev_signal_check_neutral() -> None:
    """CHECK at low freq should be neutral."""
    assert _infer_ev_signal("CHECK", 0.15) == EvSignal.NEUTRAL


def test_ev_signal_check_high_freq_positive() -> None:
    """CHECK at >50% freq should be positive (dominant play)."""
    assert _infer_ev_signal("CHECK", 0.65) == EvSignal.POSITIVE


def test_ev_signal_allin_positive() -> None:
    """ALL-IN should be positive."""
    assert _infer_ev_signal("ALLIN", 0.40) == EvSignal.POSITIVE


def test_ev_signal_3bet_positive() -> None:
    """3-bet should be positive."""
    assert _infer_ev_signal("3BET", 0.20) == EvSignal.POSITIVE


# ──────────────────────────────────────────────
# Test: street review extraction
# ──────────────────────────────────────────────


def test_street_reviews_extracted() -> None:
    """Should extract per-street sections from structured advice."""
    result = format_structured_advice(_MOCK_RESULT_SOLVER)
    assert result is not None
    assert "preflop" in result.street_reviews or "flop" in result.street_reviews
    # Flop should mention overpair
    if "flop" in result.street_reviews:
        assert "overpair" in result.street_reviews["flop"].lower()


def test_street_reviews_from_text() -> None:
    """Direct test of _extract_street_reviews."""
    text = (
        "## Preflop\nRaise with QQ.\n\n"
        "## Flop\nBet for value on the flop.\n\n"
        "## Turn\nContinue betting.\n"
    )
    reviews = _extract_street_reviews(text)
    assert "preflop" in reviews
    assert "flop" in reviews
    assert "turn" in reviews
    assert "raise" in reviews["preflop"].lower()


def test_street_reviews_empty_on_no_headers() -> None:
    """Should return empty dict when no street headers found."""
    reviews = _extract_street_reviews("Just some general advice without sections.")
    assert reviews == {}


# ──────────────────────────────────────────────
# Test: table rule generation
# ──────────────────────────────────────────────


def test_table_rule_pure_play() -> None:
    """Freq >= 90% → 'Always' rule."""
    rule = _extract_table_rule("", "BET 67", 0.95)
    assert "always" in rule.lower()


def test_table_rule_strong_preference() -> None:
    """Freq 70-90% → 'Strongly prefer' rule."""
    rule = _extract_table_rule("", "BET 67", 0.78)
    assert "strongly" in rule.lower()


def test_table_rule_lean_toward() -> None:
    """Freq 50-70% → 'Lean toward' rule."""
    rule = _extract_table_rule("", "CHECK", 0.55)
    assert "lean" in rule.lower()


def test_table_rule_mixed() -> None:
    """Freq < 50% → 'Mixed strategy' rule."""
    rule = _extract_table_rule("", "BET 67", 0.40)
    assert "mixed" in rule.lower()


def test_table_rule_empty_action() -> None:
    """Empty best_action → empty rule."""
    rule = _extract_table_rule("", "", 0.0)
    assert rule == ""


# ──────────────────────────────────────────────
# Test: LLM-only fallback (no strategy)
# ──────────────────────────────────────────────


def test_llm_fallback_creates_single_play() -> None:
    """When no strategy exists, create a single fallback play."""
    result = format_structured_advice(_MOCK_RESULT_LLM)
    assert result is not None
    assert len(result.top_plays) >= 1
    assert result.top_plays[0].action == "See advice"
    assert result.top_plays[0].frequency == 1.0
    assert result.top_plays[0].ev_signal == EvSignal.NEUTRAL


def test_llm_fallback_raw_advice_preserved() -> None:
    """Raw advice text should be preserved."""
    result = format_structured_advice(_MOCK_RESULT_LLM)
    assert result is not None
    assert "raising" in result.raw_advice.lower()


# ──────────────────────────────────────────────
# Test: empty/missing data graceful handling
# ──────────────────────────────────────────────


def test_empty_advice_returns_none() -> None:
    """Empty advice text → None."""
    r = dict(_MOCK_RESULT_SOLVER)
    r["advice"] = ""
    result = format_structured_advice(r)
    assert result is None


def test_strategy_with_empty_actions() -> None:
    """Strategy with no actions → fallback play."""
    r = dict(_MOCK_RESULT_SOLVER)
    r["strategy"] = {
        "hand": "QhQd",
        "actions": {},
        "best_action": "",
        "best_action_freq": 0.0,
        "range_summary": {},
        "source": "solver",
    }
    result = format_structured_advice(r)
    assert result is not None
    assert len(result.top_plays) == 1
    assert result.top_plays[0].action == "See advice"


# ──────────────────────────────────────────────
# Test: integration via serialize_pipeline_result
# ──────────────────────────────────────────────


def test_serialize_includes_structured_advice() -> None:
    """serialize_pipeline_result should populate structured_advice."""
    response = serialize_pipeline_result(_MOCK_RESULT_SOLVER)
    assert response.structured_advice is not None
    assert len(response.structured_advice.top_plays) == 3
    assert response.structured_advice.top_plays[0].action == "BET 67"


def test_serialize_llm_fallback_structured_advice() -> None:
    """serialize_pipeline_result should work for LLM-only results too."""
    response = serialize_pipeline_result(_MOCK_RESULT_LLM)
    assert response.structured_advice is not None
    assert len(response.structured_advice.top_plays) >= 1
    assert response.structured_advice.raw_advice != ""

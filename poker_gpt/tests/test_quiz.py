"""
test_quiz.py — Tests for the Quiz/Study Mode scoring engine.

Tests cover:
  - Action normalisation (alias resolution, sizing extraction)
  - Scoring rubric (perfect, good, acceptable, incorrect)
  - Mixed strategy handling
  - Edge cases (empty input, unknown actions, no-strategy)
  - QuizScore properties (is_mixed_spot)

Created: 2026-02-28
"""

import pytest

from poker_gpt.quiz import (
    normalise_user_action,
    _extract_sizing,
    score_user_action,
    QuizScore,
)
from poker_gpt.poker_types import StrategyResult


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def pure_bet_strategy():
    """Strategy where BET 67 is overwhelmingly correct (pure strategy)."""
    return StrategyResult(
        hand="QhQd",
        source="solver",
        best_action="BET 67",
        best_action_freq=0.92,
        actions={"BET 67": 0.92, "CHECK": 0.08},
        range_summary={},
    )


@pytest.fixture
def mixed_strategy():
    """Strategy with a genuine mix between BET and CHECK."""
    return StrategyResult(
        hand="AhKd",
        source="solver",
        best_action="BET 33",
        best_action_freq=0.55,
        actions={"BET 33": 0.55, "CHECK": 0.35, "BET 75": 0.10},
        range_summary={},
    )


@pytest.fixture
def fold_or_call_strategy():
    """Strategy mixing FOLD and CALL with no bet/raise."""
    return StrategyResult(
        hand="7h2d",
        source="solver",
        best_action="FOLD",
        best_action_freq=0.70,
        actions={"FOLD": 0.70, "CALL": 0.30},
        range_summary={},
    )


@pytest.fixture
def raise_strategy():
    """Strategy where RAISE is best."""
    return StrategyResult(
        hand="AsAc",
        source="solver",
        best_action="RAISE 100",
        best_action_freq=0.85,
        actions={"RAISE 100": 0.85, "CALL": 0.15},
        range_summary={},
    )


# ──────────────────────────────────────────────
# Action Normalisation
# ──────────────────────────────────────────────

class TestNormaliseUserAction:
    """Tests for normalise_user_action()."""

    def test_fold_basic(self):
        assert normalise_user_action("fold") == "FOLD"

    def test_check_basic(self):
        assert normalise_user_action("check") == "CHECK"

    def test_call_basic(self):
        assert normalise_user_action("call") == "CALL"

    def test_bet_basic(self):
        assert normalise_user_action("bet") == "BET"

    def test_raise_basic(self):
        assert normalise_user_action("raise") == "RAISE"

    def test_bet_with_sizing(self):
        assert normalise_user_action("bet 67") == "BET"

    def test_raise_with_sizing(self):
        assert normalise_user_action("raise 100") == "RAISE"

    def test_all_in_two_words(self):
        assert normalise_user_action("all in") == "ALLIN"

    def test_all_in_hyphen(self):
        assert normalise_user_action("all-in") == "ALLIN"

    def test_shove_alias(self):
        assert normalise_user_action("shove") == "ALLIN"

    def test_jam_alias(self):
        assert normalise_user_action("jam") == "ALLIN"

    def test_muck_alias(self):
        assert normalise_user_action("muck") == "FOLD"

    def test_flat_alias(self):
        assert normalise_user_action("flat") == "CALL"

    def test_x_alias(self):
        assert normalise_user_action("x") == "CHECK"

    def test_3bet_alias(self):
        assert normalise_user_action("3bet") == "RAISE"

    def test_case_insensitive(self):
        assert normalise_user_action("FOLD") == "FOLD"
        assert normalise_user_action("Bet 50") == "BET"
        assert normalise_user_action("CHECK") == "CHECK"

    def test_whitespace_tolerance(self):
        assert normalise_user_action("  bet 67  ") == "BET"
        assert normalise_user_action(" fold ") == "FOLD"

    def test_unknown_action_passthrough(self):
        """Unknown actions are uppercased and returned as-is."""
        assert normalise_user_action("bluff") == "BLUFF"

    def test_bet_with_percent(self):
        assert normalise_user_action("bet 67%") == "BET"


# ──────────────────────────────────────────────
# Sizing Extraction
# ──────────────────────────────────────────────

class TestExtractSizing:
    """Tests for _extract_sizing()."""

    def test_bet_with_number(self):
        assert _extract_sizing("bet 67") == 67

    def test_bet_with_percent(self):
        assert _extract_sizing("bet 33%") == 33

    def test_raise_with_number(self):
        assert _extract_sizing("raise 100") == 100

    def test_no_sizing(self):
        assert _extract_sizing("check") is None

    def test_fold_no_sizing(self):
        assert _extract_sizing("fold") is None


# ──────────────────────────────────────────────
# Scoring — Pure Strategy
# ──────────────────────────────────────────────

class TestScorePureStrategy:
    """Tests for scoring against a clear best action."""

    def test_perfect_match_with_sizing(self, pure_bet_strategy):
        qs = score_user_action("bet 67", pure_bet_strategy)
        assert qs.score == 100
        assert qs.grade == "Perfect"
        assert qs.action_correct is True
        assert qs.user_action == "BET"
        assert qs.user_sizing == 67
        assert qs.sizing_delta == 0

    def test_correct_action_no_sizing(self, pure_bet_strategy):
        qs = score_user_action("bet", pure_bet_strategy)
        assert qs.action_correct is True
        # No sizing to compare — still "correct action root"
        assert qs.score >= 70

    def test_correct_action_wrong_sizing(self, pure_bet_strategy):
        qs = score_user_action("bet 33", pure_bet_strategy)
        assert qs.action_correct is True
        # Sizing delta = abs(33 - 67) = 34, so penalty caps at 30
        assert qs.score >= 70  # max penalty is 30
        assert qs.grade in ("Good", "Perfect")

    def test_wrong_action_low_freq(self, pure_bet_strategy):
        qs = score_user_action("check", pure_bet_strategy)
        assert qs.action_correct is False
        assert qs.gto_freq_of_user_action == pytest.approx(0.08, abs=0.01)
        assert qs.score == 30  # 5-20% freq = 30 points
        assert qs.grade == "Incorrect"

    def test_wrong_action_zero_freq(self, pure_bet_strategy):
        qs = score_user_action("fold", pure_bet_strategy)
        assert qs.action_correct is False
        assert qs.gto_freq_of_user_action == 0.0
        assert qs.score == 0
        assert qs.grade == "Incorrect"


# ──────────────────────────────────────────────
# Scoring — Mixed Strategy
# ──────────────────────────────────────────────

class TestScoreMixedStrategy:
    """Tests for scoring against a mixed strategy."""

    def test_best_action_match(self, mixed_strategy):
        qs = score_user_action("bet 33", mixed_strategy)
        assert qs.action_correct is True
        assert qs.score == 100
        assert qs.grade == "Perfect"

    def test_mixed_alternative_above_20pct(self, mixed_strategy):
        """CHECK is 35% — should score as Acceptable (60)."""
        qs = score_user_action("check", mixed_strategy)
        assert qs.action_correct is False
        assert qs.gto_freq_of_user_action == pytest.approx(0.35, abs=0.01)
        assert qs.score == 60
        assert qs.grade == "Acceptable"

    def test_is_mixed_spot(self, mixed_strategy):
        qs = score_user_action("bet 33", mixed_strategy)
        assert qs.is_mixed_spot is True

    def test_is_not_mixed_spot(self, pure_bet_strategy):
        qs = score_user_action("bet 67", pure_bet_strategy)
        assert qs.is_mixed_spot is False

    def test_minor_mixed_action(self, mixed_strategy):
        """BET 75 is 10% — should score as minor action (30)."""
        qs = score_user_action("bet 75", mixed_strategy)
        # user_action normalises to BET; total BET freq = 0.55 + 0.10 = 0.65
        # Since the root matches the best action root (BET), it's correct
        assert qs.action_correct is True


# ──────────────────────────────────────────────
# Scoring — Fold/Call Strategy
# ──────────────────────────────────────────────

class TestScoreFoldCall:
    """Tests for fold/call spots (no bet/raise sizing)."""

    def test_fold_correct(self, fold_or_call_strategy):
        qs = score_user_action("fold", fold_or_call_strategy)
        assert qs.action_correct is True
        assert qs.score == 100
        assert qs.grade == "Perfect"
        assert qs.sizing_delta is None  # no sizing for fold

    def test_call_alternative(self, fold_or_call_strategy):
        qs = score_user_action("call", fold_or_call_strategy)
        assert qs.action_correct is False
        assert qs.gto_freq_of_user_action == pytest.approx(0.30, abs=0.01)
        assert qs.score == 60
        assert qs.grade == "Acceptable"

    def test_bet_never_done(self, fold_or_call_strategy):
        qs = score_user_action("bet 50", fold_or_call_strategy)
        assert qs.action_correct is False
        assert qs.gto_freq_of_user_action == 0.0
        assert qs.score == 0


# ──────────────────────────────────────────────
# Scoring — Raise Strategy
# ──────────────────────────────────────────────

class TestScoreRaise:
    """Tests for raise action matching."""

    def test_raise_correct_sizing(self, raise_strategy):
        qs = score_user_action("raise 100", raise_strategy)
        assert qs.action_correct is True
        assert qs.score == 100
        assert qs.sizing_delta == 0

    def test_raise_no_sizing(self, raise_strategy):
        qs = score_user_action("raise", raise_strategy)
        assert qs.action_correct is True
        assert qs.score >= 70

    def test_3bet_alias(self, raise_strategy):
        qs = score_user_action("3bet", raise_strategy)
        assert qs.action_correct is True

    def test_call_is_minor_alternative(self, raise_strategy):
        qs = score_user_action("call", raise_strategy)
        assert qs.action_correct is False
        assert qs.gto_freq_of_user_action == pytest.approx(0.15, abs=0.01)
        assert qs.score == 30  # 5-20% freq


# ──────────────────────────────────────────────
# Edge Cases
# ──────────────────────────────────────────────

class TestEdgeCases:
    """Edge case tests for the quiz scoring engine."""

    def test_empty_input(self, pure_bet_strategy):
        """Empty input normalises to empty string → unknown action → 0 score."""
        qs = score_user_action("", pure_bet_strategy)
        assert qs.score == 0
        assert qs.grade == "Incorrect"

    def test_unknown_action(self, pure_bet_strategy):
        """Gibberish input → unknown action → 0 freq → 0 score."""
        qs = score_user_action("asdf123", pure_bet_strategy)
        assert qs.score == 0
        assert qs.grade == "Incorrect"

    def test_quiz_score_fields_populated(self, pure_bet_strategy):
        """Verify all fields in QuizScore are populated."""
        qs = score_user_action("bet 67", pure_bet_strategy)
        assert qs.user_action == "BET"
        assert qs.user_sizing == 67
        assert qs.gto_best_action == "BET 67"
        assert qs.gto_best_freq == pytest.approx(0.92, abs=0.01)
        assert isinstance(qs.gto_actions, dict)
        assert qs.action_correct is True
        assert qs.score >= 0
        assert qs.grade in ("Perfect", "Good", "Acceptable", "Incorrect")

    def test_all_in_scoring(self, pure_bet_strategy):
        """All-in input when GTO says BET → wrong action root."""
        qs = score_user_action("all in", pure_bet_strategy)
        assert qs.user_action == "ALLIN"
        assert qs.action_correct is False

    def test_sizing_close_enough(self, pure_bet_strategy):
        """Sizing within 5 → still Perfect."""
        qs = score_user_action("bet 65", pure_bet_strategy)
        assert qs.action_correct is True
        assert qs.sizing_delta == 2
        assert qs.score == 100
        assert qs.grade == "Perfect"

    def test_sizing_penalty_proportional(self, pure_bet_strategy):
        """Sizing delta > 5 → proportional penalty."""
        qs = score_user_action("bet 50", pure_bet_strategy)
        assert qs.action_correct is True
        assert qs.sizing_delta == 17
        assert qs.score == 100 - 17  # 83
        assert qs.grade == "Good"

    def test_multiple_bet_sizes_aggregation(self, mixed_strategy):
        """When user says 'bet', freq should aggregate all BET sizes."""
        qs = score_user_action("bet", mixed_strategy)
        # BET 33 (0.55) + BET 75 (0.10) = 0.65
        assert qs.gto_freq_of_user_action == pytest.approx(0.65, abs=0.01)
        assert qs.action_correct is True

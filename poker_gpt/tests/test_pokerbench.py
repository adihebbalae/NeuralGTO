"""
test_pokerbench.py — Tests for the PokerBench evaluation framework.

Tests the data loading, parsing, action matching, and metric aggregation
without making any API calls.

Created: 2026-02-27
"""

import pytest

from poker_gpt.evaluation.pokerbench import (
    PBScenario,
    _parse_action,
    _detect_street,
    _parse_scenario,
    action_matches,
    dataset_stats,
)
from poker_gpt.evaluation.evaluator import (
    EvalResult,
    _aggregate,
)


# ---------------------------------------------------------------------------
# Action parsing
# ---------------------------------------------------------------------------

class TestParseAction:
    """Tests for _parse_action."""

    def test_call(self):
        cat, size = _parse_action("call")
        assert cat == "call"
        assert size is None

    def test_fold(self):
        cat, size = _parse_action("fold")
        assert cat == "fold"
        assert size is None

    def test_check(self):
        cat, size = _parse_action("check")
        assert cat == "check"
        assert size is None

    def test_raise_with_amount(self):
        cat, size = _parse_action("raise 11")
        assert cat == "raise"
        assert size == 11.0

    def test_bet_with_amount(self):
        cat, size = _parse_action("bet 4")
        assert cat == "bet"
        assert size == 4.0

    def test_raise_float(self):
        cat, size = _parse_action("raise 3.0")
        assert cat == "raise"
        assert size == 3.0

    def test_empty(self):
        cat, size = _parse_action("")
        assert cat == "unknown"
        assert size is None

    def test_whitespace(self):
        cat, size = _parse_action("  call  ")
        assert cat == "call"
        assert size is None


# ---------------------------------------------------------------------------
# Street detection
# ---------------------------------------------------------------------------

class TestDetectStreet:
    """Tests for _detect_street."""

    def test_preflop_flag(self):
        assert _detect_street("Some text", is_preflop_set=True) == "preflop"

    def test_flop(self):
        text = "The flop comes Ten Of Heart, Three Of Spade, and Two Of Diamond"
        assert _detect_street(text, is_preflop_set=False) == "flop"

    def test_turn(self):
        text = "The flop comes Ks7h2d. The turn comes Jc"
        assert _detect_street(text, is_preflop_set=False) == "turn"

    def test_river(self):
        text = "The flop comes... The turn comes... The river comes 5c"
        assert _detect_street(text, is_preflop_set=False) == "river"

    def test_no_street_markers(self):
        assert _detect_street("Before the flop, UTG raise.", is_preflop_set=False) == "unknown"


# ---------------------------------------------------------------------------
# Scenario parsing
# ---------------------------------------------------------------------------

class TestParseScenario:
    """Tests for _parse_scenario."""

    def test_basic_preflop(self):
        entry = {
            "instruction": (
                "your position is BB, and your holding is "
                "[King of Heart and King of Club]. "
                "the current pot size is 132.0 chips"
            ),
            "output": "call",
        }
        s = _parse_scenario(entry, index=0, is_preflop=True)
        assert s.action_category == "call"
        assert s.street == "preflop"
        assert s.hero_position == "BB"
        assert "King of Heart" in s.hero_holding
        assert s.pot_size == 132.0
        assert s.index == 0

    def test_postflop_raise(self):
        entry = {
            "instruction": (
                "your position is BTN. your holding is [Ace of Spade and King of Heart]. "
                "The flop comes Ten... The turn comes Five. "
                "the current pot size is 20.0 chips"
            ),
            "output": "raise 11",
        }
        s = _parse_scenario(entry, index=5, is_preflop=False)
        assert s.action_category == "raise"
        assert s.bet_size == 11.0
        assert s.street == "turn"
        assert s.hero_position == "BTN"
        assert s.pot_size == 20.0


# ---------------------------------------------------------------------------
# Action matching
# ---------------------------------------------------------------------------

class TestActionMatches:
    """Tests for action_matches."""

    def test_exact_match(self):
        assert action_matches("call", "call") is True
        assert action_matches("fold", "fold") is True
        assert action_matches("check", "check") is True

    def test_case_insensitive(self):
        assert action_matches("Call", "call") is True
        assert action_matches("FOLD", "fold") is True

    def test_bet_raise_equivalent(self):
        assert action_matches("raise", "bet 4") is True
        assert action_matches("bet", "raise 11") is True
        assert action_matches("Raise", "bet 10") is True

    def test_raise_with_amount_ignored(self):
        assert action_matches("raise 15", "raise 11") is True

    def test_mismatch(self):
        assert action_matches("call", "fold") is False
        assert action_matches("check", "raise 11") is False
        assert action_matches("fold", "bet 4") is False

    def test_empty(self):
        assert action_matches("", "call") is False


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

class TestAggregation:
    """Tests for _aggregate."""

    def _make_result(
        self,
        street: str,
        position: str,
        truth: str,
        predicted: str,
        correct: bool,
    ) -> EvalResult:
        scenario = PBScenario(
            instruction="",
            ground_truth=truth,
            action_category=truth.split()[0],
            street=street,
            hero_position=position,
        )
        return EvalResult(
            scenario=scenario,
            predicted_action=predicted.split()[0],
            predicted_raw=predicted,
            correct=correct,
        )

    def test_basic_accuracy(self):
        results = [
            self._make_result("preflop", "BTN", "call", "call", True),
            self._make_result("preflop", "BB", "fold", "fold", True),
            self._make_result("preflop", "CO", "raise", "call", False),
        ]
        report = _aggregate(results, "test", "preflop", 10.0)
        assert report.total == 3
        assert report.correct == 2
        assert abs(report.accuracy - 2 / 3) < 0.01

    def test_by_street(self):
        results = [
            self._make_result("flop", "BTN", "check", "check", True),
            self._make_result("flop", "BTN", "bet", "call", False),
            self._make_result("turn", "BB", "call", "call", True),
        ]
        report = _aggregate(results, "test", "postflop", 5.0)
        assert report.by_street["flop"]["total"] == 2
        assert report.by_street["flop"]["correct"] == 1
        assert report.by_street["turn"]["total"] == 1
        assert report.by_street["turn"]["correct"] == 1

    def test_confusion_matrix(self):
        results = [
            self._make_result("preflop", "BTN", "call", "call", True),
            self._make_result("preflop", "BTN", "call", "fold", False),
            self._make_result("preflop", "BTN", "fold", "fold", True),
        ]
        report = _aggregate(results, "test", "preflop", 3.0)
        assert report.confusion["call"]["call"] == 1
        assert report.confusion["call"]["fold"] == 1
        assert report.confusion["fold"]["fold"] == 1

    def test_summary_runs(self):
        results = [
            self._make_result("preflop", "BTN", "call", "call", True),
        ]
        report = _aggregate(results, "test", "preflop", 1.0)
        summary = report.summary()
        assert "Accuracy" in summary
        assert "100.0%" in summary


# ---------------------------------------------------------------------------
# Dataset stats
# ---------------------------------------------------------------------------

class TestDatasetStats:
    """Tests for dataset_stats."""

    def test_basic_stats(self):
        scenarios = [
            PBScenario(
                instruction="", ground_truth="call",
                action_category="call", street="preflop",
                hero_position="BTN",
            ),
            PBScenario(
                instruction="", ground_truth="fold",
                action_category="fold", street="preflop",
                hero_position="BB",
            ),
        ]
        stats = dataset_stats(scenarios)
        assert stats["total"] == 2
        assert stats["by_street"]["preflop"] == 2
        assert stats["by_action"]["call"] == 1
        assert stats["by_action"]["fold"] == 1

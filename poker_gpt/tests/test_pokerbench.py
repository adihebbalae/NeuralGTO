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
    _holding_nl_to_cards,
    _parse_pb_preflop_actions,
    _snap_to_tree_size,
    _context_snap_size,
    _pb_to_scenario,
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


# ---------------------------------------------------------------------------
# NL holding conversion
# ---------------------------------------------------------------------------

class TestHoldingNlToCards:
    """Tests for _holding_nl_to_cards."""

    def test_pair(self):
        assert _holding_nl_to_cards("King of Heart and King of Club") == "KhKc"

    def test_suited(self):
        assert _holding_nl_to_cards("Ace of Spade and Queen of Spade") == "AsQs"

    def test_offsuit(self):
        assert _holding_nl_to_cards("Jack of Diamond and Ten of Heart") == "JdTh"

    def test_low_cards(self):
        assert _holding_nl_to_cards("Two of Club and Three of Diamond") == "2c3d"

    def test_invalid(self):
        assert _holding_nl_to_cards("not a hand") is None

    def test_single_card(self):
        assert _holding_nl_to_cards("Ace of Spade") is None


# ---------------------------------------------------------------------------
# Size snapping
# ---------------------------------------------------------------------------

class TestSnapToTreeSize:
    """Tests for _snap_to_tree_size (global fallback)."""

    def test_exact_match(self):
        assert _snap_to_tree_size(2.5) == 2.5

    def test_open_2_0_maps_to_2_5(self):
        assert _snap_to_tree_size(2.0) == 2.5

    def test_open_2_3_maps_to_2_5(self):
        assert _snap_to_tree_size(2.3) == 2.5

    def test_sb_open(self):
        assert _snap_to_tree_size(3.0, is_sb_open=True) == 3.0

    def test_3bet_6_5_maps_to_nearest(self):
        # 6.5 is closer to 8.5 than to 3.0
        result = _snap_to_tree_size(6.5)
        assert result in (8.5, 3.0)  # Should be closest

    def test_4bet_24_3(self):
        result = _snap_to_tree_size(24.3)
        assert result == 24.0


class TestContextSnapSize:
    """Tests for _context_snap_size (context-aware sizing)."""

    def test_open_non_sb(self):
        assert _context_snap_size(2.0, "HJ", 1, False, None, None) == 2.5

    def test_open_sb(self):
        assert _context_snap_size(2.5, "SB", 1, False, None, None) == 3.0

    def test_3bet_ip(self):
        # BTN 3-bets vs any open → 8.5
        assert _context_snap_size(9.0, "BTN", 2, False, "HJ", 2.5) == 8.5

    def test_3bet_oop_sb(self):
        # SB 3-bets vs BTN open → 11.0 (not 9.0)
        assert _context_snap_size(9.0, "SB", 2, False, "BTN", 2.5) == 11.0

    def test_3bet_oop_bb_vs_non_sb(self):
        # BB 3-bets vs CO open → 11.0 (not 13.0)
        assert _context_snap_size(13.0, "BB", 2, False, "CO", 2.5) == 11.0

    def test_3bet_bb_vs_sb(self):
        # BB 3-bets vs SB open → 9.0
        assert _context_snap_size(8.0, "BB", 2, False, "SB", 3.0) == 9.0

    def test_squeeze(self):
        # BB raises after open + call → 13.0
        assert _context_snap_size(12.0, "BB", 2, True, "CO", 2.5) == 13.0

    def test_4bet_vs_ip_3bet(self):
        # Opener (UTG) re-raises IP 3-bet (8.5) → 22.0
        assert _context_snap_size(20.0, "UTG", 3, False, "UTG", 8.5) == 22.0

    def test_4bet_vs_oop_3bet(self):
        # Opener (BTN) re-raises OOP 3-bet (11.0) → 24.0
        assert _context_snap_size(22.0, "BTN", 3, False, "BTN", 11.0) == 24.0

    def test_cold_4bet_non_sb(self):
        # CO cold 4-bets (not the opener) → 20.0
        assert _context_snap_size(13.0, "CO", 3, False, "UTG", 8.5) == 20.0

    def test_cold_4bet_sb(self):
        # SB cold 4-bets → 21.0
        assert _context_snap_size(20.0, "SB", 3, False, "UTG", 8.5) == 21.0

    def test_5bet(self):
        # 5-bet → always 25.0
        assert _context_snap_size(30.0, "BB", 4, False, "CO", 22.0) == 25.0


# ---------------------------------------------------------------------------
# Preflop action parsing
# ---------------------------------------------------------------------------

class TestParsePbPreflopActions:
    """Tests for _parse_pb_preflop_actions."""

    def test_no_action(self):
        inst = "Before the flop, there has been no action yet. Now it is your turn."
        entries = _parse_pb_preflop_actions(inst, "SB")
        assert entries == []

    def test_single_raise(self):
        inst = "Before the flop, HJ raise 2.0. Assume that all other players folded."
        entries = _parse_pb_preflop_actions(inst, "CO")
        assert len(entries) == 1
        assert entries[0].position == "HJ"
        assert entries[0].action == "raise"
        assert entries[0].amount_bb == 2.5  # snapped from 2.0

    def test_multiple_actions(self):
        inst = ("Before the flop, HJ raise 2.0, CO call, SB call, "
                "BB raise 15.0. Assume that all other players folded.")
        entries = _parse_pb_preflop_actions(inst, "HJ")
        assert len(entries) == 4
        assert entries[0].position == "HJ"
        assert entries[0].amount_bb == 2.5  # open snapped
        assert entries[1].position == "CO"
        assert entries[1].action == "call"
        assert entries[2].position == "SB"
        assert entries[3].position == "BB"
        assert entries[3].action == "raise"
        assert entries[3].amount_bb == 13.0  # squeeze (callers before)

    def test_allin(self):
        inst = "Before the flop, SB all in. Assume that all others folded."
        entries = _parse_pb_preflop_actions(inst, "BB")
        assert len(entries) == 1
        assert entries[0].action == "allin"

    def test_no_before_the_flop(self):
        inst = "Some random text without the keyword."
        entries = _parse_pb_preflop_actions(inst, "BB")
        assert entries == []


# ---------------------------------------------------------------------------
# PBScenario to ScenarioData conversion
# ---------------------------------------------------------------------------

class TestPbToScenario:
    """Tests for _pb_to_scenario."""

    def test_basic_conversion(self):
        sc = PBScenario(
            instruction=(
                "In this hand, your position is SB, and your holding is "
                "[Ace of Heart and King of Club]. "
                "Before the flop, there has been no action yet. "
                "Assume that all other players folded."
            ),
            ground_truth="raise 3.0",
            action_category="raise",
            bet_size=3.0,
            street="preflop",
            hero_position="SB",
            hero_holding="Ace of Heart and King of Club",
        )
        sd = _pb_to_scenario(sc)
        assert sd is not None
        assert sd.hero_hand == "AhKc"
        assert sd.hero_position == "SB"
        assert sd.current_street == "preflop"
        assert sd.action_history == []

    def test_with_action_history(self):
        sc = PBScenario(
            instruction=(
                "In this hand, your position is BB. "
                "Before the flop, BTN raise 2.0. "
                "Assume that all other players folded."
            ),
            ground_truth="call",
            action_category="call",
            street="preflop",
            hero_position="BB",
            hero_holding="Jack of Diamond and Ten of Diamond",
        )
        sd = _pb_to_scenario(sc)
        assert sd is not None
        assert sd.hero_hand == "JdTd"
        assert len(sd.action_history) == 1
        assert sd.action_history[0].position == "BTN"
        assert sd.action_history[0].amount_bb == 2.5  # snapped

    def test_invalid_holding(self):
        sc = PBScenario(
            instruction="some text",
            ground_truth="fold",
            action_category="fold",
            street="preflop",
            hero_position="BB",
            hero_holding="invalid",
        )
        assert _pb_to_scenario(sc) is None


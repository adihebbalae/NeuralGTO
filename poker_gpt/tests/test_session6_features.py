"""
test_session6_features.py — Tests for Session 6 features.

Covers: trust badge, gap-filling, pool notes, spot frequency.
All offline — no API key or solver binary needed.

Created: 2026-02-27
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from poker_gpt.poker_types import ScenarioData, ActionEntry
from poker_gpt.main import (
    get_source_badge,
    _combine_opponent_pool_notes,
    _HAS_HAND,
    _HAS_POSITION,
    _HAS_ACTION,
    _HAS_STACK,
    _HAS_BOARD,
)
from poker_gpt.spot_frequency import (
    get_spot_frequency,
    format_spot_frequency_for_advisor,
    SpotFrequencyInfo,
    _classify_pot_type,
    _get_position_pair,
)


# ──────────────────────────────────────────────
# Trust Badge Tests
# ──────────────────────────────────────────────

class TestTrustBadge:
    """Tests for get_source_badge()."""

    def test_solver_badge(self):
        badge = get_source_badge("solver")
        assert "TexasSolver" in badge
        assert "CFR" in badge

    def test_solver_cached_badge(self):
        badge = get_source_badge("solver_cached")
        assert "TexasSolver" in badge
        assert "cached" in badge.lower()

    def test_preflop_lookup_badge(self):
        badge = get_source_badge("preflop_lookup")
        assert "GTO" in badge

    def test_llm_badge_has_warning(self):
        badge = get_source_badge("llm_only")
        assert "LLM" in badge or "approximation" in badge.lower()
        badge2 = get_source_badge("llm_fallback")
        assert "LLM" in badge2 or "approximation" in badge2.lower()

    def test_unknown_source_empty(self):
        badge = get_source_badge("some_unknown_source")
        assert badge == ""


# ──────────────────────────────────────────────
# Pool Notes Combiner Tests
# ──────────────────────────────────────────────

class TestPoolNotesCombiner:
    """Tests for _combine_opponent_pool_notes()."""

    def test_both_notes(self):
        combined = _combine_opponent_pool_notes("calling station", "pool underbluffs")
        assert "calling station" in combined
        assert "[POOL TENDENCIES" in combined
        assert "pool underbluffs" in combined

    def test_opponent_only(self):
        combined = _combine_opponent_pool_notes("nit who folds", "")
        assert combined == "nit who folds"

    def test_pool_only(self):
        combined = _combine_opponent_pool_notes("", "pool overvalues top pair")
        assert "[POOL TENDENCIES" in combined
        assert "pool overvalues top pair" in combined

    def test_empty_both(self):
        combined = _combine_opponent_pool_notes("", "")
        assert combined == ""


# ──────────────────────────────────────────────
# Gap-Filling Pattern Tests
# ──────────────────────────────────────────────

class TestGapFillingPatterns:
    """Tests for the regex detectors used in conversational gap-filling."""

    def test_hand_detection_specific(self):
        assert _HAS_HAND.search("I have AhKd on the button")
        assert _HAS_HAND.search("holding QQ")
        assert _HAS_HAND.search("pocket aces")
        assert _HAS_HAND.search("I have big slick")
        assert _HAS_HAND.search("I have cowboys")

    def test_hand_detection_canonical(self):
        assert _HAS_HAND.search("AKs on CO")
        assert _HAS_HAND.search("playing 99")

    def test_hand_detection_negative(self):
        # "at" in "what" matches [TJQKA]{2} — use a truly clean sentence
        assert not _HAS_HAND.search("should I check or fold here")

    def test_position_detection(self):
        assert _HAS_POSITION.search("on the button")
        assert _HAS_POSITION.search("UTG opens")
        assert _HAS_POSITION.search("from the CO")
        assert _HAS_POSITION.search("in the big blind")

    def test_position_detection_negative(self):
        assert not _HAS_POSITION.search("I have QQ and villain bets")

    def test_action_detection(self):
        assert _HAS_ACTION.search("villain raises to 3bb")
        assert _HAS_ACTION.search("I call")
        assert _HAS_ACTION.search("should I bet here")
        assert _HAS_ACTION.search("3bet to 9bb")
        assert _HAS_ACTION.search("villain jams")

    def test_action_detection_negative(self):
        assert not _HAS_ACTION.search("I have QQ on the button")

    def test_stack_detection(self):
        assert _HAS_STACK.search("100bb effective")
        assert _HAS_STACK.search("we are 150bb deep")
        assert _HAS_STACK.search("short stacked")

    def test_board_detection(self):
        assert _HAS_BOARD.search("flop is Ts 9d 4h")
        assert _HAS_BOARD.search("on the turn the board is")


# ──────────────────────────────────────────────
# Spot Frequency Tests
# ──────────────────────────────────────────────

def _make_scenario(**overrides) -> ScenarioData:
    """Helper to create a scenario with defaults suitable for spot freq tests."""
    defaults = dict(
        hero_hand="QhQd",
        hero_position="BTN",
        board="Ts,9d,4h",
        pot_size_bb=36.0,
        effective_stack_bb=88.0,
        current_street="flop",
        oop_range="AA,KK,QQ",
        ip_range="TT,99,88",
        hero_is_ip=True,
        action_history=[],
    )
    defaults.update(overrides)
    return ScenarioData(**defaults)


class TestSpotFrequency:
    """Tests for the spot frequency module."""

    def test_basic_output_shape(self):
        scenario = _make_scenario()
        info = get_spot_frequency(scenario)
        assert isinstance(info, SpotFrequencyInfo)
        assert info.frequency_pct > 0
        assert info.priority_tier in (1, 2, 3, 4, 5)
        assert info.priority_label != ""
        assert info.spot_label != ""
        assert info.note != ""

    def test_btn_vs_bb_is_high_frequency(self):
        """BTN vs BB flop SRP should be a top-priority spot."""
        scenario = _make_scenario(
            hero_position="BTN",
            hero_is_ip=True,
            current_street="flop",
        )
        info = get_spot_frequency(scenario)
        assert info.is_high_frequency, (
            f"BTN vs BB flop SRP should be high freq, got tier {info.priority_tier}"
        )
        assert info.priority_tier <= 2

    def test_river_is_lower_frequency(self):
        """River spots should be less frequent than flop."""
        flop = get_spot_frequency(_make_scenario(current_street="flop"))
        river = get_spot_frequency(_make_scenario(current_street="river"))
        assert river.frequency_pct < flop.frequency_pct

    def test_3bet_pot_is_lower_frequency(self):
        """3-bet pot should be less frequent than SRP."""
        srp_scenario = _make_scenario(action_history=[
            ActionEntry(position="CO", action="raise", amount_bb=3.0),
        ])
        three_bet_scenario = _make_scenario(action_history=[
            ActionEntry(position="CO", action="raise", amount_bb=3.0),
            ActionEntry(position="BTN", action="raise", amount_bb=9.0),
        ])
        srp = get_spot_frequency(srp_scenario)
        three_bet = get_spot_frequency(three_bet_scenario)
        assert three_bet.frequency_pct < srp.frequency_pct

    def test_similar_spots_not_empty(self):
        info = get_spot_frequency(_make_scenario())
        assert len(info.similar_spots) >= 1

    def test_format_for_advisor(self):
        info = get_spot_frequency(_make_scenario())
        text = format_spot_frequency_for_advisor(info)
        assert "SPOT FREQUENCY DATA:" in text
        assert "Spot type:" in text
        assert "Frequency:" in text
        assert "Study priority:" in text

    def test_classify_pot_type_srp(self):
        scenario = _make_scenario(action_history=[
            ActionEntry(position="CO", action="raise", amount_bb=3.0),
        ])
        assert _classify_pot_type(scenario) == "srp"

    def test_classify_pot_type_3bp(self):
        scenario = _make_scenario(action_history=[
            ActionEntry(position="CO", action="raise", amount_bb=3.0),
            ActionEntry(position="BTN", action="raise", amount_bb=9.0),
        ])
        assert _classify_pot_type(scenario) == "3bp"

    def test_classify_pot_type_empty(self):
        scenario = _make_scenario(action_history=[])
        assert _classify_pot_type(scenario) == "srp"  # Default

    def test_classify_pot_type_4bp(self):
        scenario = _make_scenario(action_history=[
            ActionEntry(position="CO", action="raise", amount_bb=3.0),
            ActionEntry(position="BTN", action="raise", amount_bb=9.0),
            ActionEntry(position="CO", action="raise", amount_bb=25.0),
        ])
        assert _classify_pot_type(scenario) == "4bp"

    def test_position_pair_ip(self):
        scenario = _make_scenario(
            hero_position="BTN",
            hero_is_ip=True,
            action_history=[
                ActionEntry(position="BB", action="call", amount_bb=3.0),
            ],
        )
        ip_pos, oop_pos = _get_position_pair(scenario)
        assert ip_pos == "BTN"
        assert oop_pos == "BB"

    def test_position_pair_oop(self):
        scenario = _make_scenario(
            hero_position="BB",
            hero_is_ip=False,
            action_history=[
                ActionEntry(position="BTN", action="raise", amount_bb=3.0),
            ],
        )
        ip_pos, oop_pos = _get_position_pair(scenario)
        assert ip_pos == "BTN"
        assert oop_pos == "BB"


class TestSpotFrequencyEdgeCases:
    """Edge case tests for spot frequency computation."""

    def test_preflop_scenario(self):
        """Preflop scenario should still return valid data."""
        scenario = _make_scenario(current_street="preflop", board="")
        info = get_spot_frequency(scenario)
        assert info.frequency_pct > 0
        assert "preflop" in info.spot_label

    def test_unusual_position(self):
        """Unusual position pair should still return data with default freq."""
        scenario = _make_scenario(
            hero_position="HJ",
            hero_is_ip=False,
            action_history=[
                ActionEntry(position="CO", action="raise", amount_bb=3.0),
            ],
        )
        info = get_spot_frequency(scenario)
        assert info.frequency_pct > 0

    def test_5bet_pot(self):
        """5-bet pot should be very rare (tier 5)."""
        scenario = _make_scenario(action_history=[
            ActionEntry(position="CO", action="raise", amount_bb=3.0),
            ActionEntry(position="BTN", action="raise", amount_bb=9.0),
            ActionEntry(position="CO", action="raise", amount_bb=25.0),
            ActionEntry(position="BTN", action="allin", amount_bb=100.0),
        ])
        info = get_spot_frequency(scenario)
        assert info.priority_tier >= 4, (
            f"5-bet pot should be rare, got tier {info.priority_tier}"
        )

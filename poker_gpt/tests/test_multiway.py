"""
test_multiway.py — Tests for pairwise HU decomposition module.

Tests decomposition logic, HU pair creation, synthesis parsing,
and heuristic fallback. No API calls or solver binary required
(uses mocks for LLM synthesis).

Created: 2026-02-28
"""

import json
from unittest.mock import patch, MagicMock

import pytest

from poker_gpt.poker_types import ScenarioData, StrategyResult, ActionEntry
from poker_gpt.multiway import (
    OpponentInfo,
    PairResult,
    MultiwayResult,
    identify_active_opponents,
    is_multiway,
    create_hu_scenario,
    solve_pairs_preflop,
    _parse_synthesis_response,
    _heuristic_fallback,
    _build_synthesis_context,
    analyze_multiway,
)


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

def _make_scenario(
    hero_pos: str = "BB",
    hero_hand: str = "AhKs",
    actions: list[tuple[str, str, float | None]] | None = None,
    pot: float = 7.5,
) -> ScenarioData:
    """Create a ScenarioData with given preflop action history.

    Args:
        hero_pos: Hero's position.
        hero_hand: Hero's hole cards.
        actions: List of (position, action, amount_bb) tuples.
        pot: Current pot in big blinds.

    Returns:
        ScenarioData for testing.
    """
    history = []
    if actions:
        for pos, action, amt in actions:
            history.append(ActionEntry(
                position=pos,
                action=action,
                amount_bb=amt,
                street="preflop",
            ))

    return ScenarioData(
        hero_hand=hero_hand,
        hero_position=hero_pos,
        board="",
        pot_size_bb=pot,
        effective_stack_bb=100.0,
        current_street="preflop",
        oop_range="",
        ip_range="",
        hero_is_ip=False,
        action_history=history,
    )


def _make_strategy(
    hand: str = "AhKs",
    best_action: str = "Raise 11.0bb",
    freq: float = 0.75,
    actions: dict | None = None,
) -> StrategyResult:
    """Create a StrategyResult for testing."""
    if actions is None:
        actions = {best_action: freq, "Fold": 1.0 - freq}
    return StrategyResult(
        hand=hand,
        actions=actions,
        best_action=best_action,
        best_action_freq=freq,
        source="preflop_lookup",
    )


# ──────────────────────────────────────────────
# identify_active_opponents
# ──────────────────────────────────────────────

class TestIdentifyActiveOpponents:
    """Tests for opponent identification from action history."""

    def test_three_way_open_and_call(self):
        """BTN facing HJ open + CO call → 2 opponents."""
        scenario = _make_scenario(
            hero_pos="BTN",
            actions=[
                ("HJ", "raise", 2.5),
                ("CO", "call", None),
            ],
        )
        opponents = identify_active_opponents(scenario)
        assert len(opponents) == 2
        assert opponents[0].position == "HJ"
        assert opponents[0].role == "opener"
        assert opponents[1].position == "CO"
        assert opponents[1].role == "caller"

    def test_four_way_multiple_callers(self):
        """BB facing UTG open + CO call + SB call → 3 opponents."""
        scenario = _make_scenario(
            hero_pos="BB",
            actions=[
                ("UTG", "raise", 2.5),
                ("CO", "call", None),
                ("SB", "call", None),
            ],
        )
        opponents = identify_active_opponents(scenario)
        assert len(opponents) == 3
        roles = {o.position: o.role for o in opponents}
        assert roles["UTG"] == "opener"
        assert roles["CO"] == "caller"
        assert roles["SB"] == "caller"

    def test_folded_players_excluded(self):
        """Players who folded should not be active."""
        scenario = _make_scenario(
            hero_pos="BB",
            actions=[
                ("UTG", "raise", 2.5),
                ("HJ", "fold", None),
                ("CO", "call", None),
                ("BTN", "fold", None),
                ("SB", "call", None),
            ],
        )
        opponents = identify_active_opponents(scenario)
        positions = [o.position for o in opponents]
        assert "HJ" not in positions
        assert "BTN" not in positions
        assert len(opponents) == 3

    def test_three_bet_pot(self):
        """Hero facing open and 3bet → opener role updates to 3bettor."""
        scenario = _make_scenario(
            hero_pos="BB",
            actions=[
                ("CO", "raise", 2.5),
                ("BTN", "raise", 8.5),
            ],
        )
        opponents = identify_active_opponents(scenario)
        assert len(opponents) == 2
        roles = {o.position: o.role for o in opponents}
        assert roles["CO"] == "opener"
        assert roles["BTN"] == "3bettor"

    def test_hero_prior_action_excluded(self):
        """Hero's own prior actions should not count as opponents."""
        scenario = _make_scenario(
            hero_pos="UTG",
            actions=[
                ("UTG", "raise", 2.5),
                ("CO", "raise", 8.5),
                ("BTN", "call", None),
            ],
        )
        opponents = identify_active_opponents(scenario)
        positions = [o.position for o in opponents]
        assert "UTG" not in positions
        assert len(opponents) == 2

    def test_all_in_opponent(self):
        """All-in opponents should be identified."""
        scenario = _make_scenario(
            hero_pos="BB",
            actions=[
                ("CO", "raise", 2.5),
                ("BTN", "allin", None),
            ],
        )
        opponents = identify_active_opponents(scenario)
        assert len(opponents) == 2
        allin_opp = [o for o in opponents if o.role == "all-in"]
        assert len(allin_opp) == 1
        assert allin_opp[0].position == "BTN"

    def test_heads_up_not_multiway(self):
        """Single opponent → not multi-way."""
        scenario = _make_scenario(
            hero_pos="BB",
            actions=[("BTN", "raise", 2.5)],
        )
        opponents = identify_active_opponents(scenario)
        assert len(opponents) == 1
        assert not is_multiway(scenario)

    def test_no_actions(self):
        """No action history → no opponents."""
        scenario = _make_scenario(hero_pos="BB", actions=[])
        opponents = identify_active_opponents(scenario)
        assert len(opponents) == 0


# ──────────────────────────────────────────────
# is_multiway
# ──────────────────────────────────────────────

class TestIsMultiway:
    """Tests for multi-way detection."""

    def test_three_way_is_multiway(self):
        scenario = _make_scenario(
            hero_pos="BB",
            actions=[
                ("UTG", "raise", 2.5),
                ("CO", "call", None),
            ],
        )
        assert is_multiway(scenario) is True

    def test_heads_up_not_multiway(self):
        scenario = _make_scenario(
            hero_pos="BB",
            actions=[("BTN", "raise", 2.5)],
        )
        assert is_multiway(scenario) is False

    def test_four_way_is_multiway(self):
        scenario = _make_scenario(
            hero_pos="BB",
            actions=[
                ("UTG", "raise", 2.5),
                ("CO", "call", None),
                ("BTN", "call", None),
            ],
        )
        assert is_multiway(scenario) is True


# ──────────────────────────────────────────────
# create_hu_scenario
# ──────────────────────────────────────────────

class TestCreateHUScenario:
    """Tests for HU sub-scenario construction."""

    def test_strips_other_opponents(self):
        """HU scenario should only keep hero and target villain actions."""
        scenario = _make_scenario(
            hero_pos="BB",
            actions=[
                ("UTG", "raise", 2.5),
                ("CO", "call", None),
                ("SB", "call", None),
            ],
        )
        villain = OpponentInfo(position="UTG", role="opener", action="raise", amount_bb=2.5)
        all_opps = identify_active_opponents(scenario)
        hu = create_hu_scenario(scenario, villain, all_opps)

        # Only UTG's raise should remain (CO and SB stripped)
        assert len(hu.action_history) == 1
        assert hu.action_history[0].position == "UTG"
        assert hu.action_history[0].action == "raise"

    def test_preserves_hero_hand(self):
        scenario = _make_scenario(
            hero_pos="BB",
            hero_hand="QhQd",
            actions=[("UTG", "raise", 2.5), ("CO", "call", None)],
        )
        villain = OpponentInfo(position="UTG", role="opener", action="raise", amount_bb=2.5)
        hu = create_hu_scenario(scenario, villain, [])

        assert hu.hero_hand == "QhQd"
        assert hu.hero_position == "BB"
        assert hu.current_street == "preflop"

    def test_keeps_hero_prior_action(self):
        """If hero acted earlier (e.g., opened), keep that in HU history."""
        scenario = _make_scenario(
            hero_pos="UTG",
            actions=[
                ("UTG", "raise", 2.5),
                ("CO", "raise", 8.5),
                ("BTN", "call", None),
            ],
        )
        villain = OpponentInfo(position="CO", role="3bettor", action="raise", amount_bb=8.5)
        hu = create_hu_scenario(scenario, villain, [])

        positions = [e.position for e in hu.action_history]
        assert "UTG" in positions  # Hero's open
        assert "CO" in positions   # Villain's 3bet
        assert "BTN" not in positions  # Stripped


# ──────────────────────────────────────────────
# _parse_synthesis_response
# ──────────────────────────────────────────────

class TestParseSynthesisResponse:
    """Tests for LLM response parsing."""

    def test_valid_json(self):
        raw = '{"action": "raise", "confidence": 0.8, "reasoning": "Premium hand"}'
        result = _parse_synthesis_response(raw)
        assert result["action"] == "raise"
        assert result["confidence"] == 0.8
        assert "Premium" in result["reasoning"]

    def test_json_with_markdown_fences(self):
        raw = '```json\n{"action": "fold", "confidence": 0.9, "reasoning": "Weak holding"}\n```'
        result = _parse_synthesis_response(raw)
        assert result["action"] == "fold"
        assert result["confidence"] == 0.9

    def test_invalid_json_fallback(self):
        raw = "I think you should fold here because multi-way"
        result = _parse_synthesis_response(raw)
        assert result["action"] == "fold"
        assert result["confidence"] < 0.5

    def test_invalid_action_normalized(self):
        raw = '{"action": "Raise to 11bb", "confidence": 0.7, "reasoning": "Strong hand"}'
        result = _parse_synthesis_response(raw)
        assert result["action"] == "raise"

    def test_empty_response(self):
        result = _parse_synthesis_response("")
        assert result["action"] == "fold"
        assert result["confidence"] <= 0.3


# ──────────────────────────────────────────────
# _heuristic_fallback
# ──────────────────────────────────────────────

class TestHeuristicFallback:
    """Tests for heuristic multi-way synthesis without LLM."""

    def test_no_matches_defaults_fold(self):
        scenario = _make_scenario(hero_pos="BB")
        pairs = [
            PairResult(hero_pos="BB", villain_pos="HJ", villain_role="opener", match_type="no_match"),
            PairResult(hero_pos="BB", villain_pos="CO", villain_role="caller", match_type="no_match"),
        ]
        result = _heuristic_fallback(scenario, pairs)
        assert result.action == "fold"
        assert result.synthesis_source == "heuristic"

    def test_pure_fold_hu_stays_fold(self):
        strategy = _make_strategy(best_action="Fold", freq=0.95, actions={"Fold": 0.95, "Call": 0.05})
        pairs = [
            PairResult(
                hero_pos="BB", villain_pos="CO", villain_role="opener",
                strategy=strategy, match_type="simplified",
            ),
            PairResult(hero_pos="BB", villain_pos="BTN", villain_role="caller", match_type="no_match"),
        ]
        result = _heuristic_fallback(_make_scenario(), pairs)
        assert result.action == "fold"

    def test_pure_raise_hu_stays_raise(self):
        strategy = _make_strategy(best_action="Raise 11.0bb", freq=0.90, actions={"Raise 11.0bb": 0.90, "Fold": 0.10})
        pairs = [
            PairResult(
                hero_pos="BB", villain_pos="CO", villain_role="opener",
                strategy=strategy, match_type="simplified",
            ),
        ]
        result = _heuristic_fallback(_make_scenario(), pairs)
        assert result.action == "raise"

    def test_mixed_raise_shifts_to_call_or_fold(self):
        """Mixed raise/fold HU (55% raise / 45% fold) should shift in multi-way."""
        strategy = _make_strategy(
            best_action="Raise 11.0bb", freq=0.55,
            actions={"Raise 11.0bb": 0.55, "Fold": 0.45},
        )
        pairs = [
            PairResult(
                hero_pos="BB", villain_pos="UTG", villain_role="opener",
                strategy=strategy, match_type="simplified",
            ),
            PairResult(hero_pos="BB", villain_pos="CO", villain_role="caller", match_type="no_match"),
        ]
        result = _heuristic_fallback(_make_scenario(), pairs)
        # Multi-way compression: 55% raise HU → should shift to call or fold
        assert result.action in ("call", "fold")


# ──────────────────────────────────────────────
# _build_synthesis_context
# ──────────────────────────────────────────────

class TestBuildSynthesisContext:
    """Tests for LLM context string construction."""

    def test_includes_hero_info(self):
        scenario = _make_scenario(
            hero_pos="BB", hero_hand="AhKs",
            actions=[("UTG", "raise", 2.5), ("CO", "call", None)],
        )
        pairs = [
            PairResult(hero_pos="BB", villain_pos="UTG", villain_role="opener", match_type="no_match"),
        ]
        context = _build_synthesis_context(scenario, pairs)
        assert "BB" in context
        assert "AhKs" in context
        assert "UTG" in context

    def test_includes_strategy_data(self):
        strategy = _make_strategy(best_action="Raise 11.0bb", freq=0.75)
        pairs = [
            PairResult(
                hero_pos="BB", villain_pos="UTG", villain_role="opener",
                strategy=strategy, match_type="simplified",
            ),
        ]
        context = _build_synthesis_context(_make_scenario(), pairs)
        assert "Raise 11.0bb" in context
        assert "75%" in context


# ──────────────────────────────────────────────
# analyze_multiway (end-to-end with mocks)
# ──────────────────────────────────────────────

class TestAnalyzeMultiway:
    """End-to-end tests with mocked components."""

    @patch("poker_gpt.multiway.lookup_preflop_strategy")
    def test_not_multiway_uses_direct_lookup(self, mock_lookup):
        """Single-opponent scenario should attempt direct lookup."""
        strategy = _make_strategy()
        mock_lookup.return_value = strategy

        scenario = _make_scenario(
            hero_pos="BB",
            actions=[("BTN", "raise", 2.5)],
        )
        result = analyze_multiway(scenario, use_llm=False)

        assert result.synthesis_source == "single_lookup"
        assert "raise" in result.action.lower()

    @patch("poker_gpt.multiway.lookup_preflop_strategy")
    def test_multiway_heuristic_fallback(self, mock_lookup):
        """Multi-way with no LLM should use heuristic."""
        # Return a strategy for direct lookup, None for simplified
        mock_lookup.side_effect = [
            None,  # direct lookup for full scenario
            _make_strategy(best_action="Fold", freq=0.95, actions={"Fold": 0.95, "Call": 0.05}),
            None,  # second pair (simplified, also fails)
            None,  # opener minimal
            None,  # caller simplified
        ]

        scenario = _make_scenario(
            hero_pos="BB",
            actions=[
                ("UTG", "raise", 2.5),
                ("CO", "call", None),
            ],
        )
        result = analyze_multiway(scenario, use_llm=False)

        assert result.num_opponents == 2
        assert result.synthesis_source == "heuristic"
        assert result.action in ("fold", "call", "raise", "check")

    @patch("poker_gpt.multiway.lookup_preflop_strategy")
    def test_multiway_all_no_match(self, mock_lookup):
        """When all lookups fail, heuristic defaults to fold."""
        mock_lookup.return_value = None

        scenario = _make_scenario(
            hero_pos="BB",
            actions=[
                ("UTG", "raise", 2.5),
                ("CO", "call", None),
                ("BTN", "call", None),
            ],
        )
        result = analyze_multiway(scenario, use_llm=False)

        assert result.action == "fold"
        assert result.confidence <= 0.4


# ──────────────────────────────────────────────
# Regression: data structure integrity
# ──────────────────────────────────────────────

class TestDataStructures:
    """Verify dataclass defaults and field types."""

    def test_opponent_info_fields(self):
        opp = OpponentInfo(position="CO", role="opener", action="raise", amount_bb=2.5)
        assert opp.position == "CO"
        assert opp.amount_bb == 2.5

    def test_pair_result_defaults(self):
        pr = PairResult(hero_pos="BB", villain_pos="CO", villain_role="opener")
        assert pr.strategy is None
        assert pr.match_type == "no_match"

    def test_multiway_result_defaults(self):
        mr = MultiwayResult()
        assert mr.action == ""
        assert mr.pair_results == []
        assert mr.num_opponents == 0
        assert mr.synthesis_source == "llm"

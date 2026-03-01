"""
test_llm_pruner.py — Offline unit tests for the LLM pruner module (T4.2a).

Tests PruningDecision dataclass, JSON response parsing, threshold pruning,
failure handling, and edge cases. No API calls, no solver binary needed.

Created: 2026-02-28
Task: T4.2a

Usage:
    python -m pytest poker_gpt/tests/test_llm_pruner.py -v
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from poker_gpt.poker_types import PruningDecision
from poker_gpt.llm_pruner import (
    parse_pruning_response,
    threshold_prune,
    action_to_bet_size_pct,
    keep_actions_to_bet_sizes,
    _build_pruning_prompt,
)


# ──────────────────────────────────────────────
# PruningDecision dataclass tests
# ──────────────────────────────────────────────

class TestPruningDecision:
    """Tests for the PruningDecision dataclass."""

    def test_basic_creation(self):
        """PruningDecision can be created with required fields."""
        pd = PruningDecision(
            keep_sizes=["CHECK", "BET 67"],
            prune_sizes=["BET 33", "BET 100"],
            reasoning="Low SPR spot, small and large bets are suboptimal.",
        )
        assert pd.keep_sizes == ["CHECK", "BET 67"]
        assert pd.prune_sizes == ["BET 33", "BET 100"]
        assert "Low SPR" in pd.reasoning

    def test_defaults(self):
        """PruningDecision has correct default values."""
        pd = PruningDecision(
            keep_sizes=["CHECK"],
            prune_sizes=[],
            reasoning="No pruning needed.",
        )
        assert pd.warm_iterations == 0
        assert pd.board == ""

    def test_with_metadata(self):
        """PruningDecision stores metadata fields correctly."""
        pd = PruningDecision(
            keep_sizes=["CHECK", "BET 67"],
            prune_sizes=["BET 150"],
            reasoning="Overbet rarely used on dry board.",
            warm_iterations=20,
            board="Kc,Qc,2h",
        )
        assert pd.warm_iterations == 20
        assert pd.board == "Kc,Qc,2h"

    def test_empty_prune_list(self):
        """PruningDecision works with empty prune list."""
        pd = PruningDecision(
            keep_sizes=["CHECK", "BET 33", "BET 67", "BET 100"],
            prune_sizes=[],
            reasoning="All actions needed.",
        )
        assert len(pd.prune_sizes) == 0
        assert len(pd.keep_sizes) == 4


# ──────────────────────────────────────────────
# parse_pruning_response tests
# ──────────────────────────────────────────────

class TestParsePruningResponse:
    """Tests for JSON response parsing from LLM."""

    def test_valid_json(self):
        """Parse a clean JSON response."""
        response = json.dumps({
            "keep": ["CHECK", "BET 67"],
            "prune": ["BET 33", "BET 100"],
            "reasoning": "Dry board favors medium sizing.",
        })
        result = parse_pruning_response(response)
        assert result is not None
        assert result.keep_sizes == ["CHECK", "BET 67"]
        assert result.prune_sizes == ["BET 33", "BET 100"]
        assert "Dry board" in result.reasoning

    def test_json_with_markdown_fences(self):
        """Parse JSON wrapped in markdown code fences."""
        response = '```json\n{"keep": ["CHECK", "BET 67"], "prune": ["BET 33"], "reasoning": "test"}\n```'
        result = parse_pruning_response(response)
        assert result is not None
        assert result.keep_sizes == ["CHECK", "BET 67"]

    def test_json_with_plain_fences(self):
        """Parse JSON wrapped in plain markdown fences (no language tag)."""
        response = '```\n{"keep": ["CHECK"], "prune": [], "reasoning": "no prune"}\n```'
        result = parse_pruning_response(response)
        assert result is not None
        assert result.keep_sizes == ["CHECK"]

    def test_extra_whitespace(self):
        """Parse JSON with leading/trailing whitespace."""
        response = '  \n  {"keep": ["CHECK"], "prune": ["BET 33"], "reasoning": "ok"}  \n  '
        result = parse_pruning_response(response)
        assert result is not None

    def test_metadata_passthrough(self):
        """Metadata (warm_iterations, board) passes through to result."""
        response = json.dumps({
            "keep": ["CHECK", "BET 67"],
            "prune": [],
            "reasoning": "ok",
        })
        result = parse_pruning_response(
            response, warm_iterations=20, board="Ac,9h,3d"
        )
        assert result is not None
        assert result.warm_iterations == 20
        assert result.board == "Ac,9h,3d"

    def test_invalid_json_returns_none(self):
        """Malformed JSON returns None."""
        result = parse_pruning_response("this is not json at all")
        assert result is None

    def test_empty_string_returns_none(self):
        """Empty string returns None."""
        result = parse_pruning_response("")
        assert result is None

    def test_missing_keep_field(self):
        """JSON without 'keep' field returns None (empty keep list)."""
        response = json.dumps({"prune": ["BET 33"], "reasoning": "test"})
        result = parse_pruning_response(response)
        assert result is None  # Empty keep list is rejected

    def test_empty_keep_list_returns_none(self):
        """Empty 'keep' list is rejected as invalid."""
        response = json.dumps({"keep": [], "prune": ["BET 33"], "reasoning": "x"})
        result = parse_pruning_response(response)
        assert result is None

    def test_non_list_keep_returns_none(self):
        """Non-list 'keep' value returns None."""
        response = json.dumps({"keep": "CHECK", "prune": [], "reasoning": "x"})
        result = parse_pruning_response(response)
        assert result is None

    def test_non_list_prune_returns_none(self):
        """Non-list 'prune' value returns None."""
        response = json.dumps({"keep": ["CHECK"], "prune": "BET 33", "reasoning": "x"})
        result = parse_pruning_response(response)
        assert result is None

    def test_missing_reasoning_uses_empty(self):
        """Missing 'reasoning' field defaults to empty string."""
        response = json.dumps({"keep": ["CHECK"], "prune": []})
        result = parse_pruning_response(response)
        assert result is not None
        assert result.reasoning == ""


# ──────────────────────────────────────────────
# threshold_prune tests
# ──────────────────────────────────────────────

class TestThresholdPrune:
    """Tests for the rule-based threshold pruning baseline."""

    def test_basic_pruning(self):
        """Actions below threshold are pruned."""
        freqs = {"CHECK": 0.35, "BET 33": 0.25, "BET 67": 0.30, "BET 100": 0.03}
        result = threshold_prune(freqs, threshold=0.05)
        assert "BET 100" in result.prune_sizes
        assert "CHECK" in result.keep_sizes
        assert "BET 33" in result.keep_sizes
        assert "BET 67" in result.keep_sizes

    def test_check_always_kept(self):
        """CHECK is kept even if frequency is below threshold."""
        freqs = {"CHECK": 0.01, "BET 33": 0.50, "BET 67": 0.49}
        result = threshold_prune(freqs, threshold=0.05)
        assert "CHECK" in result.keep_sizes

    def test_no_pruning_needed(self):
        """All actions above threshold → nothing pruned."""
        freqs = {"CHECK": 0.40, "BET 67": 0.60}
        result = threshold_prune(freqs, threshold=0.05)
        assert len(result.prune_sizes) == 0
        assert len(result.keep_sizes) == 2

    def test_all_below_threshold_keeps_best(self):
        """If all non-CHECK actions are below threshold, keep the best one."""
        freqs = {"CHECK": 0.90, "BET 33": 0.04, "BET 67": 0.03, "BET 100": 0.03}
        result = threshold_prune(freqs, threshold=0.05)
        # BET 33 has highest frequency among pruned, should be rescued
        assert "BET 33" in result.keep_sizes
        assert "CHECK" in result.keep_sizes

    def test_custom_threshold(self):
        """Custom threshold value is respected."""
        freqs = {"CHECK": 0.50, "BET 33": 0.08, "BET 67": 0.42}
        result = threshold_prune(freqs, threshold=0.10)
        assert "BET 33" in result.prune_sizes
        assert "BET 67" in result.keep_sizes

    def test_reasoning_mentions_threshold(self):
        """Reasoning string mentions the threshold value."""
        freqs = {"CHECK": 0.50, "BET 67": 0.50}
        result = threshold_prune(freqs, threshold=0.05)
        assert "5%" in result.reasoning

    def test_returns_pruning_decision_type(self):
        """Returns a PruningDecision instance."""
        freqs = {"CHECK": 0.50, "BET 67": 0.50}
        result = threshold_prune(freqs, threshold=0.05)
        assert isinstance(result, PruningDecision)


# ──────────────────────────────────────────────
# action_to_bet_size_pct tests
# ──────────────────────────────────────────────

class TestActionToBetSizePct:
    """Tests for extracting bet size percentages from action names."""

    def test_bet_33(self):
        assert action_to_bet_size_pct("BET 33") == 33

    def test_bet_67(self):
        assert action_to_bet_size_pct("BET 67") == 67

    def test_bet_100(self):
        assert action_to_bet_size_pct("BET 100") == 100

    def test_bet_150(self):
        assert action_to_bet_size_pct("BET 150") == 150

    def test_check_returns_none(self):
        assert action_to_bet_size_pct("CHECK") is None

    def test_fold_returns_none(self):
        assert action_to_bet_size_pct("FOLD") is None

    def test_lowercase_works(self):
        assert action_to_bet_size_pct("bet 67") == 67

    def test_empty_string(self):
        assert action_to_bet_size_pct("") is None

    def test_bet_no_number(self):
        assert action_to_bet_size_pct("BET") is None

    def test_bet_non_numeric(self):
        assert action_to_bet_size_pct("BET abc") is None


# ──────────────────────────────────────────────
# keep_actions_to_bet_sizes tests
# ──────────────────────────────────────────────

class TestKeepActionsToBetSizes:
    """Tests for converting keep action lists to bet size percentages."""

    def test_mixed_actions(self):
        """Extracts bet sizes, ignores non-bet actions."""
        sizes = keep_actions_to_bet_sizes(["CHECK", "BET 33", "BET 67"])
        assert sizes == [33, 67]

    def test_no_bets(self):
        """All non-bet actions returns empty list."""
        sizes = keep_actions_to_bet_sizes(["CHECK", "FOLD"])
        assert sizes == []

    def test_all_bets(self):
        """All bet actions are converted."""
        sizes = keep_actions_to_bet_sizes(["BET 33", "BET 67", "BET 100"])
        assert sizes == [33, 67, 100]

    def test_empty_list(self):
        """Empty input returns empty output."""
        sizes = keep_actions_to_bet_sizes([])
        assert sizes == []


# ──────────────────────────────────────────────
# _build_pruning_prompt tests
# ──────────────────────────────────────────────

class TestBuildPruningPrompt:
    """Tests for the prompt builder."""

    def test_contains_board(self):
        """Prompt includes the board string."""
        prompt = _build_pruning_prompt(
            action_frequencies={"CHECK": 0.50, "BET 67": 0.50},
            board="Kc,Qc,2h",
            position_ip="BTN",
            position_oop="BB",
            effective_stack_bb=100.0,
            pot_size_bb=6.0,
            warm_iterations=20,
        )
        assert "Kc,Qc,2h" in prompt

    def test_contains_positions(self):
        """Prompt includes position labels."""
        prompt = _build_pruning_prompt(
            action_frequencies={"CHECK": 0.50},
            board="Ac,9h,3d",
            position_ip="CO",
            position_oop="BB",
            effective_stack_bb=100.0,
            pot_size_bb=6.0,
            warm_iterations=20,
        )
        assert "CO" in prompt
        assert "BB" in prompt

    def test_contains_spr(self):
        """Prompt includes computed SPR."""
        prompt = _build_pruning_prompt(
            action_frequencies={"CHECK": 0.50},
            board="Ac,9h,3d",
            position_ip="BTN",
            position_oop="BB",
            effective_stack_bb=100.0,
            pot_size_bb=10.0,
            warm_iterations=20,
        )
        assert "SPR: 10.0" in prompt

    def test_contains_frequencies(self):
        """Prompt includes action frequency data."""
        prompt = _build_pruning_prompt(
            action_frequencies={"CHECK": 0.35, "BET 67": 0.65},
            board="Ts,9d,4h",
            position_ip="BTN",
            position_oop="BB",
            effective_stack_bb=100.0,
            pot_size_bb=6.0,
            warm_iterations=20,
        )
        assert "CHECK" in prompt
        assert "BET 67" in prompt
        assert "35" in prompt  # 35% frequency

    def test_contains_iteration_count(self):
        """Prompt mentions the warm-up iteration count."""
        prompt = _build_pruning_prompt(
            action_frequencies={"CHECK": 0.50},
            board="Ac,9h,3d",
            position_ip="BTN",
            position_oop="BB",
            effective_stack_bb=100.0,
            pot_size_bb=6.0,
            warm_iterations=50,
        )
        assert "50" in prompt

    def test_zero_pot_no_crash(self):
        """Zero pot doesn't crash (SPR division by zero handled)."""
        prompt = _build_pruning_prompt(
            action_frequencies={"CHECK": 1.0},
            board="Ac,9h,3d",
            position_ip="BTN",
            position_oop="BB",
            effective_stack_bb=100.0,
            pot_size_bb=0.0,
            warm_iterations=20,
        )
        assert "SPR: 0" in prompt


# ──────────────────────────────────────────────
# Edge cases / failure handling
# ──────────────────────────────────────────────

class TestEdgeCases:
    """Edge case and failure mode tests."""

    def test_single_action_strategy(self):
        """Threshold prune with only one action keeps it."""
        freqs = {"CHECK": 1.0}
        result = threshold_prune(freqs, threshold=0.05)
        assert "CHECK" in result.keep_sizes
        assert len(result.prune_sizes) == 0

    def test_threshold_prune_empty_input(self):
        """Empty frequency dict returns empty keep/prune."""
        result = threshold_prune({}, threshold=0.05)
        assert result.keep_sizes == []
        assert result.prune_sizes == []

    def test_parse_response_with_extra_fields(self):
        """Extra fields in JSON are ignored."""
        response = json.dumps({
            "keep": ["CHECK", "BET 67"],
            "prune": ["BET 33"],
            "reasoning": "test",
            "confidence": 0.9,  # Extra field
        })
        result = parse_pruning_response(response)
        assert result is not None
        assert result.keep_sizes == ["CHECK", "BET 67"]

    def test_parse_response_nested_json(self):
        """Deeply nested/weird JSON returns None (missing required structure)."""
        response = json.dumps({"data": {"keep": ["CHECK"]}})
        result = parse_pruning_response(response)
        assert result is None  # No top-level 'keep' with items

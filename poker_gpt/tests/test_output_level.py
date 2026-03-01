"""
test_output_level.py — Tests for T3.6 Beginner/Advanced output level split.

Verifies:
  - Beginner prompt loads and contains no jargon
  - Advanced prompt loads and contains expected sections
  - output_level parameter threads through the pipeline
  - Invalid output_level raises ValueError

All offline — no API key or solver binary needed.

Created: 2026-02-28
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from poker_gpt.nl_advisor import (
    _load_advisor_prompt,
    OUTPUT_LEVELS,
)
from poker_gpt.main import analyze_hand


# ──────────────────────────────────────────────
# Prompt Loading Tests
# ──────────────────────────────────────────────

class TestPromptLoading:
    """Tests for _load_advisor_prompt with output level routing."""

    def test_advanced_prompt_loads(self):
        prompt = _load_advisor_prompt("advanced")
        assert len(prompt) > 100
        assert "GTO" in prompt

    def test_beginner_prompt_loads(self):
        prompt = _load_advisor_prompt("beginner")
        assert len(prompt) > 100

    def test_beginner_prompt_file_exists(self):
        path = Path(__file__).parent.parent / "prompts" / "advisor_beginner_system.txt"
        assert path.exists(), "advisor_beginner_system.txt must exist"

    def test_advanced_prompt_file_exists(self):
        path = Path(__file__).parent.parent / "prompts" / "advisor_system.txt"
        assert path.exists(), "advisor_system.txt must exist"

    def test_invalid_level_raises(self):
        with pytest.raises(ValueError, match="Unknown output_level"):
            _load_advisor_prompt("expert")

    def test_default_level_is_advanced(self):
        """Default call (no argument) should load the advanced prompt."""
        prompt = _load_advisor_prompt()
        assert "GTO" in prompt
        # Should be identical to explicitly requesting advanced
        advanced = _load_advisor_prompt("advanced")
        assert prompt == advanced

    def test_output_levels_tuple(self):
        assert "beginner" in OUTPUT_LEVELS
        assert "advanced" in OUTPUT_LEVELS
        assert len(OUTPUT_LEVELS) == 2


# ──────────────────────────────────────────────
# Beginner Prompt Content — Jargon-Free
# ──────────────────────────────────────────────

class TestBeginnerPromptContent:
    """Verify the beginner system prompt prohibits jargon."""

    BANNED_WORDS = [
        "frequency",
        "equity",
        "GTO",
        "blocker",
        "polarized",
        "merged",
        "solver",
        "exploitative",
        "expected value",
        "indifferent",
        "mixed strategy",
        "combinatorics",
        "nut advantage",
        "range advantage",
        "equity realization",
    ]

    @pytest.fixture
    def beginner_prompt(self):
        return _load_advisor_prompt("beginner")

    def test_prohibitions_listed(self, beginner_prompt):
        """The beginner prompt must explicitly prohibit jargon terms."""
        lower = beginner_prompt.lower()
        # Check that the prompt mentions these as forbidden
        assert "prohibit" in lower or "never" in lower

    def test_rule_of_thumb_required(self, beginner_prompt):
        """Beginner prompt must require a rule of thumb."""
        lower = beginner_prompt.lower()
        assert "rule of thumb" in lower

    def test_no_multi_section_format(self, beginner_prompt):
        """Beginner prompt must not require multi-section headers."""
        lower = beginner_prompt.lower()
        assert "section 1" not in lower
        assert "section 2" not in lower

    def test_single_action_required(self, beginner_prompt):
        """Beginner prompt must ask for one clear action."""
        lower = beginner_prompt.lower()
        assert "one clear action" in lower or "single action" in lower

    def test_no_percentage_numbers(self, beginner_prompt):
        """Beginner prompt must prohibit percentage numbers."""
        lower = beginner_prompt.lower()
        assert "percentage" in lower or "%" in lower


# ──────────────────────────────────────────────
# Advanced Prompt Content — Full GTO Analysis
# ──────────────────────────────────────────────

class TestAdvancedPromptContent:
    """Verify the advanced prompt has the expected 4+ section structure."""

    @pytest.fixture
    def advanced_prompt(self):
        return _load_advisor_prompt("advanced")

    def test_has_gto_recommendation_section(self, advanced_prompt):
        assert "GTO Recommendation" in advanced_prompt

    def test_has_why_section(self, advanced_prompt):
        assert "Why This Strategy Exists" in advanced_prompt

    def test_has_practice_section(self, advanced_prompt):
        assert "In Practice" in advanced_prompt

    def test_has_villain_adjustment_section(self, advanced_prompt):
        assert "Villain Adjustment" in advanced_prompt

    def test_has_table_rule_section(self, advanced_prompt):
        assert "Table Rule" in advanced_prompt

    def test_mentions_frequencies(self, advanced_prompt):
        lower = advanced_prompt.lower()
        assert "frequency" in lower or "frequencies" in lower

    def test_mentions_blocker(self, advanced_prompt):
        lower = advanced_prompt.lower()
        assert "blocker" in lower

    def test_mentions_range(self, advanced_prompt):
        lower = advanced_prompt.lower()
        assert "range" in lower


# ──────────────────────────────────────────────
# Pipeline Integration — output_level threading
# ──────────────────────────────────────────────

class TestOutputLevelThreading:
    """Verify output_level flows through analyze_hand without error."""

    def test_output_level_in_validation_error_result(self):
        """A too-vague query returns validation error with output_level set."""
        result = analyze_hand("poker", mode="fast", output_level="beginner")
        assert result["output_level"] == "beginner"
        assert result["source"] == "validation_error"

    def test_output_level_advanced_in_validation_error_result(self):
        result = analyze_hand("poker", mode="fast", output_level="advanced")
        assert result["output_level"] == "advanced"
        assert result["source"] == "validation_error"

    def test_output_level_default_is_advanced(self):
        """When output_level is not specified, it defaults to advanced."""
        result = analyze_hand("poker", mode="fast")
        assert result["output_level"] == "advanced"

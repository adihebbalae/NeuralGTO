"""
test_pipeline.py — Tests for the PokerGPT pipeline.

Tests each component independently and the full pipeline integration.
Can be run without a Gemini API key for the offline tests.

Created: 2026-02-06
Updated: 2026-02-06 — Replaced OpenAI with Google Gemini

DOCUMENTATION:
Usage:
    # Run all tests (offline tests only, no API key needed):
    python -m poker_gpt.tests.test_pipeline

    # Run with API tests (needs GEMINI_API_KEY in .env):
    python -m poker_gpt.tests.test_pipeline --with-api
"""

import json
import sys
import os
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from poker_gpt.poker_types import ScenarioData, StrategyResult, ActionEntry
from poker_gpt.range_utils import (
    hand_to_solver_combos,
    normalize_hand_for_lookup,
    get_position_relative,
    is_valid_card,
)
from poker_gpt.solver_input import generate_solver_input
from poker_gpt.strategy_extractor import extract_strategy
from poker_gpt.validation import validate_scenario
from poker_gpt import config


def test_hand_combos():
    """Test hand_to_solver_combos."""
    print("Testing hand_to_solver_combos...")
    
    # Pairs
    qq = hand_to_solver_combos("QQ")
    assert len(qq) == 6, f"QQ should have 6 combos, got {len(qq)}"
    assert "QhQd" in qq
    print(f"  ✓ QQ → {len(qq)} combos: {qq[:3]}...")
    
    # Suited hands
    aks = hand_to_solver_combos("AKs")
    assert len(aks) == 4, f"AKs should have 4 combos, got {len(aks)}"
    print(f"  ✓ AKs → {len(aks)} combos: {aks[:3]}...")
    
    # Offsuit hands
    ako = hand_to_solver_combos("AKo")
    assert len(ako) == 12, f"AKo should have 12 combos, got {len(ako)}"
    print(f"  ✓ AKo → {len(ako)} combos: {ako[:3]}...")
    
    # Specific hand
    specific = hand_to_solver_combos("QhQd")
    assert specific == ["QhQd"]
    print(f"  ✓ QhQd → {specific}")


def test_card_validation():
    """Test is_valid_card."""
    print("Testing is_valid_card...")
    assert is_valid_card("Qh") == True
    assert is_valid_card("Ts") == True
    assert is_valid_card("2c") == True
    assert is_valid_card("Xx") == False
    assert is_valid_card("Q") == False
    print("  ✓ All card validations passed")


def test_position_logic():
    """Test IP/OOP determination."""
    print("Testing get_position_relative...")
    
    # BTN vs BB: BTN is IP
    hero_ip, oop, ip = get_position_relative("BTN", "BB")
    assert hero_ip == True, "BTN should be IP vs BB"
    assert ip == "BTN"
    assert oop == "BB"
    print(f"  ✓ BTN vs BB: BTN is IP")
    
    # BB vs CO: CO is IP
    hero_ip, oop, ip = get_position_relative("BB", "CO")
    assert hero_ip == False, "BB should be OOP vs CO"
    print(f"  ✓ BB vs CO: BB is OOP")
    
    # UTG vs BTN: BTN is IP
    hero_ip, oop, ip = get_position_relative("UTG", "BTN")
    assert hero_ip == False, "UTG should be OOP vs BTN"
    print(f"  ✓ UTG vs BTN: UTG is OOP")


def test_normalize_hand():
    """Test hand normalization for lookup."""
    print("Testing normalize_hand_for_lookup...")
    assert normalize_hand_for_lookup("Qh", "Qd") == "QhQd"
    assert normalize_hand_for_lookup("Kd", "Ah") == "AhKd"  # A is higher
    assert normalize_hand_for_lookup("2s", "Ah") == "Ah2s"
    print("  ✓ All normalizations passed")


def test_solver_input_generation():
    """Test generating solver input file."""
    print("Testing solver input generation...")
    
    config.ensure_work_dir()
    
    scenario = ScenarioData(
        hero_hand="QhQd",
        hero_position="BTN",
        board="Ts,9d,4h",
        pot_size_bb=36.0,
        effective_stack_bb=88.0,
        current_street="flop",
        oop_range="AA,KK,QQ,JJ,TT,99,AKs,AQs,AJs",
        ip_range="TT,99,88,77,AKs,AQs,KQs,QJs,JTs",
        hero_is_ip=True,
        action_history=[],
    )
    
    output_path = config.WORK_DIR / "test_solver_input.txt"
    result_path = generate_solver_input(scenario, output_path)
    
    assert result_path.exists(), f"Output file not created: {result_path}"
    
    with open(result_path) as f:
        content = f.read()
    
    assert "set_pot 36" in content
    assert "set_effective_stack 88" in content
    assert "set_board Ts,9d,4h" in content
    assert "set_range_oop" in content
    assert "set_range_ip" in content
    assert "build_tree" in content
    assert "start_solve" in content
    assert "dump_result" in content
    
    # Count bet size commands
    bet_lines = [l for l in content.split("\n") if l.startswith("set_bet_sizes")]
    assert len(bet_lines) >= 12, f"Expected ≥12 bet size commands, got {len(bet_lines)}"
    
    print(f"  ✓ Generated {len(content.split(chr(10)))} commands")
    print(f"  ✓ File: {result_path}")


def test_solver_input_rejects_preflop():
    """Test that generate_solver_input raises ValueError for preflop scenarios."""
    print("Testing solver input rejects preflop...")

    preflop_scenario = ScenarioData(
        hero_hand="QhQd",
        hero_position="BTN",
        board="",
        pot_size_bb=6.5,
        effective_stack_bb=100.0,
        current_street="preflop",
        oop_range="AA,KK,QQ,AKs",
        ip_range="TT+,AQs+,AKo",
        hero_is_ip=True,
        action_history=[],
    )

    with pytest.raises(ValueError, match="postflop"):
        generate_solver_input(preflop_scenario)

    print("  ✓ Correctly rejected preflop scenario")


def test_strategy_extraction():
    """Test extracting strategy from sample solver output."""
    print("Testing strategy extraction...")
    
    sample_file = Path(__file__).parent / "sample_solver_output.json"
    assert sample_file.exists(), f"Sample file not found: {sample_file}"
    
    # Test OOP scenario (player 0 at root)
    scenario_oop = ScenarioData(
        hero_hand="QhQd",
        hero_position="BB",
        board="Ts,9d,4h",
        pot_size_bb=36.0,
        effective_stack_bb=88.0,
        current_street="flop",
        oop_range="AA,KK,QQ",
        ip_range="TT,99,88",
        hero_is_ip=False,  # Hero is OOP = player 0
    )
    
    result = extract_strategy(sample_file, scenario_oop)
    
    assert result.hand == "QhQd"
    assert len(result.actions) == 4
    assert "CHECK" in result.actions
    assert "BET 67" in result.actions
    assert result.best_action == "BET 67"
    assert result.best_action_freq > 0.5
    
    print(f"  ✓ OOP QhQd strategy: {result.actions}")
    print(f"  ✓ Best action: {result.best_action} ({result.best_action_freq:.0%})")
    
    # Test IP scenario (player 1, need to navigate to CHECK child)
    scenario_ip = ScenarioData(
        hero_hand="QhQd",
        hero_position="BTN",
        board="Ts,9d,4h",
        pot_size_bb=36.0,
        effective_stack_bb=88.0,
        current_street="flop",
        oop_range="AA,KK,QQ",
        ip_range="TT,99,88",
        hero_is_ip=True,  # Hero is IP = player 1
    )
    
    result_ip = extract_strategy(sample_file, scenario_ip)
    assert result_ip.hand == "QhQd"
    assert result_ip.actions.get("CHECK", 0) > 0
    print(f"  ✓ IP QhQd strategy: {result_ip.actions}")
    print(f"  ✓ Best action: {result_ip.best_action} ({result_ip.best_action_freq:.0%})")


def test_full_pipeline_no_api():
    """Test the pipeline components that don't require an API key."""
    print("\n" + "=" * 50)
    print("Running offline pipeline tests...")
    print("=" * 50 + "\n")
    
    test_hand_combos()
    test_card_validation()
    test_position_logic()
    test_normalize_hand()
    test_solver_input_generation()
    test_strategy_extraction()
    
    print("\n" + "=" * 50)
    print("✓ All offline tests passed!")
    print("=" * 50)


@pytest.mark.integration
def test_full_pipeline_with_api():
    """Test the full pipeline including API calls (requires GEMINI_API_KEY)."""
    if not config.GEMINI_API_KEY or config.GEMINI_API_KEY == "your-gemini-api-key-here":
        pytest.skip("GEMINI_API_KEY not set")

    from poker_gpt.nl_parser import parse_scenario
    from poker_gpt.nl_advisor import generate_fallback_advice

    # Test NL parsing
    test_input = (
        "I have pocket queens on the button. UTG raises to 3bb, "
        "I 3bet to 9bb, everyone folds and UTG calls. "
        "Flop is Ten of spades, Nine of diamonds, Four of hearts. "
        "UTG checks to me. What should I do?"
    )

    scenario = parse_scenario(test_input)
    assert scenario.hero_hand, "Parser should extract hero hand"
    assert scenario.hero_position, "Parser should extract hero position"

    # Test fallback advisor
    advice = generate_fallback_advice(test_input, scenario)
    assert len(advice) > 0, "Advisor should generate non-empty advice"


# ──────────────────────────────────────────────
# Validation Tests (T1.1)
# ──────────────────────────────────────────────

def _make_valid_scenario(**overrides) -> ScenarioData:
    """Helper to create a valid ScenarioData with optional overrides."""
    defaults = dict(
        hero_hand="QhQd",
        hero_position="BTN",
        board="Ts,9d,4h",
        pot_size_bb=36.0,
        effective_stack_bb=88.0,
        current_street="flop",
        oop_range="AA,KK,QQ,JJ",
        ip_range="TT,99,88,77",
        hero_is_ip=True,
    )
    defaults.update(overrides)
    return ScenarioData(**defaults)


def test_validate_scenario_valid():
    """A valid scenario should pass validation with no errors."""
    scenario = _make_valid_scenario()
    errors = validate_scenario(scenario)
    assert errors == [], f"Expected no errors, got: {errors}"


def test_validate_scenario_missing_hand():
    """Missing hero_hand should produce a validation error."""
    scenario = _make_valid_scenario(hero_hand="")
    errors = validate_scenario(scenario)
    assert len(errors) >= 1
    assert any("hero hand" in e.lower() or "hole cards" in e.lower() for e in errors)


def test_validate_scenario_invalid_hand():
    """An invalid hero_hand (wrong length) should produce a validation error."""
    scenario = _make_valid_scenario(hero_hand="QQ")
    errors = validate_scenario(scenario)
    assert len(errors) >= 1
    assert any("invalid" in e.lower() or "expected" in e.lower() for e in errors)


def test_validate_scenario_invalid_position():
    """An unknown position should produce a validation error."""
    scenario = _make_valid_scenario(hero_position="UNKNOWN")
    errors = validate_scenario(scenario)
    assert len(errors) >= 1
    assert any("position" in e.lower() for e in errors)


def test_validate_scenario_negative_pot():
    """Negative pot_size_bb should produce a validation error."""
    scenario = _make_valid_scenario(pot_size_bb=-5.0)
    errors = validate_scenario(scenario)
    assert len(errors) >= 1
    assert any("pot" in e.lower() for e in errors)


def test_validate_scenario_negative_stack():
    """Negative effective_stack_bb should produce a validation error."""
    scenario = _make_valid_scenario(effective_stack_bb=-10.0)
    errors = validate_scenario(scenario)
    assert len(errors) >= 1
    assert any("stack" in e.lower() for e in errors)


def test_validate_scenario_empty_range():
    """Empty OOP range should produce a validation error."""
    scenario = _make_valid_scenario(oop_range="")
    errors = validate_scenario(scenario)
    assert len(errors) >= 1
    assert any("range" in e.lower() for e in errors)


def test_validate_scenario_invalid_board_card():
    """An invalid board card should produce a validation error."""
    scenario = _make_valid_scenario(board="Xx,9d,4h")
    errors = validate_scenario(scenario)
    assert len(errors) >= 1
    assert any("board" in e.lower() or "card" in e.lower() for e in errors)


def test_validate_scenario_wrong_board_count():
    """Wrong number of board cards for the street should produce a validation error."""
    scenario = _make_valid_scenario(board="Ts,9d", current_street="flop")
    errors = validate_scenario(scenario)
    assert len(errors) >= 1
    assert any("board" in e.lower() or "card" in e.lower() for e in errors)


if __name__ == "__main__":
    test_full_pipeline_no_api()
    
    if "--with-api" in sys.argv:
        test_full_pipeline_with_api()
    else:
        print("\n(Run with --with-api to include API tests)")

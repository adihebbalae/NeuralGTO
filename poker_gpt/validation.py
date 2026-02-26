"""
validation.py — Input validation for parsed poker scenarios.

Validates ScenarioData fields before sending to the solver or advisor.
Returns a list of human-readable error strings (empty = valid).

Created: 2026-02-26

DOCUMENTATION:
    Used by main.py after parse_scenario() returns a ScenarioData.
    If validation fails, the pipeline returns a helpful error message
    instead of crashing or producing nonsensical output.
"""

import re
from typing import Optional

from poker_gpt.poker_types import ScenarioData

# Valid card ranks and suits
_RANKS = set("23456789TJQKA")
_SUITS = set("hdcs")
_VALID_POSITIONS = {"UTG", "HJ", "CO", "BTN", "SB", "BB"}
_VALID_STREETS = {"preflop", "flop", "turn", "river"}


def _is_valid_card(card: str) -> bool:
    """Check if a string represents a valid poker card (e.g., 'Qh', 'Ts')."""
    if len(card) != 2:
        return False
    return card[0] in _RANKS and card[1] in _SUITS


def validate_scenario(scenario: ScenarioData) -> list[str]:
    """
    Validate a parsed ScenarioData for correctness.

    Args:
        scenario: The parsed poker scenario to validate.

    Returns:
        List of error strings. Empty list means the scenario is valid.
    """
    errors: list[str] = []

    # --- Hero hand validation ---
    hand = scenario.hero_hand or ""
    if not hand:
        errors.append(
            "Missing hero hand. Please specify your hole cards "
            "(e.g., 'I have AKs' or 'I hold pocket queens')."
        )
    elif len(hand) != 4:
        errors.append(
            f"Invalid hero hand '{hand}' — expected exactly 2 cards (4 characters), "
            f"got {len(hand)}. Example: 'QhQd', 'AhKs'."
        )
    else:
        card1, card2 = hand[:2], hand[2:]
        if not _is_valid_card(card1):
            errors.append(
                f"Invalid first card '{card1}' in hero hand. "
                f"Use rank (2-9, T, J, Q, K, A) + suit (h, d, c, s)."
            )
        if not _is_valid_card(card2):
            errors.append(
                f"Invalid second card '{card2}' in hero hand. "
                f"Use rank (2-9, T, J, Q, K, A) + suit (h, d, c, s)."
            )

    # --- Position validation ---
    pos = (scenario.hero_position or "").upper()
    if not pos:
        errors.append(
            "Missing hero position. Please specify where you're sitting "
            "(e.g., 'on the button', 'in the big blind', 'UTG')."
        )
    elif pos not in _VALID_POSITIONS:
        errors.append(
            f"Unknown position '{scenario.hero_position}'. "
            f"Valid positions: {', '.join(sorted(_VALID_POSITIONS))}."
        )

    # --- Board validation ---
    board = scenario.board or ""
    if board:
        cards = [c.strip() for c in board.split(",") if c.strip()]
        street = (scenario.current_street or "").lower()
        expected_counts = {"flop": 3, "turn": 4, "river": 5}

        for card in cards:
            if not _is_valid_card(card):
                errors.append(
                    f"Invalid board card '{card}'. "
                    f"Use rank (2-9, T, J, Q, K, A) + suit (h, d, c, s)."
                )

        if street in expected_counts and len(cards) != expected_counts[street]:
            errors.append(
                f"Board has {len(cards)} card(s) but street is '{street}' "
                f"(expected {expected_counts[street]})."
            )

    # --- Street validation ---
    street = (scenario.current_street or "").lower()
    if street and street not in _VALID_STREETS:
        errors.append(
            f"Unknown street '{scenario.current_street}'. "
            f"Valid streets: preflop, flop, turn, river."
        )

    # --- Pot size validation ---
    if scenario.pot_size_bb is not None and scenario.pot_size_bb <= 0:
        errors.append(
            f"Pot size must be positive, got {scenario.pot_size_bb}bb. "
            f"Include the pot size in your description (e.g., 'pot is 20bb')."
        )

    # --- Effective stack validation ---
    if scenario.effective_stack_bb is not None and scenario.effective_stack_bb <= 0:
        errors.append(
            f"Effective stack must be positive, got {scenario.effective_stack_bb}bb. "
            f"Include stack sizes (e.g., '100bb effective')."
        )

    # --- Range validation ---
    if not (scenario.oop_range or "").strip():
        errors.append(
            "OOP player range is empty. The parser couldn't estimate a range. "
            "Try providing more context about the action (e.g., 'UTG raises')."
        )
    if not (scenario.ip_range or "").strip():
        errors.append(
            "IP player range is empty. The parser couldn't estimate a range. "
            "Try providing more context about the action."
        )

    return errors


def format_validation_errors(errors: list[str]) -> str:
    """
    Format a list of validation errors into a user-friendly message.

    Args:
        errors: List of error strings from validate_scenario().

    Returns:
        A formatted string explaining what went wrong and how to fix it.
    """
    if not errors:
        return ""

    lines = [
        "I couldn't fully understand your poker scenario. Here's what needs clarification:\n"
    ]
    for i, err in enumerate(errors, 1):
        lines.append(f"  {i}. {err}")

    lines.append(
        "\nTry rephrasing with more detail. Example:\n"
        '  "I have QQ on the button, UTG raises to 3bb, I call. '
        'Flop is Ts 9d 4h, villain checks. Pot is 20bb, stacks are 90bb."'
    )
    return "\n".join(lines)

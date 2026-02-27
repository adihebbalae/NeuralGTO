"""
validation.py — Input validation for parsed poker scenarios.

Validates ScenarioData fields before sending to the solver or advisor.
Also provides pre-parse query completeness checks to catch vague queries
before they hit the Gemini API (saving tokens).
Returns a list of human-readable error strings (empty = valid).

Created: 2026-02-26
Updated: 2026-02-27 — Added pre-parse query validation, duplicate card detection

DOCUMENTATION:
    validate_query_completeness(query) — called BEFORE parse_scenario().
    validate_scenario(scenario)        — called AFTER  parse_scenario().
    If either returns errors, the pipeline returns a helpful message
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

# ──────────────────────────────────────────────
# Regex patterns for pre-parse query validation
# ──────────────────────────────────────────────

# Card / hand patterns: "AKs", "AKo", "AA", "pocket queens", "pair of", "Jd Td",
# rank names, suited/offsuit, etc.
_HAND_PATTERN = re.compile(
    r"""
    (?:pocket\s+\w+)                  # "pocket queens", "pocket aces"
    | (?:pair\s+of\s+\w+)             # "pair of kings"
    | (?:[2-9TJQKA][hdcs]\s*[2-9TJQKA][hdcs])  # "QhQd", "Ah Ks"
    | (?:[2-9TJQKA]{2}[so]?)          # "AKs", "QQ", "T9o"
    | (?:aces|kings|queens|jacks|tens|nines|eights|sevens|sixes|fives|fours|threes|twos|deuces)
    | (?:ace[- ]king|ace[- ]queen|king[- ]queen|king[- ]jack)
    | (?:big\s+slick)                 # slang for AK
    | (?:rockets|cowboys|ladies|hooks|ducks|crabs|sailboats|snowmen)
    | (?:suited|offsuit|sooted)
    | (?:hold(?:ing)?|have|got|dealt|my\s+hand)
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Position patterns: full names and abbreviations
_POSITION_PATTERN = re.compile(
    r"""
    \b(?:button|btn|cutoff|cut-off|cut\s+off|co
    | under\s*the\s*gun|utg|utg\+1|utg\+2
    | hijack|hj|lojack|lj
    | small\s*blind|sb|big\s*blind|bb
    | mp|middle\s*position|ep|early\s*position
    | late\s*position|lp|straddle)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _is_valid_card(card: str) -> bool:
    """Check if a string represents a valid poker card (e.g., 'Qh', 'Ts')."""
    if len(card) != 2:
        return False
    return card[0] in _RANKS and card[1] in _SUITS


def _extract_cards(hand_or_board: str) -> list[str]:
    """Extract individual 2-char cards from a hand or board string.

    Handles both 'QhQd' (concatenated) and 'Ts,9d,4h' (comma-separated).
    """
    cards: list[str] = []
    if not hand_or_board:
        return cards
    if "," in hand_or_board:
        for part in hand_or_board.split(","):
            part = part.strip()
            if len(part) == 2:
                cards.append(part)
    else:
        for i in range(0, len(hand_or_board) - 1, 2):
            cards.append(hand_or_board[i : i + 2])
    return cards


def validate_query_completeness(query: str) -> list[str]:
    """
    Check a raw query string for completeness BEFORE sending to Gemini.

    This catches vague or incomplete queries early, saving API tokens.

    Args:
        query: The raw natural-language poker question.

    Returns:
        List of error strings. Empty list means the query looks complete enough.
    """
    errors: list[str] = []
    if not query or not query.strip():
        errors.append(
            "Your query is empty. Please describe your poker hand. "
            "Example: 'I have AKs on the CO, facing a 3bet from the BTN. "
            "100bb effective.'"
        )
        return errors

    q = query.strip()

    # Too short
    if len(q) < 10:
        errors.append(
            "Your query is too short. Please describe your poker hand in more "
            "detail. Example: 'I have AKs on the CO, facing a 3bet from the "
            "BTN. 100bb effective.'"
        )

    # No hand / cards mentioned
    if not _HAND_PATTERN.search(q):
        errors.append(
            "Please specify your hole cards (e.g., 'I have AKs', "
            "'I hold pocket queens', 'My hand is Jd Td')."
        )

    # No position mentioned
    if not _POSITION_PATTERN.search(q):
        errors.append(
            "Please mention your position (e.g., 'on the button', "
            "'in the CO', 'UTG')."
        )

    return errors


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

    # --- Duplicate card detection (hero hand + board) ---
    hero_cards = _extract_cards(hand)
    board_cards = _extract_cards(board)
    all_cards = hero_cards + board_cards
    seen: set[str] = set()
    for card in all_cards:
        if not _is_valid_card(card):
            continue
        if card in seen:
            errors.append(
                f"Duplicate card detected: '{card}' appears in both your hand "
                f"and the board (or is repeated). Each card can only appear once "
                f"in a deck — please double-check your input."
            )
        seen.add(card)

    return errors


def format_validation_errors(errors: list[str], header: str = "") -> str:
    """
    Format a list of validation errors into a user-friendly message.

    Args:
        errors: List of error strings from validate_scenario() or
            validate_query_completeness().
        header: Optional custom header line. If empty, a default is used.

    Returns:
        A formatted string explaining what went wrong and how to fix it.
    """
    if not errors:
        return ""

    default_header = (
        "I couldn't fully understand your poker scenario. "
        "Here's what needs clarification:"
    )
    lines = [header or default_header, ""]
    for i, err in enumerate(errors, 1):
        lines.append(f"  {i}. {err}")

    lines.append(
        "\nTip: Try rephrasing with more detail. Example:\n"
        '  "I have QQ on the button, UTG raises to 3bb, I call. '
        'Flop is Ts 9d 4h, villain checks. Pot is 20bb, stacks are 90bb."'
    )
    return "\n".join(lines)

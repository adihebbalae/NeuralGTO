"""
preflop_lookup.py — Preflop GTO strategy lookup from pre-solved range files.

Replaces the LLM-only fallback for preflop scenarios by querying pre-computed
GTO ranges stored as Pio-format .txt files in solver_bin/.

The range files encode the complete 6-max 100bb preflop game tree. Each file
contains a single Pio range string representing the hands a player takes a
specific action with (and at what frequency).

Created: 2026-02-26

DOCUMENTATION:
- Input: ScenarioData with current_street == "preflop"
- Output: StrategyResult with source="preflop_lookup" or None if no match
- Range files live in solver_bin/TexasSolver-v0.2.0-Windows/ranges/qb_ranges/
  100bb 2.5x 500rake/{POSITION}/
- File naming grammar:
    filename ::= action_chain.txt
    action_chain ::= POS_ACTION[_POS_ACTION[...]]
    ACTION ::= SIZE | Call | FOLD | AllIn
    SIZE ::= digits.digitbb  (e.g. 2.5bb, 11.0bb)
- Each .txt file is a single-line Pio range: "AA:1.0,KK:0.5,..."
- Decision nodes: for a given action prefix, multiple files exist with
  different hero actions (e.g. BTN_8.5bb, BTN_Call, BTN_FOLD)
"""

import re
from pathlib import Path
from typing import Optional

from poker_gpt.poker_types import ScenarioData, StrategyResult, ActionEntry
from poker_gpt import config


# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

_RANGE_DIR = (
    Path(config._PROJECT_ROOT)
    / "solver_bin"
    / "TexasSolver-v0.2.0-Windows"
    / "ranges"
    / "qb_ranges"
    / "100bb 2.5x 500rake"
)

# Canonical position order (for mapping HJ → MP, etc.)
_POSITION_MAP = {
    "UTG": "UTG",
    "HJ": "MP",   # TexasSolver calls HJ "MP"
    "MP": "MP",
    "CO": "CO",
    "BTN": "BTN",
    "SB": "SB",
    "BB": "BB",
}

# All 169 canonical hands for validation
_RANKS = "AKQJT98765432"
ALL_HANDS_169: list[str] = []
for i, r1 in enumerate(_RANKS):
    for j, r2 in enumerate(_RANKS):
        if i < j:
            ALL_HANDS_169.append(f"{r1}{r2}s")
        elif i > j:
            ALL_HANDS_169.append(f"{r1}{r2}o")
        else:
            ALL_HANDS_169.append(f"{r1}{r2}")


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def is_preflop_lookup_available() -> bool:
    """Check if the preflop range files exist."""
    return _RANGE_DIR.is_dir()


def lookup_preflop_strategy(scenario: ScenarioData) -> Optional[StrategyResult]:
    """
    Look up the preflop GTO strategy for hero's hand from pre-solved ranges.

    Args:
        scenario: Parsed scenario with current_street == "preflop".

    Returns:
        StrategyResult with action frequencies from the range files,
        or None if the spot cannot be matched to existing files.
    """
    if scenario.current_street != "preflop":
        return None

    if not is_preflop_lookup_available():
        if config.DEBUG:
            print("[PREFLOP_LOOKUP] Range directory not found, skipping lookup")
        return None

    hero_pos = _normalize_position(scenario.hero_position)
    if hero_pos is None:
        if config.DEBUG:
            print(f"[PREFLOP_LOOKUP] Unknown position: {scenario.hero_position}")
        return None

    # Normalize hero's hand to canonical form (e.g. "QhQd" → "QQ")
    canonical_hand = _hand_to_canonical(scenario.hero_hand)
    if canonical_hand is None:
        if config.DEBUG:
            print(f"[PREFLOP_LOOKUP] Cannot canonicalize hand: {scenario.hero_hand}")
        return None

    # Build the action prefix from action_history
    prefix = _build_action_prefix(scenario.action_history, hero_pos)
    if config.DEBUG:
        print(f"[PREFLOP_LOOKUP] Hero={hero_pos}, Hand={canonical_hand}, Prefix='{prefix}'")

    # Find all files that match this decision node
    hero_dir = _RANGE_DIR / hero_pos
    if not hero_dir.is_dir():
        if config.DEBUG:
            print(f"[PREFLOP_LOOKUP] No directory for position {hero_pos}")
        return None

    node_files = _find_decision_node_files(hero_dir, prefix, hero_pos)
    if not node_files:
        if config.DEBUG:
            print(f"[PREFLOP_LOOKUP] No matching files for prefix '{prefix}'")
        return None

    if config.DEBUG:
        print(f"[PREFLOP_LOOKUP] Found {len(node_files)} action files: {list(node_files.keys())}")

    # Parse each file and get hero's hand frequency
    actions: dict[str, float] = {}
    for action_label, filepath in node_files.items():
        range_data = _parse_pio_range_file(filepath)
        if range_data is None:
            continue
        freq = range_data.get(canonical_hand, 0.0)
        actions[action_label] = freq

    if not actions:
        return None

    # Normalize so frequencies sum to 1.0 (they should already, but just in case)
    total = sum(actions.values())
    if total > 0:
        actions = {k: v / total for k, v in actions.items()}
    else:
        # Hand is 0 in all files — pure fold or not in any range
        actions = {"Fold": 1.0}

    # Determine best action
    best_action = max(actions, key=lambda k: actions[k])
    best_freq = actions[best_action]

    # Build range summary (average frequencies across all 169 hands)
    range_summary = _build_range_summary(node_files)

    return StrategyResult(
        hand=scenario.hero_hand,
        actions=actions,
        best_action=best_action,
        best_action_freq=best_freq,
        range_summary=range_summary,
        source="preflop_lookup",
    )


# ──────────────────────────────────────────────
# Internal Helpers
# ──────────────────────────────────────────────

def _normalize_position(pos: str) -> Optional[str]:
    """Map position string to the directory name used in range files."""
    return _POSITION_MAP.get(pos.upper())


def _hand_to_canonical(hand: str) -> Optional[str]:
    """
    Convert a specific hand like 'QhQd' or 'AcKh' to canonical form 'QQ' or 'AKo'.

    Canonical form: higher rank first, then 's' (suited), 'o' (offsuit), or
    nothing (pair).
    """
    hand = hand.strip()

    # Already canonical? (e.g. "QQ", "AKs", "AKo")
    if re.match(r'^[AKQJT2-9]{2}[so]?$', hand):
        return hand

    # Specific cards: "QhQd", "AcKh", etc.
    match = re.match(r'^([AKQJT2-9])([cdhs])([AKQJT2-9])([cdhs])$', hand, re.IGNORECASE)
    if not match:
        return None

    r1, s1, r2, s2 = match.groups()
    r1, r2 = r1.upper(), r2.upper()
    s1, s2 = s1.lower(), s2.lower()

    rank_order = "AKQJT98765432"
    i1 = rank_order.index(r1)
    i2 = rank_order.index(r2)

    # Ensure higher rank first
    if i1 > i2:
        r1, r2 = r2, r1
        s1, s2 = s2, s1

    if r1 == r2:
        return f"{r1}{r2}"  # Pair
    elif s1 == s2:
        return f"{r1}{r2}s"  # Suited
    else:
        return f"{r1}{r2}o"  # Offsuit


def _build_action_prefix(
    action_history: list[ActionEntry],
    hero_pos: str,
) -> str:
    """
    Convert the ScenarioData action_history into the filename prefix
    used by the range files.

    The action_history contains all actions that have occurred BEFORE hero's
    current decision. Hero's prior actions (e.g., opening before facing a 3bet)
    ARE included — only fold actions by non-hero players are omitted (they
    don't appear in the range filenames).

    Example 1 — BB facing BTN open:
        history: [BTN raise 2.5bb]
        hero_pos: BB
        → "BTN_2.5bb"

    Example 2 — UTG facing BTN 3-bet after opening:
        history: [UTG raise 2.5bb, BTN raise 8.5bb]
        hero_pos: UTG
        → "UTG_2.5bb_BTN_8.5bb"

    Example 3 — BB squeeze after CO open + BTN call:
        history: [CO raise 2.5bb, BTN call]
        hero_pos: BB
        → "CO_2.5bb_BTN_Call"
    """
    parts: list[str] = []

    for entry in action_history:
        # Only preflop actions
        if entry.street != "preflop":
            continue

        pos = _normalize_position(entry.position)
        if pos is None:
            continue

        action = entry.action.lower()

        # Fold actions by any player don't appear in the filenames
        # (they're implicit — only raises, calls, and all-ins are encoded)
        if action == "fold":
            continue
        if action in ("raise", "bet", "open"):
            # Size-based: "POS_X.Xbb"
            if entry.amount_bb is not None:
                size = f"{entry.amount_bb:.1f}bb"
                parts.append(f"{pos}_{size}")
            else:
                # Fallback: try to infer standard sizing
                parts.append(f"{pos}_2.5bb")
        elif action == "call":
            parts.append(f"{pos}_Call")
        elif action in ("allin", "all-in", "all_in", "jam", "shove"):
            parts.append(f"{pos}_AllIn")
        else:
            # Unknown action — skip
            if config.DEBUG:
                print(f"[PREFLOP_LOOKUP] Unknown action '{action}' for {pos}")

    return "_".join(parts) if parts else ""


def _find_decision_node_files(
    hero_dir: Path,
    prefix: str,
    hero_pos: str,
) -> dict[str, Path]:
    """
    Find all files in hero_dir (and subdirs) that match the action prefix
    and differ only in the hero's final action.

    Returns a dict mapping action label → file path.
    E.g., {"Raise 8.5bb": Path(...), "Call": Path(...), "Fold": Path(...)}
    """
    results: dict[str, Path] = {}

    # Build the expected file prefix
    if prefix:
        file_prefix = f"{prefix}_{hero_pos}_"
    else:
        # Hero is opening — file is just "POS_ACTION.txt"
        file_prefix = f"{hero_pos}_"

    # Search all .txt files in hero_dir and subdirs
    for txt_file in hero_dir.rglob("*.txt"):
        stem = txt_file.stem  # filename without .txt

        if not stem.startswith(file_prefix):
            # Special case: if prefix is empty and hero is opening,
            # the file might just be "BTN_2.5bb.txt" or "BTN_FOLD.txt"
            if prefix == "" and stem.startswith(f"{hero_pos}_"):
                pass  # Allow through
            else:
                continue

        # Extract the hero's action (everything after the prefix)
        hero_action_part = stem[len(file_prefix):]

        # Classify the action
        action_label = _classify_action(hero_action_part, hero_pos)
        if action_label:
            results[action_label] = txt_file

    return results


def _classify_action(action_str: str, hero_pos: str) -> Optional[str]:
    """
    Classify a filename suffix into a human-readable action label.

    Examples:
        "8.5bb" → "Raise 8.5bb"
        "Call"  → "Call"
        "FOLD"  → "Fold"
        "AllIn" → "All-In"
        "24.0bb" → "Raise 24.0bb"
    """
    if not action_str:
        return None

    if action_str == "Call":
        return "Call"
    elif action_str == "FOLD":
        return "Fold"
    elif action_str == "AllIn":
        return "All-In"
    elif re.match(r'^\d+\.\d+bb$', action_str):
        return f"Raise {action_str}"
    else:
        # Could be a multi-action suffix involving other players' actions
        # after hero's action — skip these (they're not hero's decision files)
        return None


def _parse_pio_range_file(filepath: Path) -> Optional[dict[str, float]]:
    """
    Parse a single-line Pio range file into {hand: freq} dict.

    Format: "AA:1.0,KK:0.5,AKs:1.0,AKo:0.75,..."
    Returns dict with all 169 canonical hands mapped to their frequency.
    Hands not mentioned default to 0.0.
    """
    try:
        text = filepath.read_text(encoding="utf-8").strip()
        if not text:
            return None
    except (OSError, UnicodeDecodeError):
        return None

    result: dict[str, float] = {}

    for entry in text.split(","):
        entry = entry.strip()
        if not entry:
            continue

        if ":" in entry:
            hand_part, freq_str = entry.rsplit(":", 1)
            try:
                freq = float(freq_str)
            except ValueError:
                freq = 0.0
        else:
            hand_part = entry
            freq = 1.0  # No weight = full weight

        hand_part = hand_part.strip()
        if hand_part:
            result[hand_part] = freq

    return result


def _build_range_summary(
    node_files: dict[str, Path],
) -> dict[str, float]:
    """
    Build a range-wide summary: average frequency for each action across
    all 169 hands (weighted equally by combo).

    Returns e.g. {"Raise 2.5bb": 0.42, "Fold": 0.58}
    """
    summary: dict[str, float] = {}

    for action_label, filepath in node_files.items():
        range_data = _parse_pio_range_file(filepath)
        if range_data is None:
            summary[action_label] = 0.0
            continue

        # Sum all frequencies across all hands
        total_freq = sum(range_data.values())
        # There are 169 unique hand types, but with different combo counts.
        # For simplicity, average across the 169 types (good approximation).
        avg_freq = total_freq / 169.0 if total_freq > 0 else 0.0
        summary[action_label] = avg_freq

    # Normalize to sum to 1.0
    total = sum(summary.values())
    if total > 0:
        summary = {k: v / total for k, v in summary.items()}

    return summary

"""
range_display.py — ASCII and rich 13x13 hand range grid visualization.

Renders a poker hand range as a 13x13 grid in the terminal, with optional
color-coding by action type using the rich library.

Created: 2026-02-27

DOCUMENTATION:
Usage:
    from poker_gpt.range_display import render_range_grid, render_range_grid_rich

    # Plain text grid with hero hand highlighted:
    print(render_range_grid({"Raise": 0.78, "Call": 0.15, "Fold": 0.07}, hand="QhQd"))

    # Rich terminal output (color-coded):
    render_range_grid_rich({"Raise": 0.78, "Call": 0.15, "Fold": 0.07}, hand="QhQd")

    # Full range visualization from solver output:
    print(render_strategy_grid(range_summary, highlight_hand="QhQd"))

Grid layout:
    - Rows/columns indexed by rank: A K Q J T 9 8 7 6 5 4 3 2
    - Upper-left triangle (row < col) = suited combos (e.g. AKs)
    - Diagonal (row == col) = pairs (e.g. AA)
    - Lower-right triangle (row > col) = offsuit combos (e.g. AKo)
"""

from typing import Optional

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]
"""Rank labels ordered from highest to lowest (grid top-to-bottom, left-to-right)."""

RANK_INDEX = {r: i for i, r in enumerate(RANKS)}
"""Map rank character to its 0-based grid index."""

# Action keywords mapped to display categories for color-coding.
# We normalize mixed-case solver actions to lower for matching.
_ACTION_COLORS = {
    "raise": "green",
    "bet": "green",
    "call": "blue",
    "check": "blue",
    "fold": "red",
    "allin": "green",
}


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _hand_to_combo_type(hand: str) -> str:
    """Convert a specific hand like 'QhQd' or 'AhKs' to its canonical combo type.

    Args:
        hand: A 4-character hand string, e.g. 'AhKd', 'QhQd', 'Ts9s'.

    Returns:
        Canonical combo type string: 'AKo', 'AKs', 'QQ', etc.

    Raises:
        ValueError: If hand format is unrecognised.
    """
    if len(hand) < 4:
        raise ValueError(f"Hand too short: '{hand}'")

    rank1, suit1 = hand[0], hand[1]
    rank2, suit2 = hand[2], hand[3]

    # Ensure higher rank comes first
    idx1 = RANK_INDEX.get(rank1)
    idx2 = RANK_INDEX.get(rank2)
    if idx1 is None or idx2 is None:
        raise ValueError(f"Unknown rank in hand: '{hand}'")

    if idx1 > idx2:
        # Swap so higher rank is first
        rank1, suit1, rank2, suit2 = rank2, suit2, rank1, suit1

    if rank1 == rank2:
        return f"{rank1}{rank2}"  # Pair, e.g. "QQ"
    elif suit1 == suit2:
        return f"{rank1}{rank2}s"  # Suited, e.g. "AKs"
    else:
        return f"{rank1}{rank2}o"  # Offsuit, e.g. "AKo"


def hand_to_grid_position(hand: str) -> tuple[int, int]:
    """Convert a hand like 'QhQd' or 'AhKs' to its (row, col) in the 13x13 grid.

    In the standard range grid:
    - Pairs sit on the diagonal (row == col).
    - Suited hands sit in the upper-left triangle (row < col).
    - Offsuit hands sit in the lower-right triangle (row > col).

    Args:
        hand: A 4-character hand string, e.g. 'AhKd'.

    Returns:
        (row, col) tuple of 0-based indices into the 13x13 grid.

    Raises:
        ValueError: If hand format is unrecognised.
    """
    if len(hand) < 4:
        raise ValueError(f"Hand too short: '{hand}'")

    rank1, suit1 = hand[0], hand[1]
    rank2, suit2 = hand[2], hand[3]

    idx1 = RANK_INDEX.get(rank1)
    idx2 = RANK_INDEX.get(rank2)
    if idx1 is None or idx2 is None:
        raise ValueError(f"Unknown rank in hand: '{hand}'")

    # Ensure higher rank (lower index) comes first
    if idx1 > idx2:
        rank1, suit1, rank2, suit2 = rank2, suit2, rank1, suit1
        idx1, idx2 = idx2, idx1

    if rank1 == rank2:
        # Pair — on the diagonal
        return (idx1, idx1)
    elif suit1 == suit2:
        # Suited — upper-left triangle: row = higher rank, col = lower rank
        return (idx1, idx2)
    else:
        # Offsuit — lower-right triangle: row = lower rank, col = higher rank
        return (idx2, idx1)


def _combo_label(row: int, col: int) -> str:
    """Return the combo label for a given grid cell.

    Args:
        row: Row index (0-12).
        col: Column index (0-12).

    Returns:
        e.g. 'AA', 'AKs', 'AKo'.
    """
    r1 = RANKS[row]
    r2 = RANKS[col]
    if row == col:
        return f"{r1}{r2}"
    elif row < col:
        return f"{r1}{r2}s"
    else:
        return f"{r2}{r1}o"


def _dominant_action(actions: dict[str, float]) -> str:
    """Return the action key with the highest frequency.

    Args:
        actions: Mapping of action names to frequencies.

    Returns:
        The action name with the highest frequency, or '' if empty.
    """
    if not actions:
        return ""
    return max(actions, key=actions.get)  # type: ignore[arg-type]


def _action_category(action: str) -> str:
    """Normalise an action string to a colour category.

    Handles solver actions like 'BET 67', 'RAISE 100', 'CHECK', 'CALL', etc.

    Args:
        action: Action string from solver output.

    Returns:
        One of 'green', 'blue', 'red', or 'white' (unknown).
    """
    key = action.strip().split()[0].lower()
    return _ACTION_COLORS.get(key, "white")


# ──────────────────────────────────────────────
# Plain-text grid
# ──────────────────────────────────────────────

def render_range_grid(actions: dict[str, float], hand: str = "") -> str:
    """Render a plain-text 13x13 range grid showing where a hand falls.

    Args:
        actions: Strategy action dict, e.g. {"Raise": 0.78, "Call": 0.15}.
        hand: Optional specific hand to highlight, e.g. 'QhQd'.

    Returns:
        Multi-line string of the 13x13 grid with the hand cell bracketed.
    """
    highlight: Optional[tuple[int, int]] = None
    if hand:
        try:
            highlight = hand_to_grid_position(hand)
        except ValueError:
            pass

    cell_width = 5
    lines: list[str] = []

    # Header row
    header = " " * cell_width + " ".join(f"{r:^{cell_width}}" for r in RANKS)
    lines.append(header)

    for row in range(13):
        cells: list[str] = []
        for col in range(13):
            label = _combo_label(row, col)
            if highlight and (row, col) == highlight:
                cell = f"[{label}]"
            else:
                cell = f" {label} "
            cells.append(f"{cell:^{cell_width}}")
        line = f"{RANKS[row]:^{cell_width}}" + " ".join(cells)
        lines.append(line)

    # Legend
    if hand and highlight:
        combo = _hand_to_combo_type(hand)
        best = _dominant_action(actions) if actions else "?"
        best_freq = actions.get(best, 0.0) if actions else 0.0
        lines.append("")
        lines.append(f"  Hero: {hand} → {combo}  |  Best action: {best} ({best_freq*100:.0f}%)")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Rich (colorized) grid
# ──────────────────────────────────────────────

def render_range_grid_rich(actions: dict[str, float], hand: str = "") -> None:
    """Render a colorized 13x13 range grid using the rich library.

    Color-coding:
        - Green: raise / bet / allin
        - Blue:  call / check
        - Red:   fold

    The hero's hand cell is bold + underlined.

    Falls back to plain text if rich is not installed.

    Args:
        actions: Strategy action dict, e.g. {"Raise": 0.78, "Call": 0.15}.
        hand: Optional specific hand to highlight, e.g. 'QhQd'.
    """
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.text import Text
    except ImportError:
        print(render_range_grid(actions, hand))
        return

    highlight: Optional[tuple[int, int]] = None
    if hand:
        try:
            highlight = hand_to_grid_position(hand)
        except ValueError:
            pass

    best_action = _dominant_action(actions) if actions else ""
    color = _action_category(best_action) if best_action else "white"

    console = Console()
    table = Table(
        title="Range Grid",
        show_header=True,
        header_style="bold",
        show_lines=False,
        pad_edge=False,
        padding=(0, 1),
    )

    # First column for row labels
    table.add_column("", style="bold", min_width=3, justify="center")
    for r in RANKS:
        table.add_column(r, min_width=5, justify="center")

    for row in range(13):
        cells: list[Text] = []
        for col in range(13):
            label = _combo_label(row, col)
            is_hero = highlight is not None and (row, col) == highlight

            if is_hero:
                cell = Text(f"[{label}]", style=f"bold underline {color}")
            else:
                cell = Text(f" {label} ", style="dim")

            cells.append(cell)

        table.add_row(RANKS[row], *cells)

    console.print(table)

    # Action summary below grid
    if hand and actions:
        combo = _hand_to_combo_type(hand) if hand else ""
        parts: list[str] = []
        for act, freq in sorted(actions.items(), key=lambda x: -x[1]):
            act_color = _action_category(act)
            parts.append(f"[{act_color}]{act} {freq*100:.0f}%[/{act_color}]")
        summary = "  ".join(parts)
        console.print(f"  Hero: {hand} → {combo}  |  {summary}")


# ──────────────────────────────────────────────
# Full-range strategy grid
# ──────────────────────────────────────────────

def render_strategy_grid(
    range_summary: dict[str, dict],
    highlight_hand: str = "",
) -> str:
    """Render a full 13x13 grid with each cell colored by dominant action.

    Uses single-character markers to keep the grid compact:
        R = raise/bet, C = call/check, F = fold, · = not in range

    Args:
        range_summary: Mapping of combo type (e.g. 'AKs') to action dicts
                       (e.g. {'Raise': 0.6, 'Call': 0.4}).
        highlight_hand: Optional specific hand to highlight, e.g. 'QhQd'.

    Returns:
        Multi-line plain-text string of the 13x13 grid.
    """
    highlight: Optional[tuple[int, int]] = None
    if highlight_hand:
        try:
            highlight = hand_to_grid_position(highlight_hand)
        except ValueError:
            pass

    # Markers for dominant action category
    _markers = {"green": "R", "blue": "C", "red": "F", "white": "?"}

    cell_width = 5
    lines: list[str] = []

    header = " " * cell_width + " ".join(f"{r:^{cell_width}}" for r in RANKS)
    lines.append(header)

    for row in range(13):
        cells: list[str] = []
        for col in range(13):
            label = _combo_label(row, col)
            combo_actions = range_summary.get(label, {})

            if combo_actions:
                best = _dominant_action(combo_actions)
                cat = _action_category(best)
                marker = _markers.get(cat, "?")
                freq = combo_actions.get(best, 0.0)
                # Show marker + frequency as percentage (compact)
                inner = f"{marker}{int(freq*100):>2d}"
            else:
                inner = " · "

            is_hero = highlight is not None and (row, col) == highlight
            if is_hero:
                cell = f"[{inner}]"
            else:
                cell = f" {inner} "
            cells.append(f"{cell:^{cell_width}}")

        line = f"{RANKS[row]:^{cell_width}}" + " ".join(cells)
        lines.append(line)

    # Legend
    lines.append("")
    lines.append("  R = Raise/Bet  C = Call/Check  F = Fold  · = Not in range")
    if highlight_hand and highlight:
        combo = _hand_to_combo_type(highlight_hand)
        lines.append(f"  Hero: {highlight_hand} → {combo}")

    return "\n".join(lines)

"""
spot_frequency.py — Spot frequency data and study prioritization.

Provides approximate frequency data for common poker spot types in 6-max
cash games. Used to tell the player how often a spot type occurs and to
suggest similar, higher-frequency spots worth studying.

Data is based on published 6-max distribution studies (GTO Wizard blog,
PokerTracker 4 databases, and standard 6-max simulations).

Created: 2026-02-27

DOCUMENTATION:
    get_spot_frequency(scenario) → SpotFrequencyInfo
    Returns frequency data for the spot described by the scenario, including
    how often it comes up, whether it's high-priority for study, and
    similar spots to also drill.
"""

from dataclasses import dataclass, field
from typing import Optional

from poker_gpt.poker_types import ScenarioData


@dataclass
class SpotFrequencyInfo:
    """Frequency and study priority data for a poker spot type."""

    # The canonical spot label (e.g., "SRP BTN vs BB on flop")
    spot_label: str

    # Approximate frequency as % of all hands dealt (6-max cash)
    frequency_pct: float

    # How important this spot is to study (1 = most, 5 = least)
    priority_tier: int

    # Human-readable priority label
    priority_label: str

    # Brief note about why this spot matters (or doesn't)
    note: str

    # Similar spots the player should also study
    similar_spots: list[str] = field(default_factory=list)

    # Whether this is a common "bread-and-butter" spot
    is_high_frequency: bool = False


# ──────────────────────────────────────────────
# Spot frequency database (6-max cash game)
# ──────────────────────────────────────────────
# Sources:
#   - GTO Wizard blog: "Unwrapping GTO Wizard's Hidden Gems for 2025"
#     (SRP frequency data, spot distribution analysis)
#   - PokerTracker 4 standard population stats
#   - Standard 6-max preflop range analysis
#
# All frequencies are approximate % of all hands DEALT.
# They vary by game type, stake, and table dynamics.

# Position-pair frequencies for getting to postflop (% of all hands)
# These are approximate heads-up pot frequencies for common matchups.
_POSITION_PAIR_FREQ = {
    # Single-raised pots (SRP) — ~23% of all spots total
    ("BTN", "BB"): 4.9,    # Most common SRP pairing
    ("CO", "BB"): 3.8,
    ("BTN", "SB"): 2.5,
    ("HJ", "BB"): 2.8,
    ("CO", "BTN"): 1.5,    # 3bet pot usually
    ("UTG", "BB"): 2.2,
    ("SB", "BB"): 3.5,     # SB completes or limps into BB
    # 3-bet pots — ~6% of all spots total
    ("BTN", "CO"): 1.2,    # CO opens, BTN 3bets
    ("CO", "BTN"): 1.2,    # BTN 3bets, CO defends
    ("BB", "BTN"): 1.8,    # BTN opens, BB 3bets
    ("BB", "CO"): 1.0,
    ("BB", "HJ"): 0.8,
    ("SB", "BTN"): 0.9,
    # 4-bet pots — ~1% of all spots total
    # (lumped into "rare" category)
}

# Street distribution: given you reach postflop, how often do you face
# a decision on each street? (conditional on seeing that street)
_STREET_BASE_FREQ = {
    "preflop": 100.0,   # Every hand starts here
    "flop": 35.0,       # ~35% of hands see a flop (6-max)
    "turn": 18.0,       # ~18% see a turn
    "river": 10.0,      # ~10% see a river
}

# Action type frequencies (% of flops/streets where this action pattern occurs)
_ACTION_TYPE_LABELS = {
    "srp": "Single-Raised Pot",
    "3bp": "3-Bet Pot",
    "4bp": "4-Bet Pot",
    "5bp": "5-Bet Pot",
    "limp": "Limped Pot",
    "unknown": "Unknown Pot Type",
}

# Priority mapping
_PRIORITY_LABELS = {
    1: "🔥 Top priority — bread-and-butter spot",
    2: "⭐ High priority — common and impactful",
    3: "📚 Medium priority — worth studying",
    4: "📖 Low priority — infrequent but can be high-stakes",
    5: "🔬 Rare — only study after mastering common spots",
}


def _classify_pot_type(scenario: ScenarioData) -> str:
    """Classify the pot type from the action history."""
    if not scenario.action_history:
        return "srp"  # Default assumption

    raise_count = 0
    for action in scenario.action_history:
        act = (action.action if isinstance(action, dict) is False
               else action.get("action", ""))
        if hasattr(action, "action"):
            act = action.action
        if act.lower() in ("raise", "3bet", "4bet", "allin"):
            raise_count += 1

    if raise_count >= 4:
        return "5bp"
    elif raise_count >= 3:
        return "4bp"
    elif raise_count >= 2:
        return "3bp"
    elif raise_count >= 1:
        return "srp"
    else:
        return "limp"


def _get_position_pair(scenario: ScenarioData) -> tuple[str, str]:
    """Extract the two positions involved from the scenario."""
    hero_pos = scenario.hero_position.upper()

    # Try to find villain's position from action history
    villain_pos = None
    for action in scenario.action_history:
        pos = ""
        if hasattr(action, "position"):
            pos = action.position.upper()
        elif isinstance(action, dict):
            pos = action.get("position", "").upper()
        if pos and pos != hero_pos:
            villain_pos = pos
            break

    if not villain_pos:
        # Default: assume position-based matchup
        if scenario.hero_is_ip:
            villain_pos = "BB"  # Default OOP villain
        else:
            villain_pos = "BTN"  # Default IP villain

    # Return as (IP, OOP) or (opener, defender) based on hero's perspective
    if scenario.hero_is_ip:
        return (hero_pos, villain_pos)
    else:
        return (villain_pos, hero_pos)


def _suggest_similar_spots(
    hero_pos: str,
    street: str,
    pot_type: str,
) -> list[str]:
    """Suggest similar, potentially higher-frequency spots to study."""
    suggestions: list[str] = []

    # Always suggest the most common SRP spots
    common_srps = [
        "SRP BTN vs BB on flop — the single most common postflop spot (~5% of all hands)",
        "SRP CO vs BB on flop — second most common (~3.8%)",
        "SRP SB vs BB on flop — limped/completed pots (~3.5%)",
    ]

    # Position-specific suggestions
    if hero_pos in ("UTG", "HJ"):
        suggestions.append(
            "SRP from early position vs blinds — study c-bet strategies "
            "with a tight range advantage on dry boards"
        )
    elif hero_pos == "BTN":
        suggestions.append(
            "BTN vs BB single-raised pots — your most frequent spot; "
            "master flop c-bet and turn barrel strategies"
        )
    elif hero_pos in ("SB", "BB"):
        suggestions.append(
            "Blind defense vs late position opens — study check-raise "
            "and donk-bet frequencies on various board textures"
        )

    # Street-specific suggestions
    if street == "river":
        suggestions.append(
            "Flop and turn spots in the same configuration — you face "
            "10x more decisions before the river than on it"
        )
    elif street == "turn":
        suggestions.append(
            "Flop c-bet and check-raise spots — turn decisions flow "
            "from flop play; mastering flop strategy cascades forward"
        )

    # Pot type suggestions
    if pot_type in ("4bp", "5bp"):
        suggestions.append(
            "3-bet pots are 6x more common than 4-bet pots — "
            "master 3-bet pot play first"
        )
    elif pot_type == "3bp":
        suggestions.append(
            "Single-raised pots are 4x more common than 3-bet pots — "
            "ensure your SRP fundamentals are solid"
        )

    # Add common SRPs if they're not already covered
    for srp in common_srps:
        if hero_pos not in srp or street not in srp:
            suggestions.append(srp)
            if len(suggestions) >= 4:
                break

    return suggestions[:4]


def get_spot_frequency(scenario: ScenarioData) -> SpotFrequencyInfo:
    """
    Compute spot frequency and study priority for a poker scenario.

    Args:
        scenario: The parsed poker scenario.

    Returns:
        SpotFrequencyInfo with frequency data and study suggestions.
    """
    hero_pos = scenario.hero_position.upper()
    street = scenario.current_street.lower()
    pot_type = _classify_pot_type(scenario)
    pot_label = _ACTION_TYPE_LABELS.get(pot_type, "Unknown Pot Type")
    ip_pos, oop_pos = _get_position_pair(scenario)

    # Look up base frequency for this position pair
    pair_key = (ip_pos, oop_pos)
    pair_key_rev = (oop_pos, ip_pos)
    base_freq = _POSITION_PAIR_FREQ.get(
        pair_key,
        _POSITION_PAIR_FREQ.get(pair_key_rev, 1.0),
    )

    # Adjust for street depth — fewer hands reach later streets
    street_multiplier = {
        "preflop": 1.0,
        "flop": 1.0,  # base_freq already accounts for seeing flop
        "turn": 0.55,  # ~55% of flop hands see a turn
        "river": 0.30,  # ~30% of flop hands see a river
    }.get(street, 1.0)

    # Adjust for pot type — 3bet/4bet pots are rarer
    pot_type_multiplier = {
        "srp": 1.0,
        "3bp": 0.25,
        "4bp": 0.05,
        "5bp": 0.01,
        "limp": 0.8,
    }.get(pot_type, 1.0)

    frequency = base_freq * street_multiplier * pot_type_multiplier

    # Determine priority tier
    if frequency >= 3.0:
        priority_tier = 1
    elif frequency >= 1.5:
        priority_tier = 2
    elif frequency >= 0.5:
        priority_tier = 3
    elif frequency >= 0.1:
        priority_tier = 4
    else:
        priority_tier = 5

    priority_label = _PRIORITY_LABELS.get(priority_tier, "")
    is_high_freq = priority_tier <= 2

    # Build spot label
    spot_label = f"{pot_label} {ip_pos} vs {oop_pos} on {street}"

    # Generate note
    if is_high_freq:
        note = (
            f"This is a high-frequency spot (~{frequency:.1f}% of all hands). "
            f"Mastering it will directly impact your win rate every session."
        )
    elif priority_tier == 3:
        note = (
            f"This spot comes up moderately often (~{frequency:.1f}% of hands). "
            f"Worth studying, but don't neglect the more common SRP spots."
        )
    elif priority_tier == 4:
        note = (
            f"This spot is relatively uncommon (~{frequency:.2f}% of hands). "
            f"The decisions can be high-stakes, but you'd get more overall "
            f"EV improvement from drilling common spots."
        )
    else:
        note = (
            f"This is a rare spot (~{frequency:.2f}% of hands). "
            f"Study it for completeness, but focus your time on spots "
            f"you see every session. See suggestions below."
        )

    # Similar spots to study
    similar = _suggest_similar_spots(hero_pos, street, pot_type)

    return SpotFrequencyInfo(
        spot_label=spot_label,
        frequency_pct=round(frequency, 2),
        priority_tier=priority_tier,
        priority_label=priority_label,
        note=note,
        similar_spots=similar,
        is_high_frequency=is_high_freq,
    )


def format_spot_frequency_for_advisor(info: SpotFrequencyInfo) -> str:
    """Format spot frequency info for injection into the advisor context.

    Args:
        info: SpotFrequencyInfo from get_spot_frequency().

    Returns:
        A text block suitable for appending to the advisor's context message.
    """
    lines = [
        "SPOT FREQUENCY DATA:",
        f"  Spot type: {info.spot_label}",
        f"  Frequency: ~{info.frequency_pct}% of all hands",
        f"  Study priority: {info.priority_label}",
        f"  {info.note}",
    ]

    if info.similar_spots:
        lines.append("  Similar spots to also study:")
        for spot in info.similar_spots:
            lines.append(f"    - {spot}")

    return "\n".join(lines)

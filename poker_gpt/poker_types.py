"""
poker_types.py — Core data structures for the PokerGPT pipeline.

All data that flows between pipeline stages is defined here as dataclasses.
This ensures type safety and clear contracts between modules.

Created: 2026-02-06
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class Position(Enum):
    """Standard 6-max poker positions."""
    UTG = "UTG"       # Under the Gun (first to act preflop)
    HJ = "HJ"         # Hijack
    CO = "CO"          # Cutoff
    BTN = "BTN"        # Button (dealer)
    SB = "SB"          # Small Blind
    BB = "BB"          # Big Blind


class Street(Enum):
    """Poker streets (betting rounds)."""
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"


class Action(Enum):
    """Possible poker actions."""
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
    ALL_IN = "allin"


@dataclass
class ActionEntry:
    """A single action in the hand history."""
    position: str          # e.g. "UTG", "BTN", "BB"
    action: str            # e.g. "raise", "call", "check", "bet", "fold", "allin"
    amount_bb: Optional[float] = None  # Amount in big blinds (None for check/fold)
    street: str = "preflop"  # Which street this action occurred on


@dataclass
class ScenarioData:
    """
    Fully parsed poker scenario — the output of Step 1 (NL Parser).
    Contains everything needed to configure the solver.
    """
    # Hero's information
    hero_hand: str               # e.g. "QhQd" — specific cards
    hero_position: str           # e.g. "BTN"

    # Board cards (empty string if preflop)
    board: str                   # e.g. "Ts,9d,4h" — comma-separated, solver format

    # Game state at the decision point
    pot_size_bb: float           # Current pot in big blinds
    effective_stack_bb: float    # Effective stack remaining behind
    current_street: str          # "flop", "turn", or "river"

    # Ranges (in TexasSolver format)
    oop_range: str               # OOP player's estimated range
    ip_range: str                # IP player's estimated range

    # Who is hero? (needed to read the right strategy from output)
    hero_is_ip: bool             # True if hero is In Position

    # Full action history (for context and tree navigation)
    action_history: list = field(default_factory=list)  # List of ActionEntry dicts

    # Bet sizing configuration (defaults work for most spots)
    bet_sizes_pct: list = field(default_factory=lambda: [33, 67, 100])
    raise_sizes_pct: list = field(default_factory=lambda: [60, 100])

    # Additional context
    num_players_preflop: int = 2    # How many players saw the flop
    game_type: str = "cash"         # "cash" or "tournament"
    stack_depth_bb: float = 100.0   # Starting stack depth


@dataclass
class StrategyResult:
    """
    Output of Step 4 (Strategy Extractor).
    The solver's recommended strategy for hero's specific hand.
    """
    # Hero's hand
    hand: str                    # e.g. "QhQd"

    # Available actions and their GTO frequencies
    actions: dict                # e.g. {"CHECK": 0.15, "BET 67": 0.60, "BET 100": 0.25}

    # Best action (highest frequency)
    best_action: str             # e.g. "BET 67"
    best_action_freq: float      # e.g. 0.60

    # Range-wide strategy summary (what does the whole range do here?)
    range_summary: dict = field(default_factory=dict)  # e.g. {"CHECK": 0.40, "BET": 0.60}

    # Raw data for debugging
    raw_node: dict = field(default_factory=dict)

    # Whether this came from the solver or the fallback
    source: str = "solver"       # "solver" or "gpt_fallback"

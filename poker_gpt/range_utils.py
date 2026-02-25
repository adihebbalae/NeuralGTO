"""
range_utils.py — Poker range utilities.

Provides helper functions for working with poker hand ranges in TexasSolver format.
Includes common preflop ranges by position for use as defaults.

Created: 2026-02-06

DOCUMENTATION:
- Ranges use TexasSolver notation: "AA,KK,QQ:0.5,AKs,AKo:0.75,..."
- Suits: c=clubs, d=diamonds, h=hearts, s=spades
- Hand types: suited (s), offsuit (o), pairs (no suffix)
- Weights: hand:weight where weight is 0.0-1.0 (default 1.0)
"""

# ──────────────────────────────────────────────
# Standard 6-max Opening Ranges (approximate GTO)
# These are reasonable approximations for common spots.
# The GPT parser can override these based on specific reads.
# ──────────────────────────────────────────────

# RFI (Raise First In) ranges by position
RFI_RANGES = {
    "UTG": (
        "AA,KK,QQ,JJ,TT,99,88,77,66,"
        "AKs,AQs,AJs,ATs,A5s,A4s,"
        "AKo,AQo,"
        "KQs,KJs,KTs,"
        "QJs,QTs,"
        "JTs,J9s,"
        "T9s,T8s,"
        "98s,97s,"
        "87s,86s,"
        "76s,75s,"
        "65s,64s,"
        "54s"
    ),
    "HJ": (
        "AA,KK,QQ,JJ,TT,99,88,77,66,55,"
        "AKs,AQs,AJs,ATs,A9s,A5s,A4s,A3s,"
        "AKo,AQo,AJo,"
        "KQs,KJs,KTs,K9s,"
        "KQo,"
        "QJs,QTs,Q9s,"
        "JTs,J9s,J8s,"
        "T9s,T8s,"
        "98s,97s,"
        "87s,86s,"
        "76s,75s,"
        "65s,64s,"
        "54s,53s"
    ),
    "CO": (
        "AA,KK,QQ,JJ,TT,99,88,77,66,55,44,"
        "AKs,AQs,AJs,ATs,A9s,A8s,A7s,A6s,A5s,A4s,A3s,A2s,"
        "AKo,AQo,AJo,ATo,"
        "KQs,KJs,KTs,K9s,K8s,"
        "KQo,KJo,"
        "QJs,QTs,Q9s,Q8s,"
        "QJo,"
        "JTs,J9s,J8s,"
        "JTo,"
        "T9s,T8s,T7s,"
        "98s,97s,96s,"
        "87s,86s,"
        "76s,75s,"
        "65s,64s,"
        "54s,53s,"
        "43s"
    ),
    "BTN": (
        "AA,KK,QQ,JJ,TT,99,88,77,66,55,44,33,22,"
        "AKs,AQs,AJs,ATs,A9s,A8s,A7s,A6s,A5s,A4s,A3s,A2s,"
        "AKo,AQo,AJo,ATo,A9o,"
        "KQs,KJs,KTs,K9s,K8s,K7s,K6s,K5s,"
        "KQo,KJo,KTo,"
        "QJs,QTs,Q9s,Q8s,Q7s,Q6s,"
        "QJo,QTo,"
        "JTs,J9s,J8s,J7s,"
        "JTo,J9o,"
        "T9s,T8s,T7s,T6s,"
        "T9o,"
        "98s,97s,96s,95s,"
        "87s,86s,85s,"
        "76s,75s,74s,"
        "65s,64s,63s,"
        "54s,53s,52s,"
        "43s,42s,"
        "32s"
    ),
    "SB": (
        "AA,KK,QQ,JJ,TT,99,88,77,66,55,44,33,22,"
        "AKs,AQs,AJs,ATs,A9s,A8s,A7s,A6s,A5s,A4s,A3s,A2s,"
        "AKo,AQo,AJo,ATo,A9o,A8o,"
        "KQs,KJs,KTs,K9s,K8s,K7s,K6s,K5s,K4s,"
        "KQo,KJo,KTo,K9o,"
        "QJs,QTs,Q9s,Q8s,Q7s,Q6s,Q5s,"
        "QJo,QTo,Q9o,"
        "JTs,J9s,J8s,J7s,J6s,"
        "JTo,J9o,"
        "T9s,T8s,T7s,T6s,"
        "T9o,T8o,"
        "98s,97s,96s,95s,"
        "98o,"
        "87s,86s,85s,"
        "87o,"
        "76s,75s,74s,"
        "65s,64s,63s,"
        "54s,53s,52s,"
        "43s"
    ),
    "BB": (  # BB defense vs single raise (very wide)
        "AA,KK,QQ,JJ,TT,99,88,77,66,55,44,33,22,"
        "AKs,AQs,AJs,ATs,A9s,A8s,A7s,A6s,A5s,A4s,A3s,A2s,"
        "AKo,AQo,AJo,ATo,A9o,A8o,A7o,A6o,A5o,A4o,A3o,A2o,"
        "KQs,KJs,KTs,K9s,K8s,K7s,K6s,K5s,K4s,K3s,K2s,"
        "KQo,KJo,KTo,K9o,K8o,K7o,"
        "QJs,QTs,Q9s,Q8s,Q7s,Q6s,Q5s,Q4s,Q3s,Q2s,"
        "QJo,QTo,Q9o,Q8o,"
        "JTs,J9s,J8s,J7s,J6s,J5s,J4s,"
        "JTo,J9o,J8o,"
        "T9s,T8s,T7s,T6s,T5s,"
        "T9o,T8o,T7o,"
        "98s,97s,96s,95s,94s,"
        "98o,97o,"
        "87s,86s,85s,84s,"
        "87o,86o,"
        "76s,75s,74s,73s,"
        "76o,75o,"
        "65s,64s,63s,62s,"
        "65o,"
        "54s,53s,52s,"
        "54o,"
        "43s,42s,"
        "32s"
    ),
}

# 3-bet ranges (when facing a raise)
THREE_BET_RANGES = {
    "BTN_vs_UTG": (
        "AA,KK,QQ,JJ:0.5,AKs,AKo,AQs:0.5,"
        "A5s:0.5,A4s:0.5,"
        "KQs:0.25"
    ),
    "BTN_vs_CO": (
        "AA,KK,QQ,JJ,TT:0.5,"
        "AKs,AKo,AQs,AQo:0.5,AJs:0.5,"
        "A5s,A4s,"
        "KQs:0.5,"
        "76s:0.25,65s:0.25"
    ),
    "BB_vs_BTN": (
        "AA,KK,QQ,JJ,TT,99:0.5,"
        "AKs,AKo,AQs,AQo,AJs,AJo:0.5,ATs:0.5,"
        "A5s,A4s,A3s,"
        "KQs,KJs:0.5,"
        "QJs:0.25,"
        "T9s:0.25,98s:0.25,87s:0.25,76s:0.25,65s:0.25,54s:0.25"
    ),
    "SB_vs_BTN": (
        "AA,KK,QQ,JJ,TT,"
        "AKs,AKo,AQs,AQo,AJs,ATs,"
        "A5s,A4s,A3s,"
        "KQs,KJs,"
        "QJs:0.5"
    ),
    # Generic 3bet range (fallback)
    "DEFAULT": (
        "AA,KK,QQ,JJ:0.75,TT:0.25,"
        "AKs,AKo,AQs:0.75,AQo:0.25,"
        "A5s:0.5,A4s:0.5"
    ),
}

# 4-bet / call-3bet ranges
FOUR_BET_RANGES = {
    "DEFAULT": "AA,KK,QQ:0.5,AKs,AKo:0.5,A5s:0.25",
}

CALL_THREE_BET_RANGES = {
    "DEFAULT": (
        "QQ:0.5,JJ,TT,99,88,77,"
        "AQs,AQo:0.5,AJs,ATs,A9s,"
        "KQs,KJs,KTs,"
        "QJs,QTs,"
        "JTs,J9s,"
        "T9s,T8s,"
        "98s,97s,"
        "87s,76s,65s,54s"
    ),
}


# ──────────────────────────────────────────────
# Utility Functions
# ──────────────────────────────────────────────

RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']
SUITS = ['h', 'd', 'c', 's']


def hand_to_solver_combos(hand_str: str) -> list[str]:
    """
    Convert a hand like 'QQ' or 'AKs' to specific card combos like ['QhQd', 'QhQc', ...].
    Used when the user specifies a hand without suits and we need to find all combos.
    """
    hand_str = hand_str.strip()
    if len(hand_str) == 4:
        # Already specific: e.g. "QhQd"
        return [hand_str]
    
    if len(hand_str) == 2:
        # Pair: e.g. "QQ"
        rank = hand_str[0]
        combos = []
        for i, s1 in enumerate(SUITS):
            for s2 in SUITS[i+1:]:
                combos.append(f"{rank}{s1}{rank}{s2}")
        return combos
    
    if len(hand_str) == 3:
        r1, r2, suit_type = hand_str[0], hand_str[1], hand_str[2]
        combos = []
        if suit_type == 's':
            # Suited
            for s in SUITS:
                combos.append(f"{r1}{s}{r2}{s}")
        elif suit_type == 'o':
            # Offsuit
            for i, s1 in enumerate(SUITS):
                for j, s2 in enumerate(SUITS):
                    if i != j:
                        combos.append(f"{r1}{s1}{r2}{s2}")
        return combos
    
    return [hand_str]


def is_valid_card(card_str: str) -> bool:
    """Check if a card string like 'Qh' is valid."""
    if len(card_str) != 2:
        return False
    return card_str[0] in RANKS and card_str[1] in SUITS


def normalize_hand_for_lookup(card1: str, card2: str) -> str:
    """
    Normalize a two-card hand for lookup in solver output.
    Solver uses format like 'QhQd' (higher card first by rank, then by suit).
    """
    # Convert to (rank_int, suit_int) for sorting
    r1 = RANKS.index(card1[0])
    r2 = RANKS.index(card2[0])
    
    if r1 < r2:  # Lower index = higher rank
        return card1 + card2
    elif r1 > r2:
        return card2 + card1
    else:
        # Same rank (pair) — sort by suit
        s1 = SUITS.index(card1[1])
        s2 = SUITS.index(card2[1])
        if s1 <= s2:
            return card1 + card2
        else:
            return card2 + card1


def get_position_relative(hero_pos: str, villain_pos: str) -> tuple[bool, str, str]:
    """
    Determine who is IP (in position) and OOP (out of position) postflop.
    
    Postflop position order (first to act = OOP):
    SB > BB > UTG > HJ > CO > BTN
    
    Returns: (hero_is_ip, oop_position, ip_position)
    """
    # Postflop acting order (index 0 acts first = OOP)
    POSTFLOP_ORDER = ["SB", "BB", "UTG", "HJ", "CO", "BTN"]
    
    hero_idx = POSTFLOP_ORDER.index(hero_pos) if hero_pos in POSTFLOP_ORDER else 5
    villain_idx = POSTFLOP_ORDER.index(villain_pos) if villain_pos in POSTFLOP_ORDER else 0
    
    if hero_idx > villain_idx:
        # Hero acts later = IP
        return True, villain_pos, hero_pos
    else:
        return False, hero_pos, villain_pos

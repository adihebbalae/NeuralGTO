"""
hand_history.py — Hand History Import & Parsing for NeuralGTO.

Parses hand history files from PokerStars, GGPoker, and ClubWPT Gold
into structured ParsedHand objects, then converts them into natural
language query strings suitable for the NeuralGTO pipeline.

Created: 2026-02-27

DOCUMENTATION:
    Supported sites:
        - PokerStars (header: "PokerStars Hand #...")
        - GGPoker     (header: "Poker Hand #RC..." or "Poker Hand #HD...")
        - ClubWPT Gold (header: "ClubWPT" in first line)

    Primary entry points:
        parse_hand_history(text, hero_name)      — auto-detect site, parse all hands
        parse_hand_history_file(filepath, hero_name) — read file, then parse
        hand_to_query(hand)                      — convert ParsedHand → NL query string

    Error handling:
        - Individual hand parse failures are caught and skipped.
        - parse_pokerstars_hand / parse_ggpoker_hand / parse_clubwpt_hand
          raise ValueError on unparseable input.
        - parse_hand_history never raises; returns empty list on total failure.

    No external dependencies beyond stdlib.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


# ──────────────────────────────────────────────
# Data Model
# ──────────────────────────────────────────────

@dataclass
class ParsedHand:
    """A single parsed hand from a hand history file."""
    hand_id: str                       # Original hand ID from site
    site: str                          # "pokerstars" | "ggpoker" | "clubwpt"
    hero_name: str                     # Hero's player name
    hero_hand: str                     # "AhKs" format (no spaces)
    hero_position: str                 # "BTN", "CO", "UTG", etc.
    board: list[str]                   # ["Ts", "9d", "4h"] or [] for preflop
    pot_size_bb: float                 # Pot in big blinds at decision point
    effective_stack_bb: float          # Effective stack in big blinds
    actions: list[dict]                # [{"player": "Hero", "action": "raise", "amount": 3.0}, ...]
    street: str                        # "preflop" | "flop" | "turn" | "river"
    big_blind: float                   # Size of big blind for conversion
    timestamp: str                     # ISO timestamp of the hand
    raw_text: str                      # Original hand text


# ──────────────────────────────────────────────
# Position Mapping
# ──────────────────────────────────────────────

# Map from total seats + seat-offset-from-button to standard position names.
# For 6-max: BTN, SB, BB, UTG, HJ (MP), CO
_6MAX_POSITIONS = ["BTN", "SB", "BB", "UTG", "HJ", "CO"]
# For 9-max: BTN, SB, BB, UTG, UTG+1, UTG+2, LJ, HJ, CO
_9MAX_POSITIONS = ["BTN", "SB", "BB", "UTG", "UTG+1", "UTG+2", "LJ", "HJ", "CO"]


def _assign_positions(
    seat_numbers: list[int],
    button_seat: int,
    num_seats: int,
) -> dict[int, str]:
    """
    Assign standard position names to seat numbers.

    Args:
        seat_numbers: List of occupied seat numbers (1-based).
        button_seat: Which seat is the button.
        num_seats: Table size (6 or 9).

    Returns:
        Dict mapping seat number → position string.
    """
    positions = _6MAX_POSITIONS if num_seats <= 6 else _9MAX_POSITIONS
    # Sort seats starting from button
    sorted_seats = sorted(
        seat_numbers,
        key=lambda s: (s - button_seat) % max(seat_numbers),
    )
    # button is first in sorted order
    result: dict[int, str] = {}
    n = len(sorted_seats)
    for i, seat in enumerate(sorted_seats):
        if i < len(positions) and i < n:
            result[seat] = positions[i]
        else:
            result[seat] = f"SEAT{seat}"
    return result


# ──────────────────────────────────────────────
# Site Detection
# ──────────────────────────────────────────────

def detect_site(text: str) -> str:
    """
    Detect which poker site produced the hand history.

    Args:
        text: Raw hand history text (can contain multiple hands).

    Returns:
        "pokerstars" | "ggpoker" | "clubwpt" | "unknown"
    """
    first_500 = text[:500].lower()
    if "clubwpt" in first_500:
        return "clubwpt"
    if "pokerstars" in first_500:
        return "pokerstars"
    # GGPoker uses "Poker Hand #RC" or "Poker Hand #HD"
    if re.search(r"poker\s+hand\s+#(rc|hd)", first_500):
        return "ggpoker"
    return "unknown"


# ──────────────────────────────────────────────
# Hand Splitting
# ──────────────────────────────────────────────

def _split_hands(text: str, site: str) -> list[str]:
    """
    Split a multi-hand file into individual hand blocks.

    Args:
        text: Full file text.
        site: Detected site name.

    Returns:
        List of individual hand text blocks.
    """
    if site == "pokerstars" or site == "clubwpt":
        # PokerStars / ClubWPT: hands separated by blank lines,
        # each starting with a header line
        pattern = r"(?=(?:PokerStars|ClubWPT)\s+Hand\s+#)"
        if site == "clubwpt":
            pattern = r"(?=ClubWPT\s+Hand\s+#)"
        else:
            pattern = r"(?=PokerStars\s+Hand\s+#)"
        blocks = re.split(pattern, text, flags=re.IGNORECASE)
    elif site == "ggpoker":
        blocks = re.split(r"(?=Poker\s+Hand\s+#)", text, flags=re.IGNORECASE)
    else:
        # Fallback: try splitting on double newlines with a "Hand #" nearby
        blocks = re.split(r"\n\n(?=.*Hand\s*#)", text)

    return [b.strip() for b in blocks if b.strip()]


# ──────────────────────────────────────────────
# Common Parsing Helpers
# ──────────────────────────────────────────────

_CARD_RE = re.compile(r"\b([2-9TJQKA][cdhs])\b")


def _parse_blinds(header: str) -> tuple[float, float]:
    """
    Extract small blind and big blind from a header line.

    Args:
        header: The first line of a hand history block.

    Returns:
        (small_blind, big_blind) as floats.

    Raises:
        ValueError: If blinds cannot be parsed.
    """
    # Patterns: ($1/$2 USD), ($0.50/$1), (€1/€2), ($1/$2)
    m = re.search(
        r"[\(\[]"
        r"[€$]?([\d,]+\.?\d*)\s*/\s*[€$]?([\d,]+\.?\d*)"
        r"(?:\s*USD|\s*EUR)?"
        r"[\)\]]",
        header,
    )
    if m:
        sb = float(m.group(1).replace(",", ""))
        bb = float(m.group(2).replace(",", ""))
        return sb, bb
    raise ValueError(f"Cannot parse blinds from header: {header!r}")


def _parse_timestamp_ps(header: str) -> str:
    """
    Parse a PokerStars-style timestamp into ISO format.

    Args:
        header: Header line containing a date.

    Returns:
        ISO-formatted timestamp string, or "" if not found.
    """
    m = re.search(r"(\d{4}/\d{2}/\d{2})\s+(\d{1,2}:\d{2}:\d{2})", header)
    if m:
        date_str = m.group(1).replace("/", "-")
        time_str = m.group(2)
        return f"{date_str}T{time_str}"
    return ""


def _parse_dealt_cards(text: str, hero_name: str) -> str:
    """
    Extract the hero's hole cards from "Dealt to <hero> [Ah Ks]".

    Args:
        text: Hand history text.
        hero_name: The hero's player name.

    Returns:
        Cards in "AhKs" format (no spaces).

    Raises:
        ValueError: If dealt line is not found for hero.
    """
    # Escape hero_name for regex, match "Dealt to HeroName [Ah Ks]"
    pattern = re.compile(
        r"Dealt\s+to\s+" + re.escape(hero_name) + r"\s+\[([^\]]+)\]",
        re.IGNORECASE,
    )
    m = pattern.search(text)
    if m:
        cards_raw = m.group(1).strip()
        # Normalize: "Ah Ks" → "AhKs"
        cards = cards_raw.replace(" ", "")
        return cards
    raise ValueError(f"No dealt cards found for hero '{hero_name}'")


def _parse_seats(text: str) -> dict[int, tuple[str, float]]:
    """
    Parse seat lines: "Seat N: PlayerName ($amount in chips)"

    Args:
        text: Hand history text.

    Returns:
        Dict of seat_number → (player_name, chip_count).
    """
    seats: dict[int, tuple[str, float]] = {}
    for m in re.finditer(
        r"Seat\s+(\d+):\s+(.+?)\s+\(\s*[€$]?([\d,]+\.?\d*)\s+in\s+chips\s*\)",
        text,
    ):
        seat_num = int(m.group(1))
        player = m.group(2).strip()
        chips = float(m.group(3).replace(",", ""))
        seats[seat_num] = (player, chips)
    return seats


def _parse_button_seat(text: str) -> int:
    """
    Parse "Seat #N is the button".

    Args:
        text: Hand history text.

    Returns:
        Button seat number.

    Raises:
        ValueError: If button seat line is missing.
    """
    m = re.search(r"Seat\s*#(\d+)\s+is\s+the\s+button", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    raise ValueError("Cannot find button seat")


def _detect_hero_name(text: str, hero_name: str) -> str:
    """
    If hero_name is empty, try to auto-detect from "Dealt to <name>" line.

    Args:
        text: Hand history text.
        hero_name: User-provided hero name (may be empty).

    Returns:
        Hero name (detected or given).

    Raises:
        ValueError: If no hero can be detected.
    """
    if hero_name:
        return hero_name
    m = re.search(r"Dealt\s+to\s+(\S+)\s+\[", text)
    if m:
        return m.group(1)
    raise ValueError(
        "Cannot auto-detect hero name. Provide hero_name parameter."
    )


def _parse_table_size(text: str) -> int:
    """
    Detect table size from "6-max" / "9-max" / "6-Max" etc.

    Args:
        text: Hand history text.

    Returns:
        Number of seats (6 or 9). Defaults to 6.
    """
    m = re.search(r"(\d+)\s*-?\s*[Mm]ax", text)
    if m:
        return int(m.group(1))
    return 6


def _parse_board(text: str) -> list[str]:
    """
    Extract all board cards from street markers.

    Parses FLOP, TURN, and RIVER lines like:
        *** FLOP *** [Ts 9d 4h]
        *** TURN *** [Ts 9d 4h] [2c]
        *** RIVER *** [Ts 9d 4h 2c] [Jh]

    Args:
        text: Hand history text.

    Returns:
        List of board cards, e.g. ["Ts", "9d", "4h", "2c", "Jh"].
    """
    board: list[str] = []
    seen: set[str] = set()

    for m in re.finditer(r"\*{3}\s+(?:FLOP|TURN|RIVER)\s+\*{3}\s+(.+)", text):
        line = m.group(1)
        # Extract all bracketed groups, e.g. [Ts 9d 4h] [2c]
        for bracket_match in re.finditer(r"\[([^\]]+)\]", line):
            cards_str = bracket_match.group(1)
            for card in cards_str.split():
                card = card.strip()
                if _CARD_RE.fullmatch(card) and card not in seen:
                    board.append(card)
                    seen.add(card)
    return board


def _determine_street(board: list[str]) -> str:
    """
    Determine the current street from the number of board cards.

    Args:
        board: List of board cards.

    Returns:
        "preflop" | "flop" | "turn" | "river"
    """
    n = len(board)
    if n == 0:
        return "preflop"
    elif n <= 3:
        return "flop"
    elif n == 4:
        return "turn"
    else:
        return "river"


def _last_street_with_action(text: str) -> str:
    """
    Determine the last street on which any action occurred.

    Args:
        text: Hand history text.

    Returns:
        The last street label found ("preflop", "flop", "turn", "river").
    """
    last = "preflop"
    if re.search(r"\*{3}\s+FLOP\s+\*{3}", text):
        last = "flop"
    if re.search(r"\*{3}\s+TURN\s+\*{3}", text):
        last = "turn"
    if re.search(r"\*{3}\s+RIVER\s+\*{3}", text):
        last = "river"
    return last


def _parse_actions(text: str, bb: float) -> list[dict]:
    """
    Parse all player actions from the hand history text.

    Extracts folds, checks, calls, bets, raises, and all-ins.

    Args:
        text: Hand history text.
        bb: Big blind size for amount conversion.

    Returns:
        List of action dicts with keys: player, action, amount, street.
    """
    actions: list[dict] = []
    current_street = "preflop"

    for line in text.splitlines():
        line = line.strip()

        # Street transitions
        if "*** FLOP ***" in line:
            current_street = "flop"
            continue
        if "*** TURN ***" in line:
            current_street = "turn"
            continue
        if "*** RIVER ***" in line:
            current_street = "river"
            continue

        # Skip non-action lines
        if "*** " in line:
            continue

        # Action patterns
        # "PlayerName: folds"
        # "PlayerName: checks"
        # "PlayerName: calls $2"
        # "PlayerName: bets $6"
        # "PlayerName: raises $12 to $18"
        # "PlayerName: raises $12 to $18 and is all-in"

        m = re.match(
            r"^(.+?):\s+"
            r"(folds|checks|calls|bets|raises)"
            r"(?:\s+[€$]?([\d,]+\.?\d*))?"
            r"(?:\s+to\s+[€$]?([\d,]+\.?\d*))?"
            r"(\s+and\s+is\s+all-in)?",
            line,
            re.IGNORECASE,
        )
        if m:
            player = m.group(1).strip()
            action_str = m.group(2).lower()
            amount_raw = m.group(4) or m.group(3)  # prefer "to" amount
            is_allin = bool(m.group(5))

            amount: Optional[float] = None
            if amount_raw:
                amount = round(float(amount_raw.replace(",", "")) / bb, 1) if bb > 0 else 0.0

            if is_allin:
                action_str = "allin"

            entry = {
                "player": player,
                "action": action_str,
                "street": current_street,
            }
            if amount is not None:
                entry["amount"] = amount
            actions.append(entry)

    return actions


def _compute_pot_and_stacks(
    seats: dict[int, tuple[str, float]],
    actions: list[dict],
    hero_name: str,
    bb: float,
) -> tuple[float, float]:
    """
    Compute the pot size and hero's effective stack from actions.

    Walking the action list to sum contributions and track remaining stacks.

    Args:
        seats: Dict of seat_number → (player_name, chip_count).
        actions: Parsed action list.
        hero_name: Hero's player name.
        bb: Big blind size.

    Returns:
        (pot_size_bb, effective_stack_bb)
    """
    # Build a chip map: player → starting chips
    chip_map: dict[str, float] = {}
    for _, (player, chips) in seats.items():
        chip_map[player] = chips

    # Track contributions
    contributions: dict[str, float] = {}
    for a in actions:
        player = a["player"]
        if player not in contributions:
            contributions[player] = 0.0
        # amount is already in bb
        amt_bb = a.get("amount", 0.0)
        if a["action"] in ("calls", "bets", "raises", "allin") and amt_bb:
            contributions[player] = max(contributions[player], amt_bb)

    pot_bb = sum(contributions.values())
    # If pot is 0 (no actions parsed with amounts), estimate from blinds
    if pot_bb == 0:
        pot_bb = 1.5  # SB + BB

    # Hero's starting stack in bb
    hero_chips = 0.0
    for _, (player, chips) in seats.items():
        if player == hero_name:
            hero_chips = chips
            break
    hero_stack_bb = hero_chips / bb if bb > 0 else 100.0

    # Effective stack is hero's remaining stack minus what hero put in
    hero_contrib = contributions.get(hero_name, 0.0)
    effective_bb = hero_stack_bb - hero_contrib
    if effective_bb <= 0:
        effective_bb = hero_stack_bb  # Fallback

    return round(pot_bb, 1), round(effective_bb, 1)


# ──────────────────────────────────────────────
# PokerStars Parser
# ──────────────────────────────────────────────

def parse_pokerstars_hand(text: str, hero_name: str = "") -> ParsedHand:
    """
    Parse a single PokerStars hand history block.

    Args:
        text: A single hand history block (one hand).
        hero_name: Hero's player name. If empty, auto-detected from
            "Dealt to" line.

    Returns:
        ParsedHand object.

    Raises:
        ValueError: If the hand cannot be parsed.
    """
    lines = text.strip().splitlines()
    if not lines:
        raise ValueError("Empty hand history text")

    header = lines[0]

    # Hand ID
    m_id = re.search(r"Hand\s+#(\d+)", header)
    if not m_id:
        raise ValueError(f"Cannot parse hand ID from: {header!r}")
    hand_id = m_id.group(1)

    # Blinds
    sb, bb = _parse_blinds(header)

    # Timestamp
    timestamp = _parse_timestamp_ps(header)

    # Table size
    table_size = _parse_table_size(text)

    # Seats
    seats = _parse_seats(text)
    if not seats:
        raise ValueError("No seats found in hand history")

    # Button
    button_seat = _parse_button_seat(text)

    # Hero name
    hero_name = _detect_hero_name(text, hero_name)

    # Hero's cards
    hero_hand = _parse_dealt_cards(text, hero_name)

    # Positions
    seat_nums = sorted(seats.keys())
    pos_map = _assign_positions(seat_nums, button_seat, table_size)

    # Hero's position
    hero_seat: Optional[int] = None
    for sn, (pname, _) in seats.items():
        if pname == hero_name:
            hero_seat = sn
            break
    if hero_seat is None:
        raise ValueError(f"Hero '{hero_name}' not found in seats")
    hero_position = pos_map.get(hero_seat, "UTG")

    # Board
    board = _parse_board(text)

    # Street
    street = _last_street_with_action(text)

    # Actions
    actions = _parse_actions(text, bb)

    # Pot and stacks
    pot_bb, eff_stack_bb = _compute_pot_and_stacks(seats, actions, hero_name, bb)

    return ParsedHand(
        hand_id=hand_id,
        site="pokerstars",
        hero_name=hero_name,
        hero_hand=hero_hand,
        hero_position=hero_position,
        board=board,
        pot_size_bb=pot_bb,
        effective_stack_bb=eff_stack_bb,
        actions=actions,
        street=street,
        big_blind=bb,
        timestamp=timestamp,
        raw_text=text,
    )


# ──────────────────────────────────────────────
# GGPoker Parser
# ──────────────────────────────────────────────

def parse_ggpoker_hand(text: str, hero_name: str = "") -> ParsedHand:
    """
    Parse a single GGPoker hand history block.

    GGPoker format is very similar to PokerStars with minor differences:
    - Header starts with "Poker Hand #RC..." or "Poker Hand #HD..."
    - Some formatting differences in amounts

    Args:
        text: A single hand history block.
        hero_name: Hero's player name. If empty, auto-detected.

    Returns:
        ParsedHand object.

    Raises:
        ValueError: If the hand cannot be parsed.
    """
    lines = text.strip().splitlines()
    if not lines:
        raise ValueError("Empty hand history text")

    header = lines[0]

    # Hand ID — GGPoker uses alphanumeric IDs like RC12345 or HD12345
    m_id = re.search(r"Hand\s+#(\w+)", header)
    if not m_id:
        raise ValueError(f"Cannot parse hand ID from: {header!r}")
    hand_id = m_id.group(1)

    # Blinds
    sb, bb = _parse_blinds(header)

    # Timestamp
    timestamp = _parse_timestamp_ps(header)  # Same format

    # Table size
    table_size = _parse_table_size(text)

    # Seats
    seats = _parse_seats(text)
    if not seats:
        raise ValueError("No seats found in hand history")

    # Button
    button_seat = _parse_button_seat(text)

    # Hero name
    hero_name = _detect_hero_name(text, hero_name)

    # Hero's cards
    hero_hand = _parse_dealt_cards(text, hero_name)

    # Positions
    seat_nums = sorted(seats.keys())
    pos_map = _assign_positions(seat_nums, button_seat, table_size)

    # Hero's position
    hero_seat: Optional[int] = None
    for sn, (pname, _) in seats.items():
        if pname == hero_name:
            hero_seat = sn
            break
    if hero_seat is None:
        raise ValueError(f"Hero '{hero_name}' not found in seats")
    hero_position = pos_map.get(hero_seat, "UTG")

    # Board
    board = _parse_board(text)

    # Street
    street = _last_street_with_action(text)

    # Actions
    actions = _parse_actions(text, bb)

    # Pot and stacks
    pot_bb, eff_stack_bb = _compute_pot_and_stacks(seats, actions, hero_name, bb)

    return ParsedHand(
        hand_id=hand_id,
        site="ggpoker",
        hero_name=hero_name,
        hero_hand=hero_hand,
        hero_position=hero_position,
        board=board,
        pot_size_bb=pot_bb,
        effective_stack_bb=eff_stack_bb,
        actions=actions,
        street=street,
        big_blind=bb,
        timestamp=timestamp,
        raw_text=text,
    )


# ──────────────────────────────────────────────
# ClubWPT Gold Parser
# ──────────────────────────────────────────────

def parse_clubwpt_hand(text: str, hero_name: str = "") -> ParsedHand:
    """
    Parse a single ClubWPT Gold hand history block.

    ClubWPT uses a PokerStars-like format with "ClubWPT" in the header
    instead of "PokerStars". This parser reuses the same helpers and
    only differs in header detection and hand ID extraction.

    Args:
        text: A single hand history block.
        hero_name: Hero's player name. If empty, auto-detected.

    Returns:
        ParsedHand object.

    Raises:
        ValueError: If the hand cannot be parsed.
    """
    lines = text.strip().splitlines()
    if not lines:
        raise ValueError("Empty hand history text")

    header = lines[0]

    # Hand ID
    m_id = re.search(r"Hand\s+#(\w+)", header)
    if not m_id:
        raise ValueError(f"Cannot parse hand ID from: {header!r}")
    hand_id = m_id.group(1)

    # Blinds
    sb, bb = _parse_blinds(header)

    # Timestamp
    timestamp = _parse_timestamp_ps(header)

    # Table size
    table_size = _parse_table_size(text)

    # Seats
    seats = _parse_seats(text)
    if not seats:
        raise ValueError("No seats found in hand history")

    # Button
    button_seat = _parse_button_seat(text)

    # Hero name
    hero_name = _detect_hero_name(text, hero_name)

    # Hero's cards
    hero_hand = _parse_dealt_cards(text, hero_name)

    # Positions
    seat_nums = sorted(seats.keys())
    pos_map = _assign_positions(seat_nums, button_seat, table_size)

    # Hero's position
    hero_seat: Optional[int] = None
    for sn, (pname, _) in seats.items():
        if pname == hero_name:
            hero_seat = sn
            break
    if hero_seat is None:
        raise ValueError(f"Hero '{hero_name}' not found in seats")
    hero_position = pos_map.get(hero_seat, "UTG")

    # Board
    board = _parse_board(text)

    # Street
    street = _last_street_with_action(text)

    # Actions
    actions = _parse_actions(text, bb)

    # Pot and stacks
    pot_bb, eff_stack_bb = _compute_pot_and_stacks(seats, actions, hero_name, bb)

    return ParsedHand(
        hand_id=hand_id,
        site="clubwpt",
        hero_name=hero_name,
        hero_hand=hero_hand,
        hero_position=hero_position,
        board=board,
        pot_size_bb=pot_bb,
        effective_stack_bb=eff_stack_bb,
        actions=actions,
        street=street,
        big_blind=bb,
        timestamp=timestamp,
        raw_text=text,
    )


# ──────────────────────────────────────────────
# Top-Level Parsing API
# ──────────────────────────────────────────────

def parse_hand_history(text: str, hero_name: str = "") -> list[ParsedHand]:
    """
    Parse a hand history text containing one or more hands.

    Auto-detects the site format, splits hands, and parses each one.
    Individual parse failures are silently skipped (logged in debug mode).

    Args:
        text: Raw hand history text (may contain multiple hands).
        hero_name: Hero's player name. If empty, auto-detected from
            the first "Dealt to" line found.

    Returns:
        List of successfully parsed ParsedHand objects.
        Returns empty list if nothing could be parsed.
    """
    site = detect_site(text)

    # Choose parser function
    parsers = {
        "pokerstars": parse_pokerstars_hand,
        "ggpoker": parse_ggpoker_hand,
        "clubwpt": parse_clubwpt_hand,
    }
    parser_fn = parsers.get(site)
    if parser_fn is None:
        # Unknown site — try PokerStars parser as fallback
        parser_fn = parse_pokerstars_hand

    # Split into individual hands
    blocks = _split_hands(text, site)

    results: list[ParsedHand] = []
    for block in blocks:
        try:
            hand = parser_fn(block, hero_name=hero_name)
            results.append(hand)
        except (ValueError, KeyError, IndexError):
            # Skip unparseable hands
            continue

    return results


def parse_hand_history_file(filepath: str, hero_name: str = "") -> list[ParsedHand]:
    """
    Read a hand history file and parse all hands in it.

    Args:
        filepath: Path to the hand history file.
        hero_name: Hero's player name. If empty, auto-detected.

    Returns:
        List of ParsedHand objects.

    Raises:
        FileNotFoundError: If the file does not exist.
        OSError: If the file cannot be read.
    """
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    return parse_hand_history(text, hero_name=hero_name)


# ──────────────────────────────────────────────
# Query Conversion
# ──────────────────────────────────────────────

def hand_to_query(hand: ParsedHand) -> str:
    """
    Convert a ParsedHand into a natural language query string
    suitable for ``analyze_hand()``.

    Produces a human-readable description of the hand state including
    hero's cards, position, board, pot, stacks, and summary of actions.

    Args:
        hand: A parsed hand history object.

    Returns:
        Natural language query string.

    Example output:
        "I have AhKs on the CO. The board is Ts 9d 4h. Pot is 12.0bb,
         effective stack is 85.0bb. Villain bet 6.0bb."
    """
    parts: list[str] = []

    # Hero's hand and position
    parts.append(f"I have {hand.hero_hand} on the {hand.hero_position}.")

    # Board
    if hand.board:
        board_str = " ".join(hand.board)
        parts.append(f"The board is {board_str}.")

    # Pot and stacks
    parts.append(
        f"Pot is {hand.pot_size_bb}bb, "
        f"effective stack is {hand.effective_stack_bb}bb."
    )

    # Summarize key villain actions (last few actions, skip hero's own)
    villain_actions = [
        a for a in hand.actions
        if a["player"] != hand.hero_name
        and a["action"] not in ("folds",)
    ]
    # Show last 3 villain actions for context
    recent = villain_actions[-3:]
    for a in recent:
        action_str = a["action"]
        if action_str == "checks":
            parts.append(f"{a['player']} checks.")
        elif "amount" in a:
            parts.append(f"{a['player']} {action_str} {a['amount']}bb.")
        else:
            parts.append(f"{a['player']} {action_str}.")

    return " ".join(parts)


def hands_summary(hands: list[ParsedHand]) -> list[str]:
    """
    Generate a short summary line for each hand (for selection UIs).

    Args:
        hands: List of ParsedHand objects.

    Returns:
        List of summary strings, one per hand.
    """
    summaries: list[str] = []
    for i, h in enumerate(hands, 1):
        board_str = " ".join(h.board) if h.board else "preflop"
        summaries.append(
            f"#{i}: {h.hero_hand} @ {h.hero_position} | "
            f"{h.street} [{board_str}] | "
            f"Pot: {h.pot_size_bb}bb | "
            f"ID: {h.hand_id}"
        )
    return summaries

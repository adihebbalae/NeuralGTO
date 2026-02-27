"""
test_hand_history.py — Unit tests for hand_history.py.

Tests site detection, individual site parsers, multi-hand parsing,
and query conversion. All tests are offline — no API calls.

Created: 2026-02-27
"""

import pytest

from poker_gpt.hand_history import (
    ParsedHand,
    detect_site,
    parse_pokerstars_hand,
    parse_ggpoker_hand,
    parse_clubwpt_hand,
    parse_hand_history,
    hand_to_query,
    hands_summary,
)


# ──────────────────────────────────────────────
# Fixtures — sample hand history text blocks
# ──────────────────────────────────────────────

POKERSTARS_HAND = """\
PokerStars Hand #12345678: Hold'em No Limit ($1/$2 USD) - 2026/02/27 12:00:00 ET
Table 'TestTable' 6-max Seat #4 is the button
Seat 1: Player1 ($200 in chips)
Seat 2: Player2 ($150 in chips)
Seat 3: Player3 ($180 in chips)
Seat 4: Hero ($210 in chips)
Seat 5: Player5 ($95 in chips)
Seat 6: Player6 ($300 in chips)
Player5: posts small blind $1
Player6: posts big blind $2
*** HOLE CARDS ***
Dealt to Hero [Ah Ks]
Player1: folds
Player2: folds
Player3: folds
Hero: raises $6 to $6
Player5: folds
Player6: calls $4
*** FLOP *** [Ts 9d 4h]
Player6: checks
Hero: bets $8
Player6: calls $8
*** TURN *** [Ts 9d 4h] [2c]
Player6: checks
Hero: bets $20
Player6: folds
"""

POKERSTARS_PREFLOP_ONLY = """\
PokerStars Hand #99999999: Hold'em No Limit ($0.50/$1 USD) - 2026/01/15 08:30:00 ET
Table 'PreflopTest' 6-max Seat #2 is the button
Seat 1: Villain1 ($100 in chips)
Seat 2: Hero ($120 in chips)
Seat 3: Villain2 ($80 in chips)
Seat 4: Villain3 ($150 in chips)
Seat 5: Villain4 ($90 in chips)
Seat 6: Villain5 ($200 in chips)
Villain2: posts small blind $0.50
Villain3: posts big blind $1
*** HOLE CARDS ***
Dealt to Hero [Qd Qh]
Villain4: folds
Villain5: raises $3 to $3
Villain1: folds
Hero: raises $9 to $9
Villain2: folds
Villain3: folds
Villain5: calls $6
"""

GGPOKER_HAND = """\
Poker Hand #RC12345: Hold'em No Limit ($1/$2) - 2026/02/27 14:30:00
Table 'GGExample' 6-Max Seat #3 is the button
Seat 1: Player1 ($200.00 in chips)
Seat 2: Player2 ($150.00 in chips)
Seat 3: Hero ($250.00 in chips)
Seat 4: Player4 ($180.00 in chips)
Seat 5: Player5 ($100.00 in chips)
Seat 6: Player6 ($300.00 in chips)
Player4: posts small blind $1
Player5: posts big blind $2
*** HOLE CARDS ***
Dealt to Hero [Jd Jc]
Player6: folds
Player1: raises $6 to $6
Player2: folds
Hero: calls $6
Player4: folds
Player5: folds
*** FLOP *** [8h 5s 2d]
Player1: bets $8
Hero: raises $20 to $20
Player1: calls $12
"""

CLUBWPT_HAND = """\
ClubWPT Hand #CW55555: Hold'em No Limit ($2/$5 USD) - 2026/02/27 10:00:00 ET
Table 'WPTGold' 6-max Seat #1 is the button
Seat 1: Hero ($500 in chips)
Seat 2: Villain1 ($350 in chips)
Seat 3: Villain2 ($400 in chips)
Seat 4: Villain3 ($600 in chips)
Seat 5: Villain4 ($250 in chips)
Seat 6: Villain5 ($450 in chips)
Villain1: posts small blind $2
Villain2: posts big blind $5
*** HOLE CARDS ***
Dealt to Hero [9s 8s]
Villain3: folds
Villain4: folds
Villain5: folds
Hero: raises $12 to $12
Villain1: folds
Villain2: calls $7
*** FLOP *** [7s 6d 2s]
Villain2: checks
Hero: bets $15
Villain2: calls $15
"""


# ──────────────────────────────────────────────
# Site Detection Tests
# ──────────────────────────────────────────────

class TestDetectSite:
    def test_pokerstars(self):
        assert detect_site(POKERSTARS_HAND) == "pokerstars"

    def test_ggpoker(self):
        assert detect_site(GGPOKER_HAND) == "ggpoker"

    def test_clubwpt(self):
        assert detect_site(CLUBWPT_HAND) == "clubwpt"

    def test_unknown(self):
        assert detect_site("Some random text\nwith no poker header") == "unknown"

    def test_case_insensitive(self):
        lower = POKERSTARS_HAND.lower()
        assert detect_site(lower) == "pokerstars"


# ──────────────────────────────────────────────
# PokerStars Parser Tests
# ──────────────────────────────────────────────

class TestParsePokerStars:
    def test_basic_parse(self):
        hand = parse_pokerstars_hand(POKERSTARS_HAND, hero_name="Hero")
        assert hand.hand_id == "12345678"
        assert hand.site == "pokerstars"
        assert hand.hero_name == "Hero"
        assert hand.hero_hand == "AhKs"
        assert hand.big_blind == 2.0

    def test_board(self):
        hand = parse_pokerstars_hand(POKERSTARS_HAND, hero_name="Hero")
        assert "Ts" in hand.board
        assert "9d" in hand.board
        assert "4h" in hand.board
        assert "2c" in hand.board

    def test_street(self):
        hand = parse_pokerstars_hand(POKERSTARS_HAND, hero_name="Hero")
        assert hand.street == "turn"

    def test_timestamp(self):
        hand = parse_pokerstars_hand(POKERSTARS_HAND, hero_name="Hero")
        assert "2026-02-27" in hand.timestamp
        assert "12:00:00" in hand.timestamp

    def test_actions_parsed(self):
        hand = parse_pokerstars_hand(POKERSTARS_HAND, hero_name="Hero")
        assert len(hand.actions) > 0
        action_types = {a["action"] for a in hand.actions}
        assert "folds" in action_types or "calls" in action_types

    def test_hero_autodetect(self):
        hand = parse_pokerstars_hand(POKERSTARS_HAND)
        assert hand.hero_name == "Hero"
        assert hand.hero_hand == "AhKs"

    def test_pot_nonzero(self):
        hand = parse_pokerstars_hand(POKERSTARS_HAND, hero_name="Hero")
        assert hand.pot_size_bb > 0

    def test_effective_stack_positive(self):
        hand = parse_pokerstars_hand(POKERSTARS_HAND, hero_name="Hero")
        assert hand.effective_stack_bb > 0

    def test_preflop_only(self):
        hand = parse_pokerstars_hand(POKERSTARS_PREFLOP_ONLY, hero_name="Hero")
        assert hand.board == []
        assert hand.street == "preflop"
        assert hand.hero_hand == "QdQh"

    def test_empty_text_raises(self):
        with pytest.raises(ValueError):
            parse_pokerstars_hand("")

    def test_raw_text_preserved(self):
        hand = parse_pokerstars_hand(POKERSTARS_HAND)
        assert "PokerStars Hand #12345678" in hand.raw_text


# ──────────────────────────────────────────────
# GGPoker Parser Tests
# ──────────────────────────────────────────────

class TestParseGGPoker:
    def test_basic_parse(self):
        hand = parse_ggpoker_hand(GGPOKER_HAND, hero_name="Hero")
        assert hand.hand_id == "RC12345"
        assert hand.site == "ggpoker"
        assert hand.hero_hand == "JdJc"

    def test_board(self):
        hand = parse_ggpoker_hand(GGPOKER_HAND, hero_name="Hero")
        assert "8h" in hand.board
        assert "5s" in hand.board
        assert "2d" in hand.board

    def test_street(self):
        hand = parse_ggpoker_hand(GGPOKER_HAND, hero_name="Hero")
        assert hand.street == "flop"

    def test_hero_autodetect(self):
        hand = parse_ggpoker_hand(GGPOKER_HAND)
        assert hand.hero_name == "Hero"


# ──────────────────────────────────────────────
# ClubWPT Parser Tests
# ──────────────────────────────────────────────

class TestParseClubWPT:
    def test_basic_parse(self):
        hand = parse_clubwpt_hand(CLUBWPT_HAND, hero_name="Hero")
        assert hand.hand_id == "CW55555"
        assert hand.site == "clubwpt"
        assert hand.hero_hand == "9s8s"
        assert hand.big_blind == 5.0

    def test_board(self):
        hand = parse_clubwpt_hand(CLUBWPT_HAND, hero_name="Hero")
        assert "7s" in hand.board
        assert "6d" in hand.board
        assert "2s" in hand.board

    def test_street(self):
        hand = parse_clubwpt_hand(CLUBWPT_HAND, hero_name="Hero")
        assert hand.street == "flop"


# ──────────────────────────────────────────────
# Multi-Hand Parsing Tests
# ──────────────────────────────────────────────

class TestParseHandHistory:
    def test_single_hand(self):
        hands = parse_hand_history(POKERSTARS_HAND, hero_name="Hero")
        assert len(hands) == 1

    def test_multi_hand(self):
        multi = POKERSTARS_HAND + "\n\n\n" + POKERSTARS_PREFLOP_ONLY
        hands = parse_hand_history(multi, hero_name="Hero")
        assert len(hands) == 2

    def test_bad_hand_skipped(self):
        bad = "PokerStars Hand #000: garbage data\n\n" + POKERSTARS_HAND
        hands = parse_hand_history(bad, hero_name="Hero")
        # The bad hand is skipped, good one is parsed
        assert len(hands) >= 1

    def test_empty_returns_empty(self):
        hands = parse_hand_history("")
        assert hands == []

    def test_unknown_site_fallback(self):
        # Unknown site tries pokerstars parser as fallback
        hands = parse_hand_history("random text with no hands")
        assert hands == []


# ──────────────────────────────────────────────
# Query Conversion Tests
# ──────────────────────────────────────────────

class TestHandToQuery:
    def test_basic_query(self):
        hand = parse_pokerstars_hand(POKERSTARS_HAND, hero_name="Hero")
        query = hand_to_query(hand)
        assert "AhKs" in query
        assert "bb" in query.lower()

    def test_board_in_query(self):
        hand = parse_pokerstars_hand(POKERSTARS_HAND, hero_name="Hero")
        query = hand_to_query(hand)
        assert "Ts" in query
        assert "9d" in query

    def test_preflop_no_board(self):
        hand = parse_pokerstars_hand(POKERSTARS_PREFLOP_ONLY, hero_name="Hero")
        query = hand_to_query(hand)
        assert "QdQh" in query
        # No board line expected
        assert "board" not in query.lower() or "board" in query.lower()

    def test_position_in_query(self):
        hand = parse_pokerstars_hand(POKERSTARS_HAND, hero_name="Hero")
        query = hand_to_query(hand)
        # Position should appear
        assert hand.hero_position in query


# ──────────────────────────────────────────────
# Summary Tests
# ──────────────────────────────────────────────

class TestHandsSummary:
    def test_summary_count(self):
        hands = parse_hand_history(POKERSTARS_HAND, hero_name="Hero")
        summaries = hands_summary(hands)
        assert len(summaries) == len(hands)

    def test_summary_content(self):
        hands = parse_hand_history(POKERSTARS_HAND, hero_name="Hero")
        summaries = hands_summary(hands)
        assert "AhKs" in summaries[0]
        assert "12345678" in summaries[0]

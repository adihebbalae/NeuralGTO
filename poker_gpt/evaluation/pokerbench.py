"""
pokerbench.py — PokerBench dataset loader for NeuralGTO evaluation.

Downloads, caches, and parses the PokerBench test sets (AAAI 2025,
Zhuang et al.) from HuggingFace. Returns normalized dataclasses
ready for pipeline evaluation.

Created: 2026-02-27

DOCUMENTATION:
    Source: https://huggingface.co/datasets/RZ412/PokerBench
    Paper:  https://arxiv.org/abs/2501.08328

    The PokerBench dataset contains 11k test scenarios (1k preflop + 10k postflop)
    with solver-computed optimal decisions. Each scenario is a natural language
    game description paired with the correct action (check, fold, call,
    bet <amount>, raise <amount>).

    Usage:
        from poker_gpt.evaluation.pokerbench import load_test_set, PBScenario
        scenarios = load_test_set("preflop")   # 1000 PBScenario objects
        scenarios = load_test_set("postflop")  # 10000 PBScenario objects
        scenarios = load_test_set("all")       # 11000 combined

    The loader downloads once and caches to _data/pokerbench/.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HF_BASE = "https://huggingface.co/datasets/RZ412/PokerBench/resolve/main/"

_FILES = {
    "preflop": "preflop_1k_test_set_prompt_and_label.json",
    "postflop": "postflop_10k_test_set_prompt_and_label.json",
}

_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "_data" / "pokerbench"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PBScenario:
    """A single PokerBench evaluation scenario.

    Attributes:
        instruction: Full natural-language game description (PokerBench prompt).
        ground_truth: Raw ground truth string from PokerBench (e.g. "raise 11").
        action_category: Normalized action category: "check", "call", "fold",
            "raise", or "bet". Bet and raise are distinct in PokerBench but
            both represent aggression.
        bet_size: The bet/raise amount if applicable, else None.
        street: "preflop", "flop", "turn", or "river".
        hero_position: Hero's position (UTG, HJ, CO, BTN, SB, BB).
        hero_holding: Hero's hole cards in natural language form.
        pot_size: Current pot size in chips.
        index: Original index in the PokerBench test set.
    """

    instruction: str
    ground_truth: str
    action_category: str
    bet_size: float | None = None
    street: str = "unknown"
    hero_position: str = "unknown"
    hero_holding: str = ""
    pot_size: float = 0.0
    index: int = 0


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_POS_RE = re.compile(r"your position is (\w+)", re.IGNORECASE)
_HOLDING_RE = re.compile(r"your holding is \[(.+?)\]", re.IGNORECASE)
_POT_RE = re.compile(r"current pot size is ([\d.]+) chips", re.IGNORECASE)

# Street detection: look for "The river comes", "The turn comes", "The flop comes"
_RIVER_RE = re.compile(r"the river comes", re.IGNORECASE)
_TURN_RE = re.compile(r"the turn comes", re.IGNORECASE)
_FLOP_RE = re.compile(r"the flop comes", re.IGNORECASE)


def _parse_action(raw: str) -> tuple[str, float | None]:
    """Parse a PokerBench output string into (action_category, bet_size).

    Args:
        raw: Raw output string like "call", "fold", "raise 11", "bet 4".

    Returns:
        Tuple of (category, size). Category is one of: "check", "call",
        "fold", "raise", "bet". Size is float for raise/bet, None otherwise.
    """
    parts = raw.strip().lower().split()
    if not parts:
        return ("unknown", None)

    action = parts[0]
    size = None
    if len(parts) > 1:
        try:
            size = float(parts[1])
        except ValueError:
            pass

    if action in ("check", "call", "fold", "raise", "bet"):
        return (action, size)

    return ("unknown", None)


def _detect_street(instruction: str, is_preflop_set: bool) -> str:
    """Detect the current street from the instruction text.

    Args:
        instruction: Full PokerBench instruction text.
        is_preflop_set: Whether this came from the preflop test set.

    Returns:
        One of "preflop", "flop", "turn", "river".
    """
    if is_preflop_set:
        return "preflop"
    if _RIVER_RE.search(instruction):
        return "river"
    if _TURN_RE.search(instruction):
        return "turn"
    if _FLOP_RE.search(instruction):
        return "flop"
    return "unknown"


def _extract_field(pattern: re.Pattern, text: str, default: str = "") -> str:
    """Extract a regex match from text, returning default if not found."""
    m = pattern.search(text)
    return m.group(1) if m else default


def _parse_scenario(
    entry: dict,
    index: int,
    is_preflop: bool,
) -> PBScenario:
    """Parse a single PokerBench JSON entry into a PBScenario.

    Args:
        entry: Dict with "instruction" and "output" keys.
        index: Index in the test set.
        is_preflop: Whether this is from the preflop test set.

    Returns:
        Parsed PBScenario dataclass.
    """
    instruction = entry.get("instruction", "")
    raw_output = entry.get("output", "")

    action_cat, bet_size = _parse_action(raw_output)
    street = _detect_street(instruction, is_preflop)
    position = _extract_field(_POS_RE, instruction, "unknown")
    holding = _extract_field(_HOLDING_RE, instruction, "")

    pot_str = _extract_field(_POT_RE, instruction, "0")
    try:
        pot = float(pot_str)
    except ValueError:
        pot = 0.0

    return PBScenario(
        instruction=instruction,
        ground_truth=raw_output,
        action_category=action_cat,
        bet_size=bet_size,
        street=street,
        hero_position=position.upper(),
        hero_holding=holding,
        pot_size=pot,
        index=index,
    )


# ---------------------------------------------------------------------------
# Download / cache
# ---------------------------------------------------------------------------

def _ensure_cached(split: str) -> Path:
    """Download PokerBench test set if not already cached.

    Args:
        split: "preflop" or "postflop".

    Returns:
        Path to the cached JSON file.

    Raises:
        ValueError: If split is not "preflop" or "postflop".
        ConnectionError: If download fails.
    """
    if split not in _FILES:
        raise ValueError(f"Unknown split: {split!r}. Use 'preflop' or 'postflop'.")

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    local_path = _CACHE_DIR / _FILES[split]

    if local_path.exists():
        logger.debug("PokerBench %s test set cached at %s", split, local_path)
        return local_path

    url = _HF_BASE + _FILES[split]
    # SECURITY: Reject non-HTTPS schemes (prevents file:// local file reads)
    if not url.startswith("https://"):
        raise ValueError(f"Only HTTPS URLs are allowed, got: {url}")
    logger.info("Downloading PokerBench %s test set from %s ...", split, url)

    req = urllib.request.Request(url, headers={"User-Agent": "NeuralGTO/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            data = response.read()
    except Exception as e:
        raise ConnectionError(
            f"Failed to download PokerBench {split} test set from {url}: {e}"
        ) from e

    local_path.write_bytes(data)
    logger.info("Saved PokerBench %s test set to %s (%d bytes)", split, local_path, len(data))
    return local_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_test_set(
    split: Literal["preflop", "postflop", "all"] = "all",
    limit: int | None = None,
) -> list[PBScenario]:
    """Load PokerBench test scenarios.

    Downloads from HuggingFace on first call, then uses local cache.

    Args:
        split: Which test set to load. "preflop" (1k), "postflop" (10k),
            or "all" (11k combined).
        limit: Max number of scenarios to return (for quick testing).
            Applied after combining splits.

    Returns:
        List of PBScenario dataclasses, sorted by (split, index).

    Raises:
        ConnectionError: If download fails on first run.
    """
    scenarios: list[PBScenario] = []

    splits_to_load = ["preflop", "postflop"] if split == "all" else [split]

    for s in splits_to_load:
        path = _ensure_cached(s)
        with open(path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        is_preflop = s == "preflop"
        for i, entry in enumerate(raw_data):
            scenarios.append(_parse_scenario(entry, i, is_preflop))

    if limit is not None:
        scenarios = scenarios[:limit]

    return scenarios


def action_matches(predicted: str, ground_truth: str) -> bool:
    """Check if a predicted action matches the ground truth category.

    Normalizes both to category level: check, call, fold, or aggression
    (bet/raise are treated as equivalent since NeuralGTO doesn't distinguish).

    Args:
        predicted: Predicted action string (e.g. "Raise", "call", "Check").
        ground_truth: Ground truth from PokerBench (e.g. "raise 11", "bet 4").

    Returns:
        True if the action categories match.
    """
    pred_cat = predicted.strip().lower().split()[0] if predicted.strip() else ""
    truth_cat = ground_truth.strip().lower().split()[0] if ground_truth.strip() else ""

    # Normalize: NeuralGTO uses "raise" for all aggression;
    # PokerBench distinguishes "bet" (first to put money in) vs "raise"
    # Both are aggressive actions, so we treat them as equivalent.
    aggression = {"bet", "raise"}
    if pred_cat in aggression and truth_cat in aggression:
        return True

    return pred_cat == truth_cat


def dataset_stats(scenarios: list[PBScenario]) -> dict:
    """Compute summary statistics for a loaded dataset.

    Args:
        scenarios: List of PBScenario objects.

    Returns:
        Dict with counts by street, position, and action category.
    """
    from collections import Counter

    stats: dict = {
        "total": len(scenarios),
        "by_street": dict(Counter(s.street for s in scenarios).most_common()),
        "by_position": dict(Counter(s.hero_position for s in scenarios).most_common()),
        "by_action": dict(Counter(s.action_category for s in scenarios).most_common()),
    }
    return stats

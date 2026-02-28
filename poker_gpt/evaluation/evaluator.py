"""
evaluator.py — PokerBench evaluation runner for NeuralGTO.

Runs the NeuralGTO pipeline (or LLM-only baseline) against PokerBench
scenarios and computes accuracy metrics. Designed for both paper results
and ongoing quality tracking.

Created: 2026-02-27

DOCUMENTATION:
    Three evaluation modes:
    1. "gemini_direct" — Send PokerBench instruction direct to Gemini, ask
       for optimal action. This is the LLM baseline for the paper.
    2. "neuralgto_fast" — Run through full NeuralGTO pipeline in fast mode
       (LLM-only with NeuralGTO's enhanced prompting + range estimation).
    3. "neuralgto_solver" — Full pipeline with TexasSolver (postflop only,
       very slow — use small samples).

    Usage:
        from poker_gpt.evaluation.evaluator import run_evaluation
        results = run_evaluation(
            mode="gemini_direct",
            split="preflop",
            limit=100,
        )
        print(results.summary())
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from google import genai
from google.genai import types

from poker_gpt import config
from poker_gpt.evaluation.pokerbench import (
    PBScenario,
    action_matches,
    load_test_set,
)
from poker_gpt.poker_types import ScenarioData, ActionEntry
from poker_gpt.preflop_lookup import lookup_preflop_strategy, is_preflop_lookup_available

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class EvalResult:
    """Result of evaluating a single PokerBench scenario.

    Attributes:
        scenario: The original PokerBench scenario.
        predicted_action: The action predicted by NeuralGTO / Gemini.
        predicted_raw: Raw model output text.
        correct: Whether the prediction matches ground truth.
        latency_s: Time taken in seconds.
        error: Error message if prediction failed.
    """
    scenario: PBScenario
    predicted_action: str = ""
    predicted_raw: str = ""
    correct: bool = False
    latency_s: float = 0.0
    error: str = ""


@dataclass
class EvalReport:
    """Aggregated evaluation report.

    Attributes:
        mode: Evaluation mode used.
        split: Dataset split evaluated.
        results: Individual evaluation results.
        total: Total scenarios evaluated.
        correct: Number of correct predictions.
        errors: Number of scenarios that errored.
        accuracy: Overall accuracy (0.0 - 1.0).
        by_street: Accuracy breakdown by street.
        by_action: Accuracy breakdown by ground truth action category.
        by_position: Accuracy breakdown by hero position.
        confusion: Confusion matrix as {true_cat: {pred_cat: count}}.
        total_time_s: Total wall clock time.
        mean_latency_s: Mean per-scenario latency.
    """
    mode: str = ""
    split: str = ""
    results: list[EvalResult] = field(default_factory=list)
    total: int = 0
    correct: int = 0
    errors: int = 0
    accuracy: float = 0.0
    by_street: dict[str, dict] = field(default_factory=dict)
    by_action: dict[str, dict] = field(default_factory=dict)
    by_position: dict[str, dict] = field(default_factory=dict)
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)
    total_time_s: float = 0.0
    mean_latency_s: float = 0.0
    # Coverage metrics (for lookup mode)
    matched: int = 0       # Scenarios where lookup found a match
    no_match: int = 0      # Scenarios where lookup had no matching entry
    matched_accuracy: float = 0.0  # Accuracy on matched scenarios only

    def summary(self) -> str:
        """Return a human-readable summary of the evaluation."""
        lines = [
            f"=== PokerBench Evaluation Report ===",
            f"Mode: {self.mode}",
            f"Split: {self.split}",
            f"Total: {self.total}  Correct: {self.correct}  "
            f"Errors: {self.errors}",
            f"Accuracy: {self.accuracy:.1%}",
        ]
        if self.matched > 0 or self.no_match > 0:
            lines.append("")
            lines.append("--- Coverage ---")
            lines.append(
                f"  Matched:   {self.matched}/{self.total} "
                f"= {self.matched / max(self.total, 1):.1%}"
            )
            lines.append(
                f"  No match:  {self.no_match}/{self.total} "
                f"= {self.no_match / max(self.total, 1):.1%}"
            )
            lines.append(
                f"  Accuracy on matched: {self.matched_accuracy:.1%}"
            )
        lines.extend([
            f"Time: {self.total_time_s:.1f}s  "
            f"Mean latency: {self.mean_latency_s:.2f}s",
            "",
            "--- By Street ---",
        ])
        for street, stats in sorted(self.by_street.items()):
            lines.append(
                f"  {street:10s}: {stats['correct']}/{stats['total']} "
                f"= {stats['accuracy']:.1%}"
            )
        lines.append("")
        lines.append("--- By Ground Truth Action ---")
        for action, stats in sorted(self.by_action.items()):
            lines.append(
                f"  {action:10s}: {stats['correct']}/{stats['total']} "
                f"= {stats['accuracy']:.1%}"
            )
        lines.append("")
        lines.append("--- By Position ---")
        for pos, stats in sorted(self.by_position.items()):
            lines.append(
                f"  {pos:6s}: {stats['correct']}/{stats['total']} "
                f"= {stats['accuracy']:.1%}"
            )
        lines.append("")
        lines.append("--- Confusion Matrix ---")
        all_cats = sorted(
            {c for row in self.confusion.values() for c in row}
            | set(self.confusion.keys())
        )
        header = "           " + "  ".join(f"{c:>8s}" for c in all_cats)
        lines.append(header)
        for true_cat in all_cats:
            row = self.confusion.get(true_cat, {})
            cells = "  ".join(f"{row.get(c, 0):8d}" for c in all_cats)
            lines.append(f"  {true_cat:>8s}: {cells}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict (excludes individual results)."""
        d = {
            "mode": self.mode,
            "split": self.split,
            "total": self.total,
            "correct": self.correct,
            "errors": self.errors,
            "accuracy": self.accuracy,
            "by_street": self.by_street,
            "by_action": self.by_action,
            "by_position": self.by_position,
            "confusion": self.confusion,
            "total_time_s": self.total_time_s,
            "mean_latency_s": self.mean_latency_s,
        }
        if self.matched > 0 or self.no_match > 0:
            d["matched"] = self.matched
            d["no_match"] = self.no_match
            d["matched_accuracy"] = self.matched_accuracy
        return d


# ---------------------------------------------------------------------------
# NeuralGTO lookup evaluation (offline — no API calls)
# ---------------------------------------------------------------------------

# Map natural-language rank names → single char
_RANK_NL_MAP = {
    "ace": "A", "king": "K", "queen": "Q", "jack": "J", "ten": "T",
    "nine": "9", "eight": "8", "seven": "7", "six": "6", "five": "5",
    "four": "4", "three": "3", "two": "2", "deuce": "2",
    # Single-char/digit forms (already short)
    "a": "A", "k": "K", "q": "Q", "j": "J", "t": "T",
}

# Map natural-language suit names → single char
_SUIT_NL_MAP = {
    "heart": "h", "hearts": "h", "diamond": "d", "diamonds": "d",
    "club": "c", "clubs": "c", "spade": "s", "spades": "s",
}

# Regex to parse "King of Heart" style card names
_CARD_NL_RE = re.compile(
    r"(ace|king|queen|jack|ten|nine|eight|seven|six|five|four|three|two|deuce)"
    r"\s+of\s+(heart|hearts|diamond|diamonds|club|clubs|spade|spades)",
    re.IGNORECASE,
)

# Regex to parse PokerBench preflop action strings
# e.g. "HJ raise 2.0, CO call, SB all in"
_ACTION_RE = re.compile(
    r"(UTG|HJ|CO|BTN|SB|BB)\s+(raise|call|fold|all\s*in|check)\s*([\d]+\.?\d*)?",
    re.IGNORECASE,
)

# Available bet sizes in our pre-solved range tree
_TREE_SIZES = [2.5, 3.0, 8.5, 9.0, 11.0, 13.0, 20.0, 21.0, 22.0, 24.0, 25.0]

# Out-of-position positions for context-aware sizing
_OOP_POSITIONS = {"SB", "BB"}


def _snap_to_tree_size(amount_bb: float, is_sb_open: bool = False) -> float:
    """Map a PokerBench raise size to the nearest size in our tree.

    Args:
        amount_bb: The PB raise amount in big blinds.
        is_sb_open: True if this is an SB opening raise (uses 3.0bb).

    Returns:
        The nearest available size from _TREE_SIZES.
    """
    if is_sb_open:
        return 3.0
    return min(_TREE_SIZES, key=lambda s: abs(s - amount_bb))


def _context_snap_size(
    raw_amount: float,
    raiser_pos: str,
    raise_number: int,
    had_callers_before: bool,
    opener_pos: str | None,
    prev_raise_size: float | None,
) -> float:
    """Map a raise amount to the correct tree size for its game-tree context.

    Our pre-solved range tree uses specific sizes at each decision point.
    Global nearest-neighbor snapping fails because the same amount means
    different things in different contexts (e.g. 9.0 is a BB 3-bet vs SB
    open, but SB 3-bet vs any other open is 11.0).

    Tree sizing conventions (from file analysis):
        Open (non-SB):        2.5bb
        SB open:              3.0bb
        IP 3-bet (BTN/CO/MP): 8.5bb
        OOP 3-bet (SB/BB):    11.0bb (vs non-SB), 9.0bb (BB vs SB)
        Squeeze (after call):  13.0bb
        4-bet (vs IP 3-bet):   22.0bb
        4-bet (vs OOP 3-bet):  24.0bb
        Cold 4-bet (non-SB):   20.0bb
        Cold 4-bet (SB):       21.0bb
        5-bet / after squeeze: 25.0bb

    Args:
        raw_amount: PokerBench raise amount in bb.
        raiser_pos: Position of the raiser (PB format, e.g. "HJ").
        raise_number: 1=open, 2=3-bet, 3=4-bet, 4+=5-bet.
        had_callers_before: True if someone called between last raise
            and this one (squeeze indicator).
        opener_pos: Position of the original opener (for 4-bet context).
        prev_raise_size: Size of the previous raise (to distinguish
            4-bet vs IP 3-bet from 4-bet vs OOP 3-bet).

    Returns:
        The tree size for this action context.
    """
    pos = raiser_pos.upper()

    # --- Open ---
    if raise_number == 1:
        return 3.0 if pos == "SB" else 2.5

    # --- 3-bet (or squeeze) ---
    if raise_number == 2:
        if had_callers_before:
            return 13.0  # squeeze
        if pos in _OOP_POSITIONS:
            if opener_pos and opener_pos.upper() == "SB":
                return 9.0  # BB 3-bet vs SB open
            return 11.0  # OOP 3-bet vs non-SB
        return 8.5  # IP 3-bet

    # --- 4-bet ---
    if raise_number == 3:
        if had_callers_before:
            return 25.0  # 4-bet squeeze (rare, into multiway)
        # Original opener re-raising (regular 4-bet)
        if opener_pos and pos.upper() == opener_pos.upper():
            # 4-bet by opener: size depends on 3-bet sizing
            if prev_raise_size is not None and prev_raise_size <= 9.0:
                return 22.0  # vs IP / small 3-bet
            return 24.0  # vs OOP 3-bet (11.0bb)
        # Cold 4-bet by a different player
        if pos == "SB":
            return 21.0
        return 20.0

    # --- 5-bet+ ---
    return 25.0


def _holding_nl_to_cards(nl_holding: str) -> str | None:
    """Convert PokerBench NL holding to card notation.

    Args:
        nl_holding: e.g. "King of Heart and King of Club"

    Returns:
        e.g. "KhKc", or None if unparseable.
    """
    cards = _CARD_NL_RE.findall(nl_holding)
    if len(cards) != 2:
        return None

    result = ""
    for rank_nl, suit_nl in cards:
        rank = _RANK_NL_MAP.get(rank_nl.lower())
        suit = _SUIT_NL_MAP.get(suit_nl.lower())
        if rank is None or suit is None:
            return None
        result += rank + suit
    return result


def _parse_pb_preflop_actions(instruction: str, hero_pos: str) -> list[ActionEntry]:
    """Extract preflop action history from PokerBench instruction text.

    Parses "Before the flop, HJ raise 2.0, CO call, ..." into ActionEntry list.
    Normalizes raise sizes to match our pre-solved range tree sizes.

    Args:
        instruction: Full PokerBench instruction text.
        hero_pos: Hero's position (uppercase).

    Returns:
        List of ActionEntry for all preflop actions in the instruction.
    """
    # Extract action text between "Before the flop," and "Assume" or "Now"
    # Use the region between these markers to avoid decimal-point regex issues.
    start = instruction.lower().find("before the flop,")
    if start == -1:
        return []

    # Find the end marker
    text_from_start = instruction[start:]
    end_markers = ["Assume that", "Now it is"]
    end_pos = len(text_from_start)
    for marker in end_markers:
        idx = text_from_start.find(marker)
        if idx == -1:
            idx = text_from_start.lower().find(marker.lower())
        if idx != -1 and idx < end_pos:
            end_pos = idx

    action_text = text_from_start[:end_pos]

    # Check if it's "no action yet" or "there has been no action"
    if "no action" in action_text.lower():
        return []

    entries: list[ActionEntry] = []
    raise_count = 0          # 0=none, 1=open, 2=3bet, 3=4bet, ...
    callers_since_raise = 0  # callers since the last raise (squeeze detector)
    opener_pos: str | None = None   # who made the original open
    prev_raise_size: float | None = None  # size of last raise

    for match in _ACTION_RE.finditer(action_text):
        pos = match.group(1).upper()
        action_raw = match.group(2).lower().replace(" ", "")
        amount_str = match.group(3)

        # Map action names
        if action_raw == "allin":
            action = "allin"
        elif action_raw == "raise":
            action = "raise"
        elif action_raw == "call":
            action = "call"
        elif action_raw == "fold":
            action = "fold"
        elif action_raw == "check":
            action = "check"
        else:
            action = action_raw

        amount_bb = None
        if action == "raise" and amount_str:
            raw_amount = float(amount_str)
            raise_count += 1
            amount_bb = _context_snap_size(
                raw_amount,
                raiser_pos=pos,
                raise_number=raise_count,
                had_callers_before=callers_since_raise > 0,
                opener_pos=opener_pos,
                prev_raise_size=prev_raise_size,
            )
            if raise_count == 1:
                opener_pos = pos
            prev_raise_size = amount_bb
            callers_since_raise = 0
        elif action == "call":
            callers_since_raise += 1

        entries.append(ActionEntry(
            position=pos,
            action=action,
            amount_bb=amount_bb,
            street="preflop",
        ))

    return entries


def _pb_to_scenario(scenario: PBScenario) -> ScenarioData | None:
    """Convert a PokerBench preflop scenario to ScenarioData.

    Args:
        scenario: Parsed PBScenario.

    Returns:
        ScenarioData suitable for lookup_preflop_strategy(), or None.
    """
    # Convert NL holding to card notation
    hero_hand = _holding_nl_to_cards(scenario.hero_holding)
    if not hero_hand:
        return None

    hero_pos = scenario.hero_position.upper()
    if not hero_pos or hero_pos == "UNKNOWN":
        return None

    # Parse action history from instruction
    action_history = _parse_pb_preflop_actions(
        scenario.instruction, hero_pos
    )

    return ScenarioData(
        hero_hand=hero_hand,
        hero_position=hero_pos,
        board="",
        pot_size_bb=scenario.pot_size,
        effective_stack_bb=100.0,  # PokerBench is always 100bb
        current_street="preflop",
        oop_range="",
        ip_range="",
        hero_is_ip=False,  # Not used by preflop lookup
        action_history=action_history,
    )


def _predict_neuralgto_lookup(
    scenario: PBScenario,
) -> tuple[str, str]:
    """Get NeuralGTO preflop lookup prediction (offline, no API).

    Converts PBScenario → ScenarioData → lookup_preflop_strategy().

    Args:
        scenario: The PokerBench scenario.

    Returns:
        Tuple of (action_category, raw_description).
    """
    sd = _pb_to_scenario(scenario)
    if sd is None:
        return ("unknown", "[parse error: could not convert scenario]")

    result = lookup_preflop_strategy(sd)
    if result is None:
        return ("unknown", "[no matching lookup table entry]")

    # Map lookup best_action to PokerBench-style categories
    best = result.best_action.lower()
    if best.startswith("raise"):
        # Extract size if present: "Raise 2.5bb" → "raise 2.5"
        size_match = re.search(r"([\d.]+)", result.best_action)
        if size_match:
            return ("raise", f"raise {size_match.group(1)}")
        return ("raise", "raise")
    elif best == "call":
        return ("call", "call")
    elif best == "fold":
        return ("fold", "fold")
    elif best == "check":
        return ("check", "check")
    elif best.startswith("all"):
        return ("raise", "raise all-in")
    else:
        return (best, best)


# ---------------------------------------------------------------------------
# Gemini direct evaluation
# ---------------------------------------------------------------------------

_DIRECT_SYSTEM_PROMPT = """You are a poker decision engine. Given a No Limit Texas Hold'em game scenario, output ONLY the optimal action.

Rules:
- Output exactly one of: check, call, fold, raise <amount>, or bet <amount>
- Use lowercase
- If raising or betting, include the amount in chips (e.g. "raise 12" or "bet 5")
- Do NOT explain your reasoning
- Do NOT include any other text

Example outputs:
check
call
fold
raise 11
bet 4"""


def _normalize_prediction(raw: str) -> tuple[str, str]:
    """Normalize a raw model output to an action category.

    Handles common Gemini output variations: "Call", "I would fold",
    "The optimal action is check", markdown formatting, etc.

    Args:
        raw: Raw model output text.

    Returns:
        Tuple of (action_category, cleaned_raw).
    """
    text = raw.strip().lower()
    # Strip markdown bold/italic
    text = re.sub(r"[*_`]", "", text)
    # Strip common prefixes
    text = re.sub(
        r"^(the optimal action is|my action is|i would|i should|action:)\s*",
        "",
        text,
    )
    text = text.strip().rstrip(".")

    parts = text.split()
    if not parts:
        return ("unknown", raw)

    action = parts[0]
    if action in ("check", "call", "fold", "raise", "bet"):
        return (action, text)

    # Fuzzy matching for common variations
    for keyword in ("fold", "call", "check", "raise", "bet"):
        if keyword in text:
            return (keyword, text)

    return ("unknown", raw)


def _predict_gemini_direct(
    scenario: PBScenario,
    client: genai.Client,
) -> tuple[str, str]:
    """Get Gemini's direct prediction for a PokerBench scenario.

    Args:
        scenario: The PokerBench scenario.
        client: Gemini API client.

    Returns:
        Tuple of (action_category, raw_output).
    """
    response = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=scenario.instruction + "\n\nYour optimal action is:",
        config=types.GenerateContentConfig(
            system_instruction=_DIRECT_SYSTEM_PROMPT,
            temperature=0.0,
            max_output_tokens=1024,
        ),
    )
    raw = response.text.strip().lower() if response.text else ""
    return _normalize_prediction(raw)


# ---------------------------------------------------------------------------
# NeuralGTO pipeline evaluation (fast mode)
# ---------------------------------------------------------------------------

_NEURALGTO_EVAL_SYSTEM_PROMPT = """You are a GTO poker advisor. Given a poker scenario, determine the single optimal action.

You have deep knowledge of:
- GTO opening ranges for 6-max NLHE (100bb deep)
- Preflop raise/3bet/4bet strategies by position
- Postflop strategies: c-betting, check-raising, barreling, bluff-catching
- Pot odds, implied odds, equity realization
- Range advantage, nut advantage, board texture analysis
- Blocker effects and range construction principles

Output ONLY the action — one of: check, call, fold, raise <amount>, or bet <amount>
Use lowercase. Include bet/raise amounts in chips.
Do NOT explain."""


def _predict_neuralgto_fast(
    scenario: PBScenario,
    client: genai.Client,
) -> tuple[str, str]:
    """Get NeuralGTO fast-mode prediction (enhanced LLM prompting).

    Uses NeuralGTO's poker-theory-enhanced system prompt instead of
    vanilla Gemini. This measures the value of better prompting.

    Args:
        scenario: The PokerBench scenario.
        client: Gemini API client.

    Returns:
        Tuple of (action_category, raw_output).
    """
    response = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=scenario.instruction + "\n\nYour optimal action is:",
        config=types.GenerateContentConfig(
            system_instruction=_NEURALGTO_EVAL_SYSTEM_PROMPT,
            temperature=0.0,
            max_output_tokens=1024,
        ),
    )
    raw = response.text.strip().lower() if response.text else ""
    return _normalize_prediction(raw)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _aggregate(
    results: list[EvalResult],
    mode: str,
    split: str,
    total_time: float,
) -> EvalReport:
    """Aggregate individual results into an EvalReport.

    Args:
        results: List of EvalResult objects.
        mode: Evaluation mode name.
        split: Dataset split name.
        total_time: Total wall clock time in seconds.

    Returns:
        Populated EvalReport.
    """
    report = EvalReport(mode=mode, split=split)
    report.results = results
    report.total = len(results)
    report.correct = sum(1 for r in results if r.correct)
    report.errors = sum(1 for r in results if r.error)
    report.accuracy = report.correct / max(report.total, 1)
    report.total_time_s = total_time
    report.mean_latency_s = (
        sum(r.latency_s for r in results) / max(report.total, 1)
    )

    # By street
    streets: dict[str, list[EvalResult]] = {}
    for r in results:
        streets.setdefault(r.scenario.street, []).append(r)
    for street, rs in streets.items():
        correct = sum(1 for r in rs if r.correct)
        report.by_street[street] = {
            "total": len(rs),
            "correct": correct,
            "accuracy": correct / max(len(rs), 1),
        }

    # By ground truth action
    actions: dict[str, list[EvalResult]] = {}
    for r in results:
        cat = r.scenario.action_category
        # Merge bet+raise into "aggression" for reporting
        if cat in ("bet", "raise"):
            cat = "bet/raise"
        actions.setdefault(cat, []).append(r)
    for action, rs in actions.items():
        correct = sum(1 for r in rs if r.correct)
        report.by_action[action] = {
            "total": len(rs),
            "correct": correct,
            "accuracy": correct / max(len(rs), 1),
        }

    # By position
    positions: dict[str, list[EvalResult]] = {}
    for r in results:
        positions.setdefault(r.scenario.hero_position, []).append(r)
    for pos, rs in positions.items():
        correct = sum(1 for r in rs if r.correct)
        report.by_position[pos] = {
            "total": len(rs),
            "correct": correct,
            "accuracy": correct / max(len(rs), 1),
        }

    # Confusion matrix
    confusion: dict[str, dict[str, int]] = {}
    for r in results:
        if r.error:
            continue
        true_cat = r.scenario.action_category
        pred_cat = r.predicted_action
        # Normalize
        if true_cat in ("bet", "raise"):
            true_cat = "bet/raise"
        if pred_cat in ("bet", "raise"):
            pred_cat = "bet/raise"
        row = confusion.setdefault(true_cat, {})
        row[pred_cat] = row.get(pred_cat, 0) + 1
    report.confusion = confusion

    return report


# ---------------------------------------------------------------------------
# Main evaluation runner
# ---------------------------------------------------------------------------

def run_evaluation(
    mode: Literal["gemini_direct", "neuralgto_fast", "neuralgto_lookup"] = "neuralgto_lookup",
    split: Literal["preflop", "postflop", "all"] = "preflop",
    limit: int | None = None,
    progress_callback: callable | None = None,
    save_results: bool = True,
) -> EvalReport:
    """Run PokerBench evaluation.

    Downloads test data on first call, runs predictions, and computes
    accuracy metrics.

    Args:
        mode: Evaluation mode.
            "neuralgto_lookup" — Preflop lookup tables (offline, instant).
            "gemini_direct" — Vanilla Gemini (LLM baseline for paper).
            "neuralgto_fast" — Enhanced poker-theory prompting.
        split: Dataset split to evaluate.
        limit: Max scenarios to evaluate (for quick tests).
        progress_callback: Optional callable(current, total, result) for
            progress updates.
        save_results: Whether to save results JSON to _data/pokerbench/.

    Returns:
        EvalReport with all metrics.
    """
    logger.info("Loading PokerBench %s test set...", split)
    scenarios = load_test_set(split, limit=limit)
    logger.info("Loaded %d scenarios", len(scenarios))

    # ---- neuralgto_lookup: offline, no API key needed ----
    if mode == "neuralgto_lookup":
        if not is_preflop_lookup_available():
            raise RuntimeError(
                "Preflop lookup tables not found. Ensure solver_bin/ "
                "contains the Pio range files."
            )
        return _run_lookup_evaluation(
            scenarios, split, progress_callback, save_results
        )

    # ---- LLM-based modes: require Gemini API key ----
    from dotenv import load_dotenv
    load_dotenv(override=True)
    api_key = config.GEMINI_API_KEY

    client = genai.Client(api_key=api_key)

    predict_fn = {
        "gemini_direct": _predict_gemini_direct,
        "neuralgto_fast": _predict_neuralgto_fast,
    }.get(mode)

    if predict_fn is None:
        raise ValueError(f"Unknown evaluation mode: {mode!r}")

    results: list[EvalResult] = []
    start_time = time.time()

    for i, scenario in enumerate(scenarios):
        t0 = time.time()
        result = EvalResult(scenario=scenario)

        try:
            action_cat, raw = predict_fn(scenario, client)
            result.predicted_action = action_cat
            result.predicted_raw = raw
            result.correct = action_matches(raw, scenario.ground_truth)
        except Exception as e:
            result.error = str(e)
            logger.warning("Error on scenario %d: %s", i, e)

        result.latency_s = time.time() - t0
        results.append(result)

        if progress_callback:
            progress_callback(i + 1, len(scenarios), result)

        # Rate limiting for API modes
        if i < len(scenarios) - 1:
            time.sleep(0.5)

    total_time = time.time() - start_time
    report = _aggregate(results, mode, split, total_time)

    if save_results:
        _save_report(report)

    return report


def _run_lookup_evaluation(
    scenarios: list[PBScenario],
    split: str,
    progress_callback: callable | None,
    save_results: bool,
) -> EvalReport:
    """Run offline preflop lookup evaluation (no API calls).

    Args:
        scenarios: PokerBench scenarios to evaluate.
        split: Dataset split name.
        progress_callback: Optional progress callback.
        save_results: Whether to save results JSON.

    Returns:
        EvalReport with all metrics.
    """
    results: list[EvalResult] = []
    start_time = time.time()

    for i, scenario in enumerate(scenarios):
        t0 = time.time()
        result = EvalResult(scenario=scenario)

        try:
            action_cat, raw = _predict_neuralgto_lookup(scenario)
            result.predicted_action = action_cat
            result.predicted_raw = raw
            result.correct = action_matches(raw, scenario.ground_truth)
        except Exception as e:
            result.error = str(e)
            logger.warning("Error on scenario %d: %s", i, e)

        result.latency_s = time.time() - t0
        results.append(result)

        if progress_callback:
            progress_callback(i + 1, len(scenarios), result)

    total_time = time.time() - start_time
    report = _aggregate(results, "neuralgto_lookup", split, total_time)

    # Compute coverage stats
    no_match_marker = "[no matching lookup table entry]"
    parse_error_marker = "[parse error"
    report.no_match = sum(
        1 for r in results
        if r.predicted_raw.startswith(no_match_marker)
        or r.predicted_raw.startswith(parse_error_marker)
    )
    report.matched = report.total - report.no_match - report.errors
    matched_correct = sum(
        1 for r in results
        if r.correct
        and not r.predicted_raw.startswith(no_match_marker)
        and not r.predicted_raw.startswith(parse_error_marker)
        and not r.error
    )
    report.matched_accuracy = (
        matched_correct / max(report.matched, 1)
    )

    if save_results:
        _save_report(report)

    return report


def _save_report(report: EvalReport) -> None:
    """Save evaluation report to JSON file.

    Args:
        report: The evaluation report to save.
    """
    save_dir = Path(__file__).resolve().parent.parent.parent / "_data" / "pokerbench"
    save_dir.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"eval_{report.mode}_{report.split}_{timestamp}.json"
    filepath = save_dir / filename

    # Save report summary + per-scenario details
    data = report.to_dict()
    data["detailed_results"] = [
        {
            "index": r.scenario.index,
            "street": r.scenario.street,
            "position": r.scenario.hero_position,
            "ground_truth": r.scenario.ground_truth,
            "predicted": r.predicted_raw,
            "correct": r.correct,
            "latency_s": round(r.latency_s, 3),
            "error": r.error,
        }
        for r in report.results
    ]

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    logger.info("Saved evaluation report to %s", filepath)

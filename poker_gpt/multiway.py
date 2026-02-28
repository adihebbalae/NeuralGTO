"""
multiway.py — Pairwise HU decomposition for multi-way poker spots.

Decomposes N-player preflop or postflop scenarios into (N-1) heads-up
sub-problems, solves each independently, and synthesizes a multi-way
recommendation using LLM reasoning.

Created: 2026-02-28

DOCUMENTATION:
- Input: ScenarioData with 3+ players active at hero's decision point
- Output: MultiwayResult with action recommendation and pairwise breakdown
- Preflop: uses preflop lookup tables for HU solving (offline, fast)
- Postflop: uses TexasSolver for HU solving (slower, requires binary)
- Synthesis: uses Gemini LLM to combine HU results with multi-way adjustments
- Graceful degradation: if no HU lookups match, LLM reasons from scratch

Pipeline position:
    ScenarioData → decompose → [HU solve × N] → synthesize → MultiwayResult

This is an approximation. True multi-way Nash requires solving the full
N-player game tree, which is computationally intractable on consumer hardware.
Pairwise decomposition is a defensible baseline for research comparison.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types

from poker_gpt import config
from poker_gpt.poker_types import ScenarioData, StrategyResult, ActionEntry
from poker_gpt.preflop_lookup import lookup_preflop_strategy, is_preflop_lookup_available

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Data Structures
# ──────────────────────────────────────────────

@dataclass
class OpponentInfo:
    """Information about a single active opponent at hero's decision point.

    Attributes:
        position: Opponent's position (e.g., "HJ", "CO", "BTN").
        role: Strategic role: "opener", "caller", "3bettor", "4bettor", "all-in".
        action: The opponent's most recent action.
        amount_bb: Raise/bet amount in big blinds, if applicable.
    """
    position: str
    role: str
    action: str
    amount_bb: Optional[float] = None


@dataclass
class PairResult:
    """Result of solving a single HU sub-problem.

    Attributes:
        hero_pos: Hero's position.
        villain_pos: Villain's position in this pair.
        villain_role: Villain's strategic role.
        strategy: StrategyResult from HU lookup/solve, or None if no match.
        match_type: How the match was found: "direct", "simplified", "no_match".
    """
    hero_pos: str
    villain_pos: str
    villain_role: str
    strategy: Optional[StrategyResult] = None
    match_type: str = "no_match"


@dataclass
class MultiwayResult:
    """Final synthesized multi-way recommendation.

    Attributes:
        action: Predicted action category ("raise", "call", "fold", "check").
        raw_text: Full recommendation text or JSON from synthesis.
        confidence: Confidence score (0.0-1.0).
        reasoning: One-line explanation of the multi-way adjustment.
        pair_results: Breakdown of each HU sub-problem.
        num_opponents: Number of active opponents at decision point.
        synthesis_source: How the recommendation was produced.
    """
    action: str = ""
    raw_text: str = ""
    confidence: float = 0.0
    reasoning: str = ""
    pair_results: list[PairResult] = field(default_factory=list)
    num_opponents: int = 0
    synthesis_source: str = "llm"  # "llm", "heuristic", "single_lookup"


# ──────────────────────────────────────────────
# Opponent Identification
# ──────────────────────────────────────────────

def identify_active_opponents(scenario: ScenarioData) -> list[OpponentInfo]:
    """Identify all active opponents at hero's decision point.

    Walks the action history and tracks who has acted and not folded.
    Only considers preflop actions. Excludes hero's own actions.

    Args:
        scenario: The multi-way ScenarioData.

    Returns:
        List of OpponentInfo for each active opponent, ordered by
        action sequence (first to act → last).
    """
    hero_pos = scenario.hero_position.upper()
    active: dict[str, OpponentInfo] = {}  # pos → info
    folded: set[str] = set()
    raise_count = 0

    for entry in scenario.action_history:
        if entry.street != "preflop":
            continue

        pos = entry.position.upper()
        action = entry.action.lower().replace(" ", "")

        # Skip hero's own actions (they're in the history if hero acted earlier)
        if pos == hero_pos:
            if action in ("raise", "bet", "open"):
                raise_count += 1
            continue

        if action == "fold":
            folded.add(pos)
            active.pop(pos, None)
            continue

        # Classify role
        if action in ("raise", "bet", "open"):
            raise_count += 1
            if raise_count == 1:
                role = "opener"
            elif raise_count == 2:
                role = "3bettor"
            elif raise_count == 3:
                role = "4bettor"
            else:
                role = f"{raise_count + 1}bettor"
            active[pos] = OpponentInfo(
                position=pos,
                role=role,
                action="raise",
                amount_bb=entry.amount_bb,
            )
        elif action == "call":
            active[pos] = OpponentInfo(
                position=pos,
                role="caller",
                action="call",
                amount_bb=entry.amount_bb,
            )
        elif action in ("allin", "all-in", "all_in"):
            active[pos] = OpponentInfo(
                position=pos,
                role="all-in",
                action="allin",
                amount_bb=entry.amount_bb,
            )

    return list(active.values())


def is_multiway(scenario: ScenarioData) -> bool:
    """Check if a scenario has 2+ active opponents at hero's decision.

    Args:
        scenario: The ScenarioData to check.

    Returns:
        True if hero faces 2 or more opponents.
    """
    opponents = identify_active_opponents(scenario)
    return len(opponents) >= 2


# ──────────────────────────────────────────────
# HU Scenario Construction
# ──────────────────────────────────────────────

def create_hu_scenario(
    scenario: ScenarioData,
    villain: OpponentInfo,
    all_opponents: list[OpponentInfo],
) -> ScenarioData:
    """Create a simplified HU scenario for hero vs one villain.

    Strips other opponents' actions from the history, keeping only
    interactions between hero and the target villain. Adjusts pot
    size to approximate HU dynamics.

    Args:
        scenario: Original multi-way ScenarioData.
        villain: The specific opponent for this HU pair.
        all_opponents: All active opponents (for pot adjustment context).

    Returns:
        A new ScenarioData representing the HU sub-problem.
    """
    hero_pos = scenario.hero_position.upper()
    villain_pos = villain.position.upper()

    # Build simplified action history: keep only hero and this villain
    hu_history: list[ActionEntry] = []

    for entry in scenario.action_history:
        if entry.street != "preflop":
            continue

        pos = entry.position.upper()
        action = entry.action.lower().replace(" ", "")

        # Keep hero's actions
        if pos == hero_pos:
            hu_history.append(entry)
            continue

        # Keep this villain's actions (non-fold)
        if pos == villain_pos and action != "fold":
            hu_history.append(entry)
            continue

        # Skip all other players' actions

    # Adjust pot for HU approximation
    # In the original multi-way pot, callers contributed. In HU, we approximate
    # by using a pot that reflects hero vs this villain only.
    # Simple approach: use the original pot (conservative — gives hero better odds)
    hu_pot = scenario.pot_size_bb

    return ScenarioData(
        hero_hand=scenario.hero_hand,
        hero_position=hero_pos,
        board=scenario.board,
        pot_size_bb=hu_pot,
        effective_stack_bb=scenario.effective_stack_bb,
        current_street=scenario.current_street,
        oop_range=scenario.oop_range,
        ip_range=scenario.ip_range,
        hero_is_ip=scenario.hero_is_ip,
        action_history=hu_history,
        num_players_preflop=2,
    )


# ──────────────────────────────────────────────
# Pairwise Solving — Preflop
# ──────────────────────────────────────────────

def solve_pairs_preflop(
    scenario: ScenarioData,
    opponents: list[OpponentInfo],
) -> list[PairResult]:
    """Solve each HU pair using preflop lookup tables.

    For each opponent, creates a HU sub-scenario and attempts to look up
    the GTO strategy. Falls back to simplified action histories if the
    full path doesn't match.

    Args:
        scenario: Original multi-way ScenarioData.
        opponents: Active opponents from identify_active_opponents().

    Returns:
        List of PairResult, one per opponent.
    """
    results: list[PairResult] = []

    for villain in opponents:
        pair = PairResult(
            hero_pos=scenario.hero_position.upper(),
            villain_pos=villain.position,
            villain_role=villain.role,
        )

        # Strategy 1: Direct lookup with full multi-way action history
        # (works for squeeze spots where callers are in the tree)
        direct_result = lookup_preflop_strategy(scenario)
        if direct_result is not None:
            pair.strategy = direct_result
            pair.match_type = "direct"
            results.append(pair)
            continue

        # Strategy 2: Simplified HU scenario (strip other opponents)
        hu_scenario = create_hu_scenario(scenario, villain, opponents)
        hu_result = lookup_preflop_strategy(hu_scenario)
        if hu_result is not None:
            pair.strategy = hu_result
            pair.match_type = "simplified"
            results.append(pair)
            continue

        # Strategy 3: Minimal scenario — just hero facing villain's action
        # If villain opened, look up "hero facing open from villain's position"
        if villain.role == "opener":
            minimal_history = [
                ActionEntry(
                    position=villain.position,
                    action="raise",
                    amount_bb=villain.amount_bb,
                    street="preflop",
                )
            ]
            minimal_scenario = ScenarioData(
                hero_hand=scenario.hero_hand,
                hero_position=scenario.hero_position,
                board="",
                pot_size_bb=scenario.pot_size_bb,
                effective_stack_bb=scenario.effective_stack_bb,
                current_street="preflop",
                oop_range="",
                ip_range="",
                hero_is_ip=False,
                action_history=minimal_history,
                num_players_preflop=2,
            )
            minimal_result = lookup_preflop_strategy(minimal_scenario)
            if minimal_result is not None:
                pair.strategy = minimal_result
                pair.match_type = "simplified"
                results.append(pair)
                continue

        # No match found for this pair
        pair.match_type = "no_match"
        results.append(pair)

    return results


# ──────────────────────────────────────────────
# Pairwise Solving — Postflop (TexasSolver)
# ──────────────────────────────────────────────

def solve_pairs_postflop(
    scenario: ScenarioData,
    opponents: list[OpponentInfo],
) -> list[PairResult]:
    """Solve each HU pair using TexasSolver for postflop scenarios.

    Creates HU sub-scenarios and runs the solver for each. This is
    slower but produces exact GTO strategies for each HU matchup.

    Args:
        scenario: Original multi-way ScenarioData (must have board cards).
        opponents: Active opponents.

    Returns:
        List of PairResult, one per opponent.

    Note:
        Requires TexasSolver binary. Each pair takes 1-5 minutes to solve.
        For 3 opponents, total solve time is 3-15 minutes.
    """
    from poker_gpt.solver_input import generate_solver_input
    from poker_gpt.solver_runner import run_solver, is_solver_available
    from poker_gpt.strategy_extractor import extract_strategy

    results: list[PairResult] = []

    if not is_solver_available():
        logger.warning("TexasSolver not available; postflop pairwise solving skipped")
        return [
            PairResult(
                hero_pos=scenario.hero_position,
                villain_pos=v.position,
                villain_role=v.role,
                match_type="no_match",
            )
            for v in opponents
        ]

    for i, villain in enumerate(opponents):
        pair = PairResult(
            hero_pos=scenario.hero_position.upper(),
            villain_pos=villain.position,
            villain_role=villain.role,
        )

        try:
            hu_scenario = create_hu_scenario(scenario, villain, opponents)

            # Generate unique solver input file for this pair
            input_path = config.WORK_DIR / f"pairwise_input_{i}.txt"
            generate_solver_input(hu_scenario, output_path=input_path)

            output_path = run_solver(input_file=input_path)
            if output_path is not None:
                strategy = extract_strategy(output_path, hu_scenario)
                pair.strategy = strategy
                pair.match_type = "solver"
            else:
                pair.match_type = "no_match"

        except Exception as e:
            logger.warning(
                "Solver failed for pair %s vs %s: %s",
                scenario.hero_position, villain.position, e,
            )
            pair.match_type = "no_match"

        results.append(pair)

    return results


# ──────────────────────────────────────────────
# LLM Synthesis
# ──────────────────────────────────────────────

def _load_synthesis_prompt() -> str:
    """Load the multi-way synthesis system prompt."""
    prompt_path = Path(__file__).parent / "prompts" / "multiway_synthesis.txt"
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def _build_synthesis_context(
    scenario: ScenarioData,
    pair_results: list[PairResult],
) -> str:
    """Build the user-facing context message for LLM synthesis.

    Args:
        scenario: Original multi-way scenario.
        pair_results: Results from pairwise solving.

    Returns:
        Formatted context string for the LLM.
    """
    lines = [
        "=== MULTI-WAY SITUATION ===",
        f"Hero position: {scenario.hero_position}",
        f"Hero hand: {scenario.hero_hand}",
        f"Street: {scenario.current_street}",
        f"Pot: {scenario.pot_size_bb:.1f} BB",
        f"Effective stack: {scenario.effective_stack_bb:.1f} BB",
        f"Active opponents: {len(pair_results)}",
        "",
    ]

    # Action history
    if scenario.action_history:
        lines.append("Action history:")
        for entry in scenario.action_history:
            if entry.street != "preflop":
                continue
            amt = f" {entry.amount_bb:.1f}bb" if entry.amount_bb else ""
            lines.append(f"  {entry.position} {entry.action}{amt}")
        lines.append("")

    # Board (postflop)
    if scenario.board:
        lines.append(f"Board: {scenario.board}")
        lines.append("")

    # Pairwise results
    lines.append("=== PAIRWISE HU RESULTS ===")
    for i, pr in enumerate(pair_results, 1):
        lines.append(f"\n--- Pair {i}: Hero ({pr.hero_pos}) vs {pr.villain_pos} ({pr.villain_role}) ---")
        lines.append(f"Match quality: {pr.match_type}")

        if pr.strategy is not None:
            lines.append(f"Best action (HU): {pr.strategy.best_action} "
                         f"({pr.strategy.best_action_freq:.0%})")
            lines.append("Full strategy:")
            for action, freq in sorted(
                pr.strategy.actions.items(),
                key=lambda x: -x[1],
            ):
                lines.append(f"  {action}: {freq:.1%}")
        else:
            lines.append("No HU lookup available for this pair.")

    lines.append("")
    lines.append("=== TASK ===")
    lines.append(
        "Synthesize these HU results into a single multi-way recommendation. "
        "Apply multi-way adjustments (MDF compression, reduced bluffing, "
        "position considerations). Output JSON only."
    )

    return "\n".join(lines)


def synthesize_multiway(
    scenario: ScenarioData,
    pair_results: list[PairResult],
) -> MultiwayResult:
    """Synthesize pairwise HU results into a multi-way recommendation.

    Uses Gemini LLM to combine individual HU strategies with multi-way
    poker theory (MDF compression, equity realization adjustments).

    If all pair lookups failed, the LLM reasons from poker fundamentals.
    If only one pair matched, applies multi-way compression heuristically.

    Args:
        scenario: Original multi-way ScenarioData.
        pair_results: Results from solve_pairs_preflop/postflop.

    Returns:
        MultiwayResult with the synthesized recommendation.
    """
    result = MultiwayResult(
        pair_results=pair_results,
        num_opponents=len(pair_results),
    )

    # Check how many pairs actually matched
    matched = [pr for pr in pair_results if pr.strategy is not None]

    # If exactly one matched and it's a pure strategy (>90%), use heuristic
    if len(matched) == 1 and matched[0].strategy.best_action_freq > 0.90:
        best = matched[0].strategy.best_action.lower()
        # Heuristic multi-way adjustment: if HU says pure fold, fold.
        # If HU says pure raise, still raise (premium hand).
        if "fold" in best:
            result.action = "fold"
            result.confidence = 0.85
            result.reasoning = (
                f"HU vs {matched[0].villain_pos} ({matched[0].villain_role}) "
                f"is {matched[0].strategy.best_action_freq:.0%} fold; "
                f"multi-way makes folding even clearer."
            )
        elif "raise" in best or "all" in best.replace("-", ""):
            result.action = "raise"
            result.confidence = 0.75
            result.reasoning = (
                f"HU vs {matched[0].villain_pos} ({matched[0].villain_role}) "
                f"is {matched[0].strategy.best_action_freq:.0%} raise; "
                f"premium hand likely still raises multi-way."
            )
        elif "call" in best:
            result.action = "call"
            result.confidence = 0.70
            result.reasoning = (
                f"HU vs {matched[0].villain_pos} ({matched[0].villain_role}) "
                f"is {matched[0].strategy.best_action_freq:.0%} call; "
                f"multi-way pot odds support calling."
            )
        else:
            result.action = best.split()[0] if best else "fold"
            result.confidence = 0.60
            result.reasoning = "Heuristic multi-way adjustment from single HU match."

        result.synthesis_source = "heuristic"
        result.raw_text = result.reasoning
        return result

    # Use LLM synthesis for complex cases (multiple matches or no matches)
    try:
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        system_prompt = _load_synthesis_prompt()
        context = _build_synthesis_context(scenario, pair_results)

        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=context,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.1,
                max_output_tokens=1024,
            ),
        )

        raw = response.text.strip() if response.text else ""
        result.raw_text = raw
        result.synthesis_source = "llm"

        # Parse JSON response
        parsed = _parse_synthesis_response(raw)
        result.action = parsed.get("action", "fold")
        result.confidence = parsed.get("confidence", 0.5)
        result.reasoning = parsed.get("reasoning", "LLM synthesis")

    except Exception as e:
        logger.warning("LLM synthesis failed: %s", e)
        # Fallback: use best available HU result with multi-way compression
        result = _heuristic_fallback(scenario, pair_results)

    return result


def _parse_synthesis_response(raw: str) -> dict:
    """Parse the LLM's JSON response, handling common formatting issues.

    Args:
        raw: Raw response text from the LLM.

    Returns:
        Parsed dict with "action", "confidence", "reasoning" keys.
    """
    # Strip markdown code fences if present
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        data = json.loads(text)
        # Validate and normalize
        action = str(data.get("action", "fold")).lower().strip()
        if action not in ("raise", "call", "fold", "check"):
            # Try to match known actions
            for known in ("fold", "call", "raise", "check"):
                if known in action:
                    action = known
                    break
            else:
                action = "fold"

        return {
            "action": action,
            "confidence": float(data.get("confidence", 0.5)),
            "reasoning": str(data.get("reasoning", "")),
        }
    except (json.JSONDecodeError, ValueError, TypeError):
        # Try to extract action from raw text
        text_lower = text.lower()
        for action in ("fold", "call", "raise", "check"):
            if action in text_lower:
                return {
                    "action": action,
                    "confidence": 0.4,
                    "reasoning": f"Extracted from raw: {text[:100]}",
                }
        return {"action": "fold", "confidence": 0.3, "reasoning": "Parse failed"}


def _heuristic_fallback(
    scenario: ScenarioData,
    pair_results: list[PairResult],
) -> MultiwayResult:
    """Produce a multi-way recommendation using simple heuristics.

    Used when LLM synthesis fails. Applies basic multi-way adjustments
    to the best available HU result.

    Args:
        scenario: Original multi-way ScenarioData.
        pair_results: Pairwise results (may have no matches).

    Returns:
        MultiwayResult with heuristic recommendation.
    """
    result = MultiwayResult(
        pair_results=pair_results,
        num_opponents=len(pair_results),
        synthesis_source="heuristic",
    )

    matched = [pr for pr in pair_results if pr.strategy is not None]

    if not matched:
        # No data at all — default to fold (conservative in multi-way)
        result.action = "fold"
        result.confidence = 0.3
        result.reasoning = "No HU data available; defaulting to fold in multi-way."
        result.raw_text = result.reasoning
        return result

    # Use the pair vs the primary aggressor (opener or highest raiser)
    primary = matched[0]
    for m in matched:
        if m.villain_role in ("opener", "3bettor", "4bettor"):
            primary = m
            break

    best = primary.strategy.best_action.lower()
    freq = primary.strategy.best_action_freq

    # Multi-way compression: reduce aggression, increase folding
    n_opp = len(pair_results)
    if "fold" in best:
        result.action = "fold"
        result.confidence = min(0.95, freq + 0.1)
    elif "raise" in best or "all" in best.replace("-", ""):
        # If >80% raise HU, still raise multi-way (likely premium)
        if freq > 0.80:
            result.action = "raise"
            result.confidence = max(0.5, freq - 0.15 * n_opp)
        else:
            # Mixed raise/fold or raise/call → shift toward call or fold
            result.action = "call" if freq > 0.40 else "fold"
            result.confidence = 0.50
    elif "call" in best:
        # Calling is often correct multi-way (better odds)
        result.action = "call"
        result.confidence = min(0.80, freq)
    else:
        result.action = best.split()[0] if best else "fold"
        result.confidence = 0.40

    result.reasoning = (
        f"Heuristic: HU vs {primary.villain_pos} → {primary.strategy.best_action} "
        f"({freq:.0%}), adjusted for {n_opp} opponents."
    )
    result.raw_text = result.reasoning
    return result


# ──────────────────────────────────────────────
# End-to-End Entry Point
# ──────────────────────────────────────────────

def analyze_multiway(
    scenario: ScenarioData,
    use_llm: bool = True,
) -> MultiwayResult:
    """Analyze a multi-way poker spot using pairwise decomposition.

    End-to-end pipeline: identify opponents → create HU pairs →
    solve each pair → synthesize multi-way recommendation.

    Args:
        scenario: The ScenarioData with 3+ active players.
        use_llm: Whether to use LLM for synthesis. If False, uses
            heuristic fallback only (no API calls).

    Returns:
        MultiwayResult with the recommended action and breakdown.
    """
    opponents = identify_active_opponents(scenario)

    if len(opponents) < 2:
        logger.warning(
            "analyze_multiway called with %d opponents (need 2+)",
            len(opponents),
        )
        # Not actually multi-way — try direct lookup
        direct = lookup_preflop_strategy(scenario)
        if direct is not None:
            return MultiwayResult(
                action=direct.best_action.lower().split()[0],
                raw_text=f"Direct lookup: {direct.best_action} ({direct.best_action_freq:.0%})",
                confidence=direct.best_action_freq,
                reasoning="Not multi-way; used direct HU lookup.",
                num_opponents=len(opponents),
                synthesis_source="single_lookup",
            )
        return MultiwayResult(
            action="fold",
            raw_text="Not multi-way and no lookup match.",
            confidence=0.3,
            num_opponents=len(opponents),
            synthesis_source="heuristic",
        )

    # Solve each HU pair
    if scenario.current_street == "preflop":
        pair_results = solve_pairs_preflop(scenario, opponents)
    else:
        pair_results = solve_pairs_postflop(scenario, opponents)

    # Synthesize
    if use_llm:
        return synthesize_multiway(scenario, pair_results)
    else:
        return _heuristic_fallback(scenario, pair_results)

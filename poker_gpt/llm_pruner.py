"""
llm_pruner.py — LLM-guided tree pruning for CFR solver (T4.2a).

Uses Gemini to analyze a partially-converged CFR strategy and recommend
which bet sizes should be pruned from the game tree before a full solve.
Combines noisy partial regret signals with semantic poker knowledge.

Created: 2026-02-28
Task: T4.2a

DOCUMENTATION:
- Input: Partial strategy JSON (from solver_harness), board context, stack/position info
- Output: PruningDecision dataclass with keep/prune lists and reasoning
- System prompt lives in poker_gpt/prompts/pruner_system.txt (not inline)
- Returns None on any failure (never raises)
- Uses config.GEMINI_MODEL for all API calls
- Also provides threshold_prune() as a rule-based baseline for comparison
"""

import json
import re
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types

from poker_gpt import config
from poker_gpt.poker_types import PruningDecision


def _load_pruner_prompt() -> str:
    """Load the pruner system prompt from disk.

    Returns:
        The system prompt string.

    Raises:
        FileNotFoundError: If the prompt file is missing.
    """
    prompt_path = Path(__file__).parent / "prompts" / "pruner_system.txt"
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def suggest_pruning(
    action_frequencies: dict[str, float],
    board: str,
    position_ip: str = "BTN",
    position_oop: str = "BB",
    effective_stack_bb: float = 100.0,
    pot_size_bb: float = 6.0,
    warm_iterations: int = 20,
) -> Optional[PruningDecision]:
    """
    Ask the LLM which bet sizes to prune based on partial CFR data.

    Combines the noisy frequency signal from a warm-stop solve with the LLM's
    semantic poker reasoning to decide which bet sizes are safe to remove.

    Args:
        action_frequencies: Dict mapping action names to average frequencies
            across all combos, e.g. {"CHECK": 0.35, "BET 33": 0.25, ...}.
        board: Board cards, e.g. "Kc,Qc,2h" or "Kc-Qc-2h".
        position_ip: In-position player label, e.g. "BTN".
        position_oop: Out-of-position player label, e.g. "BB".
        effective_stack_bb: Effective stack in big blinds.
        pot_size_bb: Current pot in big blinds.
        warm_iterations: How many CFR iterations the partial data is based on.

    Returns:
        PruningDecision with keep/prune lists and reasoning, or None on failure.
    """
    try:
        system_prompt = _load_pruner_prompt()
    except FileNotFoundError:
        if config.DEBUG:
            print("[LLM_PRUNER] pruner_system.txt not found.")
        return None

    # Build the user message with all context
    user_message = _build_pruning_prompt(
        action_frequencies=action_frequencies,
        board=board,
        position_ip=position_ip,
        position_oop=position_oop,
        effective_stack_bb=effective_stack_bb,
        pot_size_bb=pot_size_bb,
        warm_iterations=warm_iterations,
    )

    try:
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=config.GEMINI_TEMPERATURE,
                max_output_tokens=1024,
            ),
        )
    except Exception as e:
        if config.DEBUG:
            print(f"[LLM_PRUNER] Gemini API call failed: {e}")
        return None

    if not response or not response.text:
        if config.DEBUG:
            print("[LLM_PRUNER] Empty response from Gemini.")
        return None

    return parse_pruning_response(
        response.text, warm_iterations=warm_iterations, board=board
    )


def threshold_prune(
    action_frequencies: dict[str, float],
    threshold: float = 0.05,
) -> PruningDecision:
    """
    Simple threshold-based pruning baseline.

    Prunes any action with average frequency below the threshold.
    CHECK is always kept regardless of frequency.

    Args:
        action_frequencies: Dict of action name -> average frequency.
        threshold: Minimum frequency to keep (default: 5%).

    Returns:
        PruningDecision with threshold-based keep/prune lists.
    """
    keep = []
    prune = []

    for action, freq in action_frequencies.items():
        if action.upper() == "CHECK" or freq >= threshold:
            keep.append(action)
        else:
            prune.append(action)

    # Ensure at least one non-CHECK action is kept
    non_check_keep = [a for a in keep if a.upper() != "CHECK"]
    if not non_check_keep and prune:
        # Move the highest-frequency pruned action back to keep
        best_pruned = max(prune, key=lambda a: action_frequencies.get(a, 0))
        prune.remove(best_pruned)
        keep.append(best_pruned)

    return PruningDecision(
        keep_sizes=keep,
        prune_sizes=prune,
        reasoning=(
            f"Threshold pruning: removed actions with avg frequency < {threshold:.0%}."
        ),
        warm_iterations=0,
        board="",
    )


def parse_pruning_response(
    response_text: str,
    warm_iterations: int = 0,
    board: str = "",
) -> Optional[PruningDecision]:
    """
    Parse the LLM's JSON response into a PruningDecision.

    Handles common formatting issues: markdown fences, trailing commas,
    extra whitespace. If JSON parsing fails (e.g. truncated response),
    falls back to regex extraction of keep/prune lists.

    Args:
        response_text: Raw text response from the LLM.
        warm_iterations: Number of warm-stop iterations (metadata).
        board: Board string (metadata).

    Returns:
        PruningDecision or None if parsing fails.
    """
    # ── Attempt 1: standard JSON parse ──
    json_parsed = False
    try:
        text = response_text.strip()
        if text.startswith("```"):
            first_newline = text.index("\n")
            text = text[first_newline + 1:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        data = json.loads(text)
        json_parsed = True

        keep = data.get("keep", [])
        prune = data.get("prune", [])
        reasoning = data.get("reasoning", "")

        if isinstance(keep, list) and isinstance(prune, list) and keep:
            return PruningDecision(
                keep_sizes=keep,
                prune_sizes=prune,
                reasoning=str(reasoning),
                warm_iterations=warm_iterations,
                board=board,
            )
        # Valid JSON but wrong structure — reject without regex fallback
        if config.DEBUG:
            print("[LLM_PRUNER] Valid JSON but missing/invalid keep/prune lists.")
        return None
    except (json.JSONDecodeError, ValueError, KeyError):
        pass

    # ── Attempt 2: regex fallback for truncated / malformed JSON ──
    # Only fires when JSON itself was unparseable (truncated, etc.)
    try:
        raw = response_text

        keep_match = re.search(
            r'"keep"\s*:\s*\[(.*?)\]', raw, re.DOTALL | re.IGNORECASE
        )
        if not keep_match:
            keep_match = re.search(
                r'"keep"\s*:\s*\[([^\]]*)', raw, re.DOTALL | re.IGNORECASE
            )

        prune_match = re.search(
            r'"prune"\s*:\s*\[(.*?)\]', raw, re.DOTALL | re.IGNORECASE
        )
        if not prune_match:
            prune_match = re.search(
                r'"prune"\s*:\s*\[([^\]]*)', raw, re.DOTALL | re.IGNORECASE
            )

        reason_match = re.search(
            r'"reasoning"\s*:\s*"(.*?)"', raw, re.DOTALL | re.IGNORECASE
        )

        if keep_match:
            keep_raw = keep_match.group(1)
            keep = [
                s.strip().strip('"').strip("'")
                for s in re.findall(r'"([^"]*)"', keep_raw)
            ]
            if not keep:
                keep = [
                    s.strip()
                    for s in keep_raw.split(",")
                    if s.strip().strip('"').strip("'")
                ]

            prune = []
            if prune_match:
                prune_raw = prune_match.group(1)
                prune = [
                    s.strip().strip('"').strip("'")
                    for s in re.findall(r'"([^"]*)"', prune_raw)
                ]

            reasoning = reason_match.group(1) if reason_match else ""

            if keep:
                if config.DEBUG:
                    print(f"[LLM_PRUNER] Regex fallback succeeded: keep={keep}")
                return PruningDecision(
                    keep_sizes=keep,
                    prune_sizes=prune,
                    reasoning=str(reasoning),
                    warm_iterations=warm_iterations,
                    board=board,
                    metadata={"parse_method": "regex_fallback"},
                )
    except Exception as e:
        if config.DEBUG:
            print(f"[LLM_PRUNER] Regex fallback also failed: {e}")

    if config.DEBUG:
        print("[LLM_PRUNER] All parsing attempts failed.")
        print(f"[LLM_PRUNER] Raw response: {response_text[:300]}")
    return None


def action_to_bet_size_pct(action_name: str) -> Optional[int]:
    """
    Extract the numeric bet size percentage from an action name.

    Handles both integer format (``BET 33``) and float format
    (``BET 2.000000`` — raw chip amounts from solver output).
    For float values, rounds to the nearest integer.

    Args:
        action_name: e.g. "BET 33", "BET 67", "BET 2.000000".

    Returns:
        Integer percentage (33, 67, 100) or None for non-bet actions
        like CHECK, FOLD, ALL-IN.
    """
    parts = action_name.strip().upper().split()
    if len(parts) == 2 and parts[0] in ("BET", "RAISE"):
        try:
            return int(round(float(parts[1])))
        except ValueError:
            return None
    return None


def keep_actions_to_bet_sizes(keep_actions: list[str]) -> list[int]:
    """
    Convert a list of keep action names to integer bet size percentages.

    Filters out non-bet actions (CHECK, FOLD, ALL-IN, etc.) and extracts the
    numeric percentage from bet actions.

    Args:
        keep_actions: List of action names from PruningDecision.keep_sizes.

    Returns:
        List of integer percentages, e.g. [33, 67] from
        ["CHECK", "BET 33", "BET 67"].
    """
    sizes = []
    for action in keep_actions:
        pct = action_to_bet_size_pct(action)
        if pct is not None:
            sizes.append(pct)
    return sizes


# ──────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────


def _build_pruning_prompt(
    action_frequencies: dict[str, float],
    board: str,
    position_ip: str,
    position_oop: str,
    effective_stack_bb: float,
    pot_size_bb: float,
    warm_iterations: int,
) -> str:
    """Build the user-facing prompt for the LLM pruning call."""
    spr = effective_stack_bb / pot_size_bb if pot_size_bb > 0 else 0

    freq_lines = []
    for action, freq in sorted(
        action_frequencies.items(), key=lambda x: -x[1]
    ):
        freq_lines.append(f"  {action}: {freq:.1%}")
    freq_block = "\n".join(freq_lines)

    prompt = (
        f"Board: {board}\n"
        f"Positions: {position_ip} (IP) vs {position_oop} (OOP)\n"
        f"Effective stack: {effective_stack_bb:.0f} BB\n"
        f"Pot: {pot_size_bb:.0f} BB\n"
        f"SPR: {spr:.1f}\n"
        f"Warm-up iterations: {warm_iterations}\n"
        f"\n"
        f"Action frequencies (averaged across all combos after "
        f"{warm_iterations} iterations):\n"
        f"{freq_block}\n"
        f"\n"
        f"Which actions should be pruned?"
    )
    return prompt

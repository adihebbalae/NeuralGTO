"""
quiz.py — Quiz/Study Mode for NeuralGTO.

Provides a quiz flow where:
  1. User describes a poker spot
  2. System generates the GTO strategy silently
  3. User guesses an action
  4. System scores the guess and reveals the GTO answer with explanation

The scoring engine is pure Python — no API calls. The explanation step
reuses the existing advisor module with a quiz-specific wrapper.

Created: 2026-02-28

DOCUMENTATION:
- score_user_action() is the core scoring function — offline, no API
- generate_quiz_feedback() calls Gemini to produce a coaching explanation
- All poker jargon filtering respects output_level (beginner/advanced)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from google import genai
from google.genai import types
from pathlib import Path

from poker_gpt.poker_types import ScenarioData, StrategyResult
from poker_gpt import config
from poker_gpt.nl_advisor import _load_advisor_prompt


# ──────────────────────────────────────────────
# Action normalisation
# ──────────────────────────────────────────────

# Maps user-typed strings → canonical action roots used in StrategyResult.actions
_ACTION_ALIASES: dict[str, str] = {
    # Folds
    "fold": "FOLD",
    "muck": "FOLD",
    "give up": "FOLD",
    # Checks
    "check": "CHECK",
    "x": "CHECK",
    # Calls
    "call": "CALL",
    "flat": "CALL",
    # Bets
    "bet": "BET",
    "donk": "BET",
    "lead": "BET",
    # Raises
    "raise": "RAISE",
    "3bet": "RAISE",
    "3-bet": "RAISE",
    "4bet": "RAISE",
    "4-bet": "RAISE",
    "re-raise": "RAISE",
    "reraise": "RAISE",
    # All-in
    "allin": "ALLIN",
    "all-in": "ALLIN",
    "all in": "ALLIN",
    "jam": "ALLIN",
    "shove": "ALLIN",
}


def normalise_user_action(raw: str) -> str:
    """Normalise a user-typed action string to a canonical root.

    Examples:
        "bet 67" → "BET"
        "check"  → "CHECK"
        "raise"  → "RAISE"
        "fold"   → "FOLD"
        "all in" → "ALLIN"

    Returns the canonical string or the uppercased original if unknown.
    """
    cleaned = raw.strip().lower()
    # Try direct alias match first (handles multi-word like "all in")
    if cleaned in _ACTION_ALIASES:
        return _ACTION_ALIASES[cleaned]
    # Strip trailing numbers/sizing (e.g. "bet 67" → "bet")
    root = re.split(r"[\s\d%]+", cleaned)[0]
    return _ACTION_ALIASES.get(root, root.upper())


def _extract_sizing(raw: str) -> Optional[int]:
    """Extract a numeric bet/raise sizing from user input.

    Examples:
        "bet 67"    → 67
        "raise 100" → 100
        "bet 33%"   → 33
        "check"     → None
    """
    m = re.search(r"(\d+)\s*%?", raw)
    if m:
        return int(m.group(1))
    return None


# ──────────────────────────────────────────────
# Scoring
# ──────────────────────────────────────────────

@dataclass
class QuizScore:
    """Result of scoring the user's quiz answer against the GTO strategy."""
    # What the user said
    user_action: str           # Normalised, e.g. "BET"
    user_sizing: Optional[int] # e.g. 67, or None

    # GTO answer
    gto_best_action: str       # e.g. "BET 67"
    gto_best_freq: float       # e.g. 0.78
    gto_actions: dict          # Full action dict from StrategyResult

    # Scoring
    action_correct: bool       # Did the user pick the right action root?
    gto_freq_of_user_action: float  # How often GTO does the user's action
    score: int                 # 0–100 composite score
    grade: str                 # "Perfect", "Good", "Acceptable", "Incorrect"

    # Sizing accuracy (only for bet/raise)
    sizing_delta: Optional[int] = None  # Difference in pot% (None if N/A)

    @property
    def is_mixed_spot(self) -> bool:
        """True if the GTO strategy genuinely mixes (2+ actions ≥ 20%)."""
        significant = [f for f in self.gto_actions.values() if f >= 0.20]
        return len(significant) >= 2


def score_user_action(
    user_raw: str,
    strategy: StrategyResult,
) -> QuizScore:
    """Score the user's action guess against the GTO strategy.

    The scoring rubric:
      - 100 = exact match on both action root and sizing
      -  85 = correct action root, wrong/missing sizing
      -  60 = user chose a GTO-mixed action (≥20% freq) that isn't the best
      -  30 = user chose a minor GTO action (5–20% freq)
      -   0 = user chose an action with <5% GTO frequency (basically never correct)

    Args:
        user_raw: Raw user input string, e.g. "bet 67", "check", "fold".
        strategy: The StrategyResult from the solver/preflop lookup.

    Returns:
        A QuizScore dataclass with all scoring details.
    """
    user_action = normalise_user_action(user_raw)
    user_sizing = _extract_sizing(user_raw)

    gto_best = strategy.best_action
    gto_best_root = re.split(r"[\s\d%]+", gto_best)[0].upper()
    gto_best_freq = strategy.best_action_freq

    # Find the GTO frequency for the user's chosen action root.
    # StrategyResult.actions keys can be like "BET 67", "CHECK", "RAISE 100".
    # We need to match on the root (BET, CHECK, RAISE, etc).
    user_freq = 0.0
    matched_full_action = None
    for action_key, freq in strategy.actions.items():
        action_root = re.split(r"[\s\d%]+", action_key)[0].upper()
        if action_root == user_action:
            user_freq += freq
            # Track the specific full action with highest freq for sizing comparison
            if matched_full_action is None or freq > strategy.actions.get(matched_full_action, 0):
                matched_full_action = action_key

    # Determine if action root matches the best action root
    action_correct = (user_action == gto_best_root)

    # Sizing delta (only relevant for BET/RAISE actions)
    sizing_delta = None
    if user_sizing is not None and matched_full_action:
        gto_sizing = _extract_sizing(matched_full_action)
        if gto_sizing is not None:
            sizing_delta = abs(user_sizing - gto_sizing)

    # Compute score
    if action_correct:
        if sizing_delta is not None and sizing_delta <= 5:
            score = 100
        elif sizing_delta is not None:
            # Penalise proportionally to sizing miss (max -30 points)
            penalty = min(30, sizing_delta)
            score = max(70, 100 - penalty)
        else:
            # Correct root, no sizing comparison needed (check/fold/call)
            score = 100
    elif user_freq >= 0.20:
        # User chose a legitimate mixed-strategy option
        score = 60
    elif user_freq >= 0.05:
        # Minor but not zero frequency
        score = 30
    else:
        # Action basically never taken at GTO
        score = 0

    # Grade
    if score >= 90:
        grade = "Perfect"
    elif score >= 70:
        grade = "Good"
    elif score >= 50:
        grade = "Acceptable"
    else:
        grade = "Incorrect"

    return QuizScore(
        user_action=user_action,
        user_sizing=user_sizing,
        gto_best_action=gto_best,
        gto_best_freq=gto_best_freq,
        gto_actions=dict(strategy.actions),
        action_correct=action_correct,
        gto_freq_of_user_action=user_freq,
        score=score,
        grade=grade,
        sizing_delta=sizing_delta,
    )


# ──────────────────────────────────────────────
# Quiz feedback prompt
# ──────────────────────────────────────────────

def _load_quiz_prompt() -> str:
    """Load the quiz explanation system prompt."""
    prompt_path = Path(__file__).parent / "prompts" / "quiz_explanation_system.txt"
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def generate_quiz_feedback(
    scenario: ScenarioData,
    strategy: StrategyResult,
    quiz_score: QuizScore,
    output_level: str = "advanced",
) -> str:
    """Generate a coaching explanation after a quiz attempt.

    Uses the beginner or advanced advisor prompt depending on output_level,
    with quiz-specific context prepended so the LLM knows the user's guess
    and score.

    Args:
        scenario: The parsed poker scenario.
        strategy: The GTO strategy result.
        quiz_score: The scoring result from score_user_action().
        output_level: "beginner" or "advanced".

    Returns:
        Natural language coaching feedback string.
    """
    client = genai.Client(api_key=config.GEMINI_API_KEY)

    # Load quiz-specific system prompt
    quiz_system = _load_quiz_prompt()

    # If beginner mode, append the beginner restrictions as extra instructions
    if output_level == "beginner":
        beginner_rules = _load_advisor_prompt("beginner")
        # Extract just the prohibitions and tone sections
        quiz_system += (
            "\n\nADDITIONAL OUTPUT RULES (beginner mode):\n"
            + beginner_rules
        )

    # Build context message
    actions_str = ""
    for action, freq in sorted(strategy.actions.items(), key=lambda x: -x[1]):
        actions_str += f"  - {action}: {freq * 100:.1f}%\n"

    context = f"""POKER SCENARIO:
- Hero's hand: {scenario.hero_hand}
- Hero's position: {scenario.hero_position} ({'In Position' if scenario.hero_is_ip else 'Out of Position'})
- Board: {scenario.board or '(preflop)'}
- Street: {scenario.current_street}
- Pot size: {scenario.pot_size_bb:.0f} BB
- Effective stack: {scenario.effective_stack_bb:.0f} BB

GTO STRATEGY FOR {strategy.hand}:
{actions_str}
Best action: {strategy.best_action} ({strategy.best_action_freq * 100:.1f}%)
Data source: {strategy.source}

STUDENT'S ANSWER: {quiz_score.user_action}
{"STUDENT'S SIZING: " + str(quiz_score.user_sizing) + "% pot" if quiz_score.user_sizing else ""}
SCORE: {quiz_score.score}/100 ({quiz_score.grade})
ACTION CORRECT: {"Yes" if quiz_score.action_correct else "No"}
GTO FREQUENCY OF STUDENT'S ACTION: {quiz_score.gto_freq_of_user_action * 100:.1f}%
{"SIZING DELTA: " + str(quiz_score.sizing_delta) + " pot%" if quiz_score.sizing_delta is not None else ""}
IS MIXED SPOT: {"Yes" if quiz_score.is_mixed_spot else "No"}

Please provide coaching feedback to the student.
"""

    try:
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=context,
            config=types.GenerateContentConfig(
                system_instruction=quiz_system,
                temperature=0.3,
                max_output_tokens=4096,
            ),
        )
    except Exception as e:
        error_msg = str(e)
        if "quota" in error_msg.lower() or "429" in error_msg:
            raise RuntimeError(
                "Gemini API quota exceeded. Check your billing at "
                "https://console.cloud.google.com/billing"
            )
        raise RuntimeError(f"Gemini API call failed: {e}")

    feedback = response.text
    if not feedback:
        raise RuntimeError(
            "Gemini returned an empty response for quiz feedback. "
            "The request may have been blocked by safety filters."
        )

    return feedback

"""
backend/app/services/advice_formatter.py — Structured advice output (W5.0c).

Transforms the raw pipeline result dict (from ``poker_gpt.main.analyze_hand()``)
into a structured ``StructuredAdviceResponse`` with:
  - Top 3 plays sorted by frequency (descending)
  - EV signal per action (positive / negative / neutral)
  - Per-street review text extracted from the advice string
  - Confidence score (solver = 100%, preflop_lookup = 90%, Gemini = 75%)
  - Table rule heuristic

Created: 2026-03-03

DOCUMENTATION:
    Usage in the adapter::

        from app.services.advice_formatter import format_structured_advice
        structured = format_structured_advice(result)
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.models.schemas import (
    EvSignal,
    StructuredAdviceResponse,
    TopPlayResponse,
)


# ──────────────────────────────────────────────
# Confidence mapping: source → numeric score
# ──────────────────────────────────────────────

_CONFIDENCE_SCORES: dict[str, float] = {
    "solver": 1.0,
    "solver_cached": 1.0,
    "preflop_lookup": 0.90,
    "llm_only": 0.75,
    "llm_fallback": 0.75,
    "gemini": 0.75,
    "gpt_fallback": 0.75,
    "validation_error": 0.0,
}


# ──────────────────────────────────────────────
# EV signal heuristics
# ──────────────────────────────────────────────

# Actions that are generally EV-positive (aggressive actions)
_POSITIVE_PATTERNS = re.compile(
    r"(?i)^(raise|bet|allin|all[_-]?in|shove|3[_-]?bet|4[_-]?bet)",
)

# Actions that are generally EV-negative (giving up)
_NEGATIVE_PATTERNS = re.compile(r"(?i)^(fold)")


def _infer_ev_signal(action: str, frequency: float) -> EvSignal:
    """Infer EV direction from action name and frequency.

    Heuristic:
      - Aggressive actions (raise/bet) at >30% freq → positive
      - Fold → negative
      - Check or low-freq passive → neutral

    Args:
        action: Action label, e.g. "BET 67", "CHECK", "FOLD".
        frequency: GTO frequency 0–1.

    Returns:
        EvSignal enum value.
    """
    if _NEGATIVE_PATTERNS.match(action):
        return EvSignal.NEGATIVE
    if _POSITIVE_PATTERNS.match(action) and frequency > 0.10:
        return EvSignal.POSITIVE
    if frequency > 0.50:
        return EvSignal.POSITIVE
    return EvSignal.NEUTRAL


# ──────────────────────────────────────────────
# Street review extraction
# ──────────────────────────────────────────────

# Pattern to match street headers in the advice text
_STREET_HEADER_RE = re.compile(
    r"(?:^|\n)\s*(?:#{1,3}\s*)?(?:\*{1,2})?"
    r"((?:Pre-?flop|Flop|Turn|River)\b[^:\n]*)"
    r"(?:\*{1,2})?[:\s]*\n?",
    re.IGNORECASE,
)


def _extract_street_reviews(advice: str) -> dict[str, str]:
    """Extract per-street analysis sections from the full advice text.

    Looks for headings like "Preflop:", "Flop:", "Turn:", "River:"
    and captures the text under each until the next heading or end.

    Args:
        advice: Full natural-language advice string.

    Returns:
        Dict mapping street name (lowercase) → review text.
    """
    reviews: dict[str, str] = {}
    if not advice:
        return reviews

    matches = list(_STREET_HEADER_RE.finditer(advice))
    if not matches:
        return reviews

    for i, m in enumerate(matches):
        header = m.group(1).strip().lower()
        # Normalize to canonical street name
        street = "preflop"
        if "flop" in header and "pre" not in header:
            street = "flop"
        elif "turn" in header:
            street = "turn"
        elif "river" in header:
            street = "river"

        # Extract body text until next section or end
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(advice)
        body = advice[start:end].strip()

        if body:
            reviews[street] = body

    return reviews


# ──────────────────────────────────────────────
# Table rule extraction
# ──────────────────────────────────────────────

def _extract_table_rule(advice: str, best_action: str, freq: float) -> str:
    """Generate a concise rule-of-thumb for this spot.

    Args:
        advice: Full advice text.
        best_action: Best GTO action, e.g. "BET 67".
        freq: Frequency of best action, 0–1.

    Returns:
        A short heuristic string.
    """
    if not best_action:
        return ""

    if freq >= 0.90:
        return f"Always {best_action.lower()} here — this is a pure play."
    elif freq >= 0.70:
        return f"Strongly prefer {best_action.lower()} ({freq:.0%}) — mix occasionally."
    elif freq >= 0.50:
        return f"Lean toward {best_action.lower()} ({freq:.0%}) but mix actions often."
    else:
        return f"Mixed strategy — no dominant play. {best_action} is slightly preferred."


# ──────────────────────────────────────────────
# Top-level formatter
# ──────────────────────────────────────────────


def _safe_get(obj: Any, attr: str, default: Any = "") -> Any:
    """Read an attribute from a dataclass or dict, returning *default* on miss."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def format_structured_advice(result: dict) -> Optional[StructuredAdviceResponse]:
    """Transform the pipeline result dict into a structured advice response.

    Extracts strategy data, builds top-3 plays sorted by frequency (desc),
    assigns EV signals, extracts per-street reviews from the advice text,
    and generates a table rule heuristic.

    Args:
        result: The dict returned by ``poker_gpt.main.analyze_hand()``.

    Returns:
        A ``StructuredAdviceResponse``, or ``None`` if no advice was generated.
    """
    advice_text = result.get("advice", "")
    if not advice_text:
        return None

    strategy = result.get("strategy")
    source = result.get("source", "unknown")

    # ── Build top plays from strategy actions ──
    top_plays: list[TopPlayResponse] = []

    if strategy is not None:
        actions: dict[str, float] = _safe_get(strategy, "actions", {})
        if actions:
            # Sort by frequency (descending), take top 3
            sorted_actions = sorted(
                actions.items(), key=lambda x: x[1], reverse=True
            )[:3]

            for action, freq in sorted_actions:
                ev_signal = _infer_ev_signal(action, freq)
                top_plays.append(
                    TopPlayResponse(
                        action=action,
                        frequency=round(freq, 4),
                        ev_signal=ev_signal,
                        explanation="",  # Will be enriched by advice text below
                    )
                )

    # If no strategy actions, create a single play from the advice
    if not top_plays and advice_text:
        top_plays.append(
            TopPlayResponse(
                action="See advice",
                frequency=1.0,
                ev_signal=EvSignal.NEUTRAL,
                explanation=advice_text[:200],
            )
        )

    # ── Enrich top play explanations from advice text ──
    # Try to find action-specific mentions in the advice
    for play in top_plays:
        action_lower = play.action.lower()
        # Search for a sentence containing this action
        for sentence in advice_text.split("."):
            sentence = sentence.strip()
            if action_lower in sentence.lower() and len(sentence) > 20:
                play.explanation = sentence + "."
                break

    # ── Extract street-by-street reviews ──
    street_reviews = _extract_street_reviews(advice_text)

    # ── Generate table rule ──
    best_action = ""
    best_freq = 0.0
    if strategy is not None:
        best_action = _safe_get(strategy, "best_action", "")
        best_freq = float(_safe_get(strategy, "best_action_freq", 0.0))
    elif top_plays:
        best_action = top_plays[0].action
        best_freq = top_plays[0].frequency

    table_rule = _extract_table_rule(advice_text, best_action, best_freq)

    # ── Compute confidence score ──
    confidence_score = _CONFIDENCE_SCORES.get(source, 0.75)

    # ── Future streets guidance ──
    future_streets = ""
    # Look for forward-looking language in the advice
    future_patterns = [
        r"(?:on the turn|on the river|future streets?|going forward|next street)",
        r"(?:if .{5,40}(?:comes|arrives|hits|falls|peels))",
    ]
    for pattern in future_patterns:
        match = re.search(pattern, advice_text, re.IGNORECASE)
        if match:
            # Grab the sentence containing the match
            start = max(0, advice_text.rfind(".", 0, match.start()) + 1)
            end = advice_text.find(".", match.end())
            if end == -1:
                end = len(advice_text)
            snippet = advice_text[start:end + 1].strip()
            if snippet and len(snippet) > 20:
                future_streets = snippet
                break

    return StructuredAdviceResponse(
        top_plays=top_plays,
        street_reviews=street_reviews,
        future_streets=future_streets,
        table_rule=table_rule,
        raw_advice=advice_text,
    )

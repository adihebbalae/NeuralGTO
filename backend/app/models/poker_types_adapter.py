"""
backend/app/models/poker_types_adapter.py — Bridge poker_gpt dataclasses ↔ Pydantic schemas.

Converts the pipeline's internal dataclasses (ScenarioData, StrategyResult,
StructuredAdvice) into the Pydantic response models defined in schemas.py.
This keeps the pipeline code untouched while giving endpoints clean JSON.

Created: 2026-03-03

DOCUMENTATION:
    Usage in an endpoint::

        from backend.app.models.poker_types_adapter import serialize_pipeline_result
        result = analyze_hand(query=body.query, mode=body.mode, ...)
        return serialize_pipeline_result(result)

    The adapter never imports Gemini, the solver, or any I/O module.
    It is a pure data-transformation layer.
"""

from __future__ import annotations

from typing import Any, Optional

from backend.app.models.schemas import (
    AnalysisMode,
    AnalyzeResponse,
    EvSignal,
    OutputLevel,
    ScenarioResponse,
    StrategyResponse,
    StrategySource,
    StructuredAdviceResponse,
    TopPlayResponse,
)


def _safe_get(obj: Any, attr: str, default: Any = "") -> Any:
    """Read an attribute from a dataclass or dict, returning *default* on miss."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def _to_strategy_source(raw: str) -> StrategySource:
    """Map free-text source strings to the enum, with a sensible fallback."""
    mapping = {
        "solver": StrategySource.SOLVER,
        "gemini": StrategySource.GEMINI,
        "gpt_fallback": StrategySource.GPT_FALLBACK,
        "validation_error": StrategySource.VALIDATION_ERROR,
    }
    return mapping.get(raw, StrategySource.GEMINI)


def _to_analysis_mode(raw: str) -> AnalysisMode:
    """Map raw mode string to the enum."""
    mapping = {
        "fast": AnalysisMode.FAST,
        "default": AnalysisMode.DEFAULT,
        "pro": AnalysisMode.PRO,
    }
    return mapping.get(raw, AnalysisMode.DEFAULT)


def _to_output_level(raw: str) -> OutputLevel:
    """Map raw output_level string to the enum."""
    mapping = {
        "beginner": OutputLevel.BEGINNER,
        "advanced": OutputLevel.ADVANCED,
    }
    return mapping.get(raw, OutputLevel.ADVANCED)


def _to_ev_signal(raw: str) -> EvSignal:
    """Map raw ev_signal string to the enum."""
    mapping = {
        "positive": EvSignal.POSITIVE,
        "negative": EvSignal.NEGATIVE,
        "neutral": EvSignal.NEUTRAL,
    }
    return mapping.get(raw, EvSignal.NEUTRAL)


# ──────────────────────────────────────────────
# Individual converters
# ──────────────────────────────────────────────


def scenario_to_response(scenario: Any) -> Optional[ScenarioResponse]:
    """Convert a ``poker_gpt.poker_types.ScenarioData`` → ``ScenarioResponse``.

    Returns ``None`` if *scenario* is ``None``.
    """
    if scenario is None:
        return None
    return ScenarioResponse(
        hero_hand=_safe_get(scenario, "hero_hand", ""),
        hero_position=_safe_get(scenario, "hero_position", ""),
        board=_safe_get(scenario, "board", ""),
        pot_size_bb=float(_safe_get(scenario, "pot_size_bb", 0.0)),
        effective_stack_bb=float(_safe_get(scenario, "effective_stack_bb", 0.0)),
        current_street=_safe_get(scenario, "current_street", ""),
        hero_is_ip=bool(_safe_get(scenario, "hero_is_ip", False)),
        num_players_preflop=int(_safe_get(scenario, "num_players_preflop", 2)),
        game_type=_safe_get(scenario, "game_type", "cash"),
        stack_depth_bb=float(_safe_get(scenario, "stack_depth_bb", 100.0)),
        oop_range=_safe_get(scenario, "oop_range", ""),
        ip_range=_safe_get(scenario, "ip_range", ""),
    )


def strategy_to_response(strategy: Any) -> Optional[StrategyResponse]:
    """Convert a ``poker_gpt.poker_types.StrategyResult`` → ``StrategyResponse``.

    Returns ``None`` if *strategy* is ``None``.
    """
    if strategy is None:
        return None
    raw_source = _safe_get(strategy, "source", "solver")
    return StrategyResponse(
        hand=_safe_get(strategy, "hand", ""),
        actions=_safe_get(strategy, "actions", {}),
        best_action=_safe_get(strategy, "best_action", ""),
        best_action_freq=float(_safe_get(strategy, "best_action_freq", 0.0)),
        range_summary=_safe_get(strategy, "range_summary", {}),
        source=_to_strategy_source(raw_source),
    )


def structured_advice_to_response(
    sa: Any,
) -> Optional[StructuredAdviceResponse]:
    """Convert a ``poker_gpt.poker_types.StructuredAdvice`` → ``StructuredAdviceResponse``.

    Returns ``None`` if *sa* is ``None``.
    """
    if sa is None:
        return None

    top_plays: list[TopPlayResponse] = []
    for tp in _safe_get(sa, "top_plays", []):
        top_plays.append(
            TopPlayResponse(
                action=_safe_get(tp, "action", ""),
                frequency=float(_safe_get(tp, "frequency", 0.0)),
                ev_signal=_to_ev_signal(_safe_get(tp, "ev_signal", "neutral")),
                explanation=_safe_get(tp, "explanation", ""),
            )
        )

    return StructuredAdviceResponse(
        top_plays=top_plays,
        street_reviews=_safe_get(sa, "street_reviews", {}),
        future_streets=_safe_get(sa, "future_streets", ""),
        table_rule=_safe_get(sa, "table_rule", ""),
        raw_advice=_safe_get(sa, "raw_advice", ""),
    )


# ──────────────────────────────────────────────
# Top-level converter
# ──────────────────────────────────────────────


def serialize_pipeline_result(result: dict) -> AnalyzeResponse:
    """Transform the dict returned by ``analyze_hand()`` into an ``AnalyzeResponse``.

    This is the single entry point that endpoints should call. It handles
    all dataclass → Pydantic conversion and gracefully degrades when
    fields are missing.

    Args:
        result: The dict returned by ``poker_gpt.main.analyze_hand()``.

    Returns:
        A fully-populated ``AnalyzeResponse`` ready for JSON serialisation.
    """
    return AnalyzeResponse(
        advice=result.get("advice", ""),
        source=_to_strategy_source(result.get("source", "unknown")),
        confidence=result.get("confidence", "low"),
        mode=_to_analysis_mode(result.get("mode", "default")),
        cached=result.get("cached", False),
        solve_time=result.get("solve_time", 0.0),
        parse_time=result.get("parse_time", 0.0),
        output_level=_to_output_level(result.get("output_level", "advanced")),
        sanity_note=result.get("sanity_note", ""),
        scenario=scenario_to_response(result.get("scenario")),
        strategy=strategy_to_response(result.get("strategy")),
        structured_advice=structured_advice_to_response(
            result.get("structured_advice")
        ),
    )

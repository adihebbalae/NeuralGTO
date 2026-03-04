"""
backend/app/api/analyze.py — POST /api/analyze endpoint.

Wraps ``poker_gpt.main.analyze_hand()`` as an HTTP endpoint.
Accepts natural-language or structured poker scenarios, runs the full
GTO pipeline (parse → solver → extract → advise), and returns a
JSON response conforming to ``AnalyzeResponse``.

Created: 2026-03-03

DOCUMENTATION:
    Register this router in ``app/main.py``::

        from app.api.analyze import router as analyze_router
        app.include_router(analyze_router)

    Endpoint::

        POST /api/analyze
        Content-Type: application/json

        {
            "query": "I have QhQd on the BTN, 100bb deep, folds to me",
            "mode": "default",
            "opponent_notes": ""
        }

    Response: ``AnalyzeResponse`` (see ``app/models/schemas.py``).
"""

from __future__ import annotations

import asyncio
import logging
import time
from functools import partial

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.models.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ErrorResponse,
    ReanalyzeStreetRequest,
)
from app.models.poker_types_adapter import serialize_pipeline_result

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Pipeline import — optional so the backend can start even without
# poker_gpt installed (e.g. for health-check-only deploys).
# ──────────────────────────────────────────────

try:
    from poker_gpt.main import analyze_hand as _analyze_hand  # noqa: WPS433
except ImportError:
    _analyze_hand = None  # type: ignore[assignment]

router = APIRouter(prefix="/api", tags=["analysis"])

# ──────────────────────────────────────────────
# Rate limiter (re-uses the app-level limiter instance)
# ──────────────────────────────────────────────

_limiter = Limiter(key_func=get_remote_address)


def _build_query(body: AnalyzeRequest) -> str:
    """Build a natural-language query string from the request body.

    If ``body.query`` is provided, use it directly.  Otherwise, assemble
    a query from the structured fields (hero_hand, hero_position, board, etc.).

    Returns:
        A non-empty query string ready for ``analyze_hand()``.

    Raises:
        ValueError: If neither ``query`` nor ``hero_hand`` is set.
    """
    if body.query:
        return body.query

    if not body.hero_hand:
        raise ValueError(
            "Either 'query' (natural language) or 'hero_hand' (structured) "
            "must be provided."
        )

    # Assemble a minimal NL query from structured fields
    parts: list[str] = [f"I have {body.hero_hand}"]
    if body.hero_position:
        parts.append(f"on the {body.hero_position}")
    if body.board:
        parts.append(f"board is {body.board}")
    if body.pot_size_bb is not None:
        parts.append(f"pot is {body.pot_size_bb}bb")
    if body.effective_stack_bb is not None:
        parts.append(f"{body.effective_stack_bb}bb effective")
    if body.villain_position:
        parts.append(f"vs {body.villain_position}")

    return ", ".join(parts) + "."


# ──────────────────────────────────────────────
# POST /api/analyze
# ──────────────────────────────────────────────


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid input"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        429: {"model": ErrorResponse, "description": "Rate limited"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Analyse a poker hand",
    description=(
        "Submit a poker scenario (free-text or structured) and receive "
        "GTO strategy analysis with natural-language explanation."
    ),
)
@_limiter.limit("10/minute")
async def analyze(request: Request, body: AnalyzeRequest) -> AnalyzeResponse:
    """Run the NeuralGTO analysis pipeline and return the result.

    The pipeline runs synchronously (CPU-bound solver + Gemini API calls),
    so we offload it to a thread via ``asyncio.to_thread`` to avoid blocking
    the event loop.

    Args:
        request: FastAPI request (required by slowapi rate limiter).
        body: Validated ``AnalyzeRequest`` from the JSON body.

    Returns:
        ``AnalyzeResponse`` with advice, strategy, and metadata.
    """
    # ── Build query ──
    try:
        query = _build_query(body)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(
                detail=str(exc),
                error_code="VALIDATION_ERROR",
            ).model_dump(),
        )

    # ── Lazy import to avoid loading the heavy pipeline at module import ──
    # This also means tests can mock the import target easily.
    if _analyze_hand is None:
        logger.error("poker_gpt pipeline not installed")
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                detail="Analysis pipeline is not available.",
                error_code="INTERNAL_ERROR",
            ).model_dump(),
        )

    # ── Run the pipeline in a thread (it's synchronous + blocking) ──
    t0 = time.monotonic()
    try:
        # functools.partial lets us pass kwargs cleanly to to_thread
        result: dict = await asyncio.to_thread(
            partial(
                _analyze_hand,
                query=query,
                mode=body.mode.value,
                opponent_notes=body.opponent_notes,
                output_level=body.output_level.value,
            )
        )
    except ValueError as exc:
        logger.warning("Pipeline ValueError: %s", exc)
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(
                detail=str(exc),
                error_code="PARSE_FAILED",
            ).model_dump(),
        )
    except TimeoutError as exc:
        logger.warning("Pipeline timeout: %s", exc)
        return JSONResponse(
            status_code=504,
            content=ErrorResponse(
                detail="Solver timed out. Try 'fast' mode for instant results.",
                error_code="SOLVER_TIMEOUT",
            ).model_dump(),
        )
    except Exception as exc:
        # Never crash — degrade gracefully
        logger.exception("Unexpected pipeline error")
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                detail="An internal error occurred. Please try again.",
                error_code="INTERNAL_ERROR",
            ).model_dump(),
        )

    elapsed = time.monotonic() - t0
    logger.info("Analysis completed in %.2fs (mode=%s)", elapsed, body.mode.value)

    # ── Serialize pipeline dict → Pydantic response ──
    try:
        response = serialize_pipeline_result(result)
    except Exception as exc:
        logger.exception("Failed to serialize pipeline result")
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                detail="Failed to format analysis result.",
                error_code="INTERNAL_ERROR",
            ).model_dump(),
        )

    return response


# ──────────────────────────────────────────────
# POST /api/reanalyze-street
# ──────────────────────────────────────────────


@router.post(
    "/reanalyze-street",
    response_model=AnalyzeResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid input"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        429: {"model": ErrorResponse, "description": "Rate limited"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Re-analyse with new board cards",
    description=(
        "Re-run the solver with new turn/river cards. Used by the interactive "
        "card picker to step through streets dynamically."
    ),
)
@_limiter.limit("10/minute")
async def reanalyze_street(
    request: Request, body: ReanalyzeStreetRequest
) -> AnalyzeResponse:
    """Re-run analysis with new board cards appended.

    Takes the current scenario state and new board cards, constructs a
    natural-language query, and calls analyze_hand() with the updated board.

    Args:
        request: FastAPI request (required by slowapi rate limiter).
        body: Validated ReanalyzeStreetRequest from the JSON body.

    Returns:
        AnalyzeResponse with updated advice and strategy for the new street.
    """
    # ── Check if pipeline is available ──
    if _analyze_hand is None:
        logger.error("poker_gpt pipeline not installed")
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                detail="Analysis pipeline is not available.",
                error_code="INTERNAL_ERROR",
            ).model_dump(),
        )

    # ── Build updated board string ──
    current_cards = [c.strip() for c in body.current_board.split(",") if c.strip()]
    new_cards = [c.strip() for c in body.new_board_cards.split(",") if c.strip()]
    updated_board = ",".join(current_cards + new_cards)

    # ── Construct natural-language query for the new street ──
    # This mirrors the _build_query logic but for reanalysis
    parts: list[str] = [f"I have {body.hero_hand}"]
    if body.hero_position:
        parts.append(f"on the {body.hero_position}")
    if updated_board:
        parts.append(f"board is {updated_board}")
    parts.append(f"pot is {body.pot_size_bb}bb")
    parts.append(f"{body.effective_stack_bb}bb effective")
    if body.villain_position:
        parts.append(f"vs {body.villain_position}")

    query = ", ".join(parts) + "."

    logger.info(
        "Reanalyzing street: %s → %s (new cards: %s)",
        body.current_board or "preflop",
        updated_board,
        body.new_board_cards,
    )

    # ── Run the pipeline in a thread ──
    t0 = time.monotonic()
    try:
        result: dict = await asyncio.to_thread(
            partial(
                _analyze_hand,
                query=query,
                mode=body.mode.value,
                opponent_notes=body.opponent_notes,
                output_level=body.output_level.value,
            )
        )
    except ValueError as exc:
        logger.warning("Pipeline ValueError: %s", exc)
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(
                detail=str(exc),
                error_code="PARSE_FAILED",
            ).model_dump(),
        )
    except TimeoutError as exc:
        logger.warning("Pipeline timeout: %s", exc)
        return JSONResponse(
            status_code=504,
            content=ErrorResponse(
                detail="Solver timed out. Try 'fast' mode for instant results.",
                error_code="SOLVER_TIMEOUT",
            ).model_dump(),
        )
    except Exception as exc:
        logger.exception("Unexpected pipeline error during reanalysis")
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                detail="An internal error occurred. Please try again.",
                error_code="INTERNAL_ERROR",
            ).model_dump(),
        )

    elapsed = time.monotonic() - t0
    logger.info("Reanalysis completed in %.2fs (mode=%s)", elapsed, body.mode.value)

    # ── Serialize pipeline dict → Pydantic response ──
    try:
        response = serialize_pipeline_result(result)
    except Exception as exc:
        logger.exception("Failed to serialize reanalysis result")
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                detail="Failed to format analysis result.",
                error_code="INTERNAL_ERROR",
            ).model_dump(),
        )

    return response

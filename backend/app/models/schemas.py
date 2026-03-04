"""
backend/app/models/schemas.py — Shared API contract (Pydantic models).

Canonical request/response models for the NeuralGTO API. Every endpoint
uses these models as the single source of truth.  The React frontend
mirrors them via TypeScript interfaces in ``frontend/src/types/api.ts``.

Created: 2026-03-03

DOCUMENTATION:
    Import from here in endpoint code:
        from backend.app.models.schemas import AnalyzeRequest, AnalyzeResponse

    These models MUST stay in sync with:
        - frontend/src/types/api.ts   (TypeScript mirror)
        - backend/docs/API_CONTRACT.md (human-readable reference)
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────────
# Validation helpers (shared across request models)
# ──────────────────────────────────────────────

# Whitelist: letters, digits, common poker symbols, basic punctuation.
# Rejects control chars, angle brackets, backticks, and injection vectors.
_SAFE_TEXT_RE = re.compile(
    r"^[A-Za-z0-9\s,.\-;:!?'\"()\[\]$%/+=♠♥♦♣♤♡♢♧#@&*]+$"
)

# Card pattern: rank (2-9TJQKAtjqka) + suit (hdcsHDCS)
_CARD_RE = re.compile(r"^[2-9TJQKAtjqka][hdcsHDCS]$")

# Board pattern: 0, 3, 4, or 5 cards (comma-separated or concatenated)
_BOARD_RE = re.compile(
    r"^$|"                                           # empty (preflop)
    r"^[2-9TJQKAtjqka][hdcsHDCS]"                    # at least one card
    r"(,?[2-9TJQKAtjqka][hdcsHDCS]){2,4}$"           # 2-4 more cards
)


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class AnalysisMode(str, Enum):
    """Solver depth modes."""
    FAST = "fast"          # LLM-only, no solver
    DEFAULT = "default"    # solver, 100 iters, 2% accuracy
    PRO = "pro"            # solver, 500 iters, 0.3% accuracy


class OutputLevel(str, Enum):
    """Advice verbosity."""
    BEGINNER = "beginner"
    ADVANCED = "advanced"


class StrategySource(str, Enum):
    """Where the strategy came from."""
    SOLVER = "solver"
    GEMINI = "gemini"
    GPT_FALLBACK = "gpt_fallback"
    VALIDATION_ERROR = "validation_error"


class EvSignal(str, Enum):
    """Expected value direction for a play."""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class Position(str, Enum):
    """Standard poker positions."""
    UTG = "UTG"
    LJ = "LJ"
    HJ = "HJ"
    CO = "CO"
    BTN = "BTN"
    SB = "SB"
    BB = "BB"


class Street(str, Enum):
    """Poker betting rounds."""
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"


# ══════════════════════════════════════════════
# REQUEST models
# ══════════════════════════════════════════════


class AnalyzeRequest(BaseModel):
    """POST /api/analyze — request body.

    Supports TWO input modes:
      1. **Natural language** — set ``query`` to a free-text poker scenario.
      2. **Structured** — set ``hero_hand``, ``hero_position``, ``board``,
         etc. directly (used by the React card picker UI).

    At least ``query`` OR ``hero_hand`` must be provided.
    """

    # ── Natural language input ──
    query: str = Field(
        default="",
        max_length=2000,
        description=(
            "Free-text poker scenario. If provided, structured fields "
            "are ignored and the NL parser extracts everything."
        ),
        examples=["I have AKs on the BTN, 100bb deep. Folds to me."],
    )

    # ── Structured input (used by React UI) ──
    hero_hand: str = Field(
        default="",
        max_length=10,
        description="Hero's hole cards, e.g. 'AhKs' or 'QQ'.",
        examples=["AhKs", "QhQd"],
    )
    hero_position: str = Field(
        default="",
        max_length=5,
        description="Hero's table position.",
        examples=["BTN", "CO", "BB"],
    )
    board: str = Field(
        default="",
        max_length=20,
        description="Community cards (empty for preflop). E.g. 'Ts,9d,4h'.",
        examples=["Ts,9d,4h", "Kc,Qc,2h,7s"],
    )
    pot_size_bb: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=5000.0,
        description="Current pot size in big blinds.",
    )
    effective_stack_bb: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=5000.0,
        description="Effective remaining stack in big blinds.",
    )
    villain_position: str = Field(
        default="",
        max_length=5,
        description="Villain's table position.",
        examples=["BB", "SB", "CO"],
    )

    # ── Shared options ──
    mode: AnalysisMode = Field(
        default=AnalysisMode.DEFAULT,
        description="Analysis depth: fast (LLM-only) | default | pro.",
    )
    opponent_notes: str = Field(
        default="",
        max_length=500,
        description="Optional villain-tendency notes for exploitative advice.",
    )
    output_level: OutputLevel = Field(
        default=OutputLevel.ADVANCED,
        description="Advice verbosity: beginner | advanced.",
    )

    # ── Validators ──

    @field_validator("query")
    @classmethod
    def _query_safe(cls, v: str) -> str:
        v = v.strip()
        if v and not _SAFE_TEXT_RE.match(v):
            raise ValueError(
                "Query contains disallowed characters. "
                "Use only letters, numbers, and standard punctuation."
            )
        return v

    @field_validator("hero_hand")
    @classmethod
    def _hero_hand_safe(cls, v: str) -> str:
        v = v.strip()
        if v and len(v) < 2:
            raise ValueError("hero_hand must be at least 2 characters (e.g. 'AKs').")
        return v

    @field_validator("hero_position", "villain_position")
    @classmethod
    def _position_upper(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("board")
    @classmethod
    def _board_safe(cls, v: str) -> str:
        v = v.strip()
        if v and not _BOARD_RE.match(v):
            raise ValueError(
                "Board must be 0, 3, 4, or 5 valid cards "
                "(e.g. 'Ts,9d,4h' or 'Kc,Qc,2h,7s')."
            )
        return v

    @field_validator("opponent_notes")
    @classmethod
    def _opp_notes_safe(cls, v: str) -> str:
        v = v.strip()
        if v and not _SAFE_TEXT_RE.match(v):
            raise ValueError("Opponent notes contain disallowed characters.")
        return v


class BoardUpdateRequest(BaseModel):
    """POST /api/board/update — append a turn/river card and re-analyse.

    Used by the interactive card picker in the React frontend.
    """

    query: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Original NL scenario description.",
    )
    new_card: str = Field(
        ...,
        min_length=2,
        max_length=2,
        description="Card to add, e.g. 'Ah', '9c'.",
    )
    mode: AnalysisMode = Field(default=AnalysisMode.DEFAULT)
    opponent_notes: str = Field(default="", max_length=500)
    output_level: OutputLevel = Field(default=OutputLevel.ADVANCED)

    @field_validator("query")
    @classmethod
    def _query_safe(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Query must not be empty.")
        if not _SAFE_TEXT_RE.match(v):
            raise ValueError("Query contains disallowed characters.")
        return v

    @field_validator("new_card")
    @classmethod
    def _card_valid(cls, v: str) -> str:
        v = v.strip()
        if not _CARD_RE.match(v):
            raise ValueError(
                "new_card must be a valid card like 'Ah', '9c', 'Td'."
            )
        return v[0].upper() + v[1].lower()

    @field_validator("opponent_notes")
    @classmethod
    def _opp_safe(cls, v: str) -> str:
        v = v.strip()
        if v and not _SAFE_TEXT_RE.match(v):
            raise ValueError("Opponent notes contain disallowed characters.")
        return v


class ReanalyzeStreetRequest(BaseModel):
    """POST /api/reanalyze-street — re-run solver with new board cards.

    Used by the interactive turn/river card picker. Takes the current scenario
    from a prior analysis and new board cards, then re-runs the full pipeline.
    """

    # Current scenario state (from prior /api/analyze response)
    hero_hand: str = Field(
        ...,
        min_length=2,
        max_length=10,
        description="Hero's hole cards, e.g. 'AhKs'.",
    )
    hero_position: str = Field(
        ...,
        max_length=5,
        description="Hero's position.",
    )
    current_board: str = Field(
        default="",
        max_length=20,
        description="Current board cards (may be empty for preflop).",
    )
    pot_size_bb: float = Field(
        ...,
        ge=0.0,
        le=5000.0,
        description="Current pot size in big blinds.",
    )
    effective_stack_bb: float = Field(
        ...,
        ge=0.0,
        le=5000.0,
        description="Effective stack in big blinds.",
    )
    villain_position: str = Field(
        default="",
        max_length=5,
        description="Villain's position.",
    )

    # New cards to add
    new_board_cards: str = Field(
        ...,
        min_length=2,
        max_length=20,
        description="New cards to add to board, e.g. 'Ah,9c,Kd' or 'As' for one card.",
    )

    # Analysis options
    mode: AnalysisMode = Field(default=AnalysisMode.DEFAULT)
    opponent_notes: str = Field(default="", max_length=500)
    output_level: OutputLevel = Field(default=OutputLevel.ADVANCED)

    @field_validator("hero_hand")
    @classmethod
    def _hero_hand_safe(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("hero_hand must be at least 2 characters.")
        return v

    @field_validator("hero_position", "villain_position")
    @classmethod
    def _position_upper(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("current_board", "new_board_cards")
    @classmethod
    def _board_safe(cls, v: str) -> str:
        v = v.strip()
        # Allow empty for current_board (preflop case)
        if v and not _BOARD_RE.match(v) and not _CARD_RE.match(v):
            # Also accept single card format for new_board_cards
            raise ValueError(
                "Board cards must be valid poker cards (e.g. 'Ah,9c' or 'Kd')."
            )
        return v

    @field_validator("opponent_notes")
    @classmethod
    def _opp_notes_safe(cls, v: str) -> str:
        v = v.strip()
        if v and not _SAFE_TEXT_RE.match(v):
            raise ValueError("Opponent notes contain disallowed characters.")
        return v


# ══════════════════════════════════════════════
# RESPONSE models
# ══════════════════════════════════════════════


class ActionEntryResponse(BaseModel):
    """A single action in the parsed hand history."""

    position: str = ""
    action: str = ""
    amount_bb: Optional[float] = None
    street: str = "preflop"


class ScenarioResponse(BaseModel):
    """Parsed scenario data returned to the frontend."""

    hero_hand: str = ""
    hero_position: str = ""
    board: str = ""
    pot_size_bb: float = 0.0
    effective_stack_bb: float = 0.0
    current_street: str = ""
    hero_is_ip: bool = False
    num_players_preflop: int = 2
    game_type: str = "cash"
    stack_depth_bb: float = 100.0
    oop_range: str = ""
    ip_range: str = ""


class TopPlayResponse(BaseModel):
    """A single recommended play with explanation."""

    action: str = Field(description="Action label, e.g. 'BET 67', 'CHECK'.")
    frequency: float = Field(ge=0.0, le=1.0, description="GTO frequency 0–1.")
    ev_signal: EvSignal = Field(
        default=EvSignal.NEUTRAL,
        description="EV direction: positive | negative | neutral.",
    )
    explanation: str = Field(
        default="",
        description="LLM-generated explanation for why this play is recommended.",
    )


class StrategyResponse(BaseModel):
    """Solver or LLM strategy for hero's specific hand."""

    hand: str = Field(default="", description="Hero's hole cards, e.g. 'QhQd'.")
    actions: dict[str, float] = Field(
        default_factory=dict,
        description="Action → GTO frequency map, e.g. {'CHECK': 0.15, 'BET 67': 0.60}.",
    )
    best_action: str = Field(default="", description="Highest-frequency action.")
    best_action_freq: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Frequency of the best action (0–1).",
    )
    range_summary: dict[str, float] = Field(
        default_factory=dict,
        description="Range-wide aggregated frequencies.",
    )
    source: StrategySource = Field(
        default=StrategySource.SOLVER,
        description="Where the strategy came from: solver | gemini | gpt_fallback.",
    )


class StructuredAdviceResponse(BaseModel):
    """Structured GTO advice breakdown for the React UI."""

    top_plays: list[TopPlayResponse] = Field(
        default_factory=list,
        description="Top recommended plays ranked by frequency.",
    )
    street_reviews: dict[str, str] = Field(
        default_factory=dict,
        description="Per-street analysis text, keyed by street name.",
    )
    future_streets: str = Field(
        default="",
        description="Forward-looking advice for upcoming streets.",
    )
    table_rule: str = Field(
        default="",
        description="Short heuristic rule-of-thumb for this spot.",
    )
    raw_advice: str = Field(
        default="",
        description="Full unstructured advisor text (fallback display).",
    )


class AnalyzeResponse(BaseModel):
    """POST /api/analyze — response body.

    Contains the full analysis result: advice text, parsed scenario,
    solver strategy, and structured advice breakdown.
    """

    # Core result
    advice: str = Field(
        description="Full natural-language GTO advice.",
    )
    source: StrategySource = Field(
        description="Where the strategy came from.",
    )
    confidence: str = Field(
        default="low",
        description="Confidence level: low | medium | high.",
    )

    # Timing & metadata
    mode: AnalysisMode = Field(
        default=AnalysisMode.DEFAULT,
        description="Analysis mode used for this request.",
    )
    cached: bool = Field(
        default=False,
        description="Whether the result was served from cache.",
    )
    solve_time: float = Field(
        default=0.0, ge=0.0,
        description="Solver wall-clock time in seconds.",
    )
    parse_time: float = Field(
        default=0.0, ge=0.0,
        description="NL parser wall-clock time in seconds.",
    )
    output_level: OutputLevel = Field(
        default=OutputLevel.ADVANCED,
        description="Verbosity level used.",
    )
    sanity_note: str = Field(
        default="",
        description="Optional sanity-checker annotation.",
    )

    # Nested objects (optional — absent on validation errors)
    scenario: Optional[ScenarioResponse] = Field(
        default=None,
        description="Parsed scenario if NL parsing succeeded.",
    )
    strategy: Optional[StrategyResponse] = Field(
        default=None,
        description="Solver/LLM strategy if extraction succeeded.",
    )
    structured_advice: Optional[StructuredAdviceResponse] = Field(
        default=None,
        description="Structured advice breakdown for UI rendering.",
    )


class HealthResponse(BaseModel):
    """GET /api/health — liveness/readiness check."""

    status: Literal["ok", "degraded", "error"] = Field(
        default="ok",
        description="Service health: ok | degraded | error.",
    )
    solver_available: bool = Field(
        default=False,
        description="Whether the TexasSolver binary is reachable.",
    )
    version: str = Field(
        default="0.1.0",
        description="API version string.",
    )


class ErrorResponse(BaseModel):
    """Standard error envelope for all 4xx/5xx responses.

    Example::

        {
            "detail": "Hero hand 'XYZ' is not a valid poker hand.",
            "error_code": "INVALID_HAND"
        }
    """

    detail: str = Field(description="Human-readable error message.")
    error_code: str = Field(
        default="UNKNOWN",
        description=(
            "Machine-readable error code. Known codes: "
            "INVALID_HAND, INVALID_BOARD, INVALID_POSITION, "
            "PARSE_FAILED, SOLVER_TIMEOUT, RATE_LIMITED, "
            "INTERNAL_ERROR, VALIDATION_ERROR."
        ),
    )

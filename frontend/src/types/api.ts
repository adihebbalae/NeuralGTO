/**
 * frontend/src/types/api.ts — Shared API contract (TypeScript interfaces).
 *
 * Mirrors the Pydantic models in backend/app/models/schemas.py exactly.
 * Includes Zod schemas for runtime validation of API responses.
 *
 * IMPORTANT: When updating Pydantic models, update this file too.
 *   - backend/app/models/schemas.py  (source of truth)
 *   - backend/docs/API_CONTRACT.md   (human-readable reference)
 *
 * Created: 2026-03-03
 */

import { z } from "zod";

// ──────────────────────────────────────────────
// Enums
// ──────────────────────────────────────────────

export const AnalysisMode = {
  FAST: "fast",
  DEFAULT: "default",
  PRO: "pro",
} as const;
export type AnalysisMode = (typeof AnalysisMode)[keyof typeof AnalysisMode];

export const OutputLevel = {
  BEGINNER: "beginner",
  ADVANCED: "advanced",
} as const;
export type OutputLevel = (typeof OutputLevel)[keyof typeof OutputLevel];

export const StrategySource = {
  SOLVER: "solver",
  GEMINI: "gemini",
  GPT_FALLBACK: "gpt_fallback",
  VALIDATION_ERROR: "validation_error",
} as const;
export type StrategySource =
  (typeof StrategySource)[keyof typeof StrategySource];

export const EvSignal = {
  POSITIVE: "positive",
  NEGATIVE: "negative",
  NEUTRAL: "neutral",
} as const;
export type EvSignal = (typeof EvSignal)[keyof typeof EvSignal];

export const Position = {
  UTG: "UTG",
  LJ: "LJ",
  HJ: "HJ",
  CO: "CO",
  BTN: "BTN",
  SB: "SB",
  BB: "BB",
} as const;
export type Position = (typeof Position)[keyof typeof Position];

export const Street = {
  PREFLOP: "preflop",
  FLOP: "flop",
  TURN: "turn",
  RIVER: "river",
} as const;
export type Street = (typeof Street)[keyof typeof Street];

// ══════════════════════════════════════════════
// REQUEST interfaces
// ══════════════════════════════════════════════

/** POST /api/analyze — request body. */
export interface AnalyzeRequest {
  /** Free-text poker scenario (NL mode). */
  query?: string;

  /** Hero's hole cards, e.g. "AhKs" or "QQ" (structured mode). */
  hero_hand?: string;

  /** Hero's table position, e.g. "BTN", "CO". */
  hero_position?: string;

  /** Community cards (empty for preflop), e.g. "Ts,9d,4h". */
  board?: string;

  /** Current pot size in big blinds. */
  pot_size_bb?: number;

  /** Effective remaining stack in big blinds. */
  effective_stack_bb?: number;

  /** Villain's table position. */
  villain_position?: string;

  /** Analysis depth: "fast" | "default" | "pro". */
  mode?: AnalysisMode;

  /** Optional villain-tendency notes for exploitative advice. */
  opponent_notes?: string;

  /** Advice verbosity: "beginner" | "advanced". */
  output_level?: OutputLevel;
}

/** POST /api/board/update — request body. */
export interface BoardUpdateRequest {
  /** Original NL scenario description. */
  query: string;

  /** Card to add, e.g. "Ah", "9c". */
  new_card: string;

  /** Analysis depth. */
  mode?: AnalysisMode;

  /** Optional villain-tendency notes. */
  opponent_notes?: string;

  /** Advice verbosity. */
  output_level?: OutputLevel;
}

// ══════════════════════════════════════════════
// RESPONSE interfaces
// ══════════════════════════════════════════════

/** A single action in the parsed hand history. */
export interface ActionEntryResponse {
  position: string;
  action: string;
  amount_bb: number | null;
  street: string;
}

/** Parsed scenario data returned from the API. */
export interface ScenarioResponse {
  hero_hand: string;
  hero_position: string;
  board: string;
  pot_size_bb: number;
  effective_stack_bb: number;
  current_street: string;
  hero_is_ip: boolean;
  num_players_preflop: number;
  game_type: string;
  stack_depth_bb: number;
  oop_range: string;
  ip_range: string;
}

/** A single recommended play with explanation. */
export interface TopPlayResponse {
  /** Action label, e.g. "BET 67", "CHECK". */
  action: string;
  /** GTO frequency 0–1. */
  frequency: number;
  /** EV direction: "positive" | "negative" | "neutral". */
  ev_signal: EvSignal;
  /** Explanation for why this play is recommended. */
  explanation: string;
}

/** Solver or LLM strategy for hero's specific hand. */
export interface StrategyResponse {
  /** Hero's hole cards, e.g. "QhQd". */
  hand: string;
  /** Action → GTO frequency map. */
  actions: Record<string, number>;
  /** Highest-frequency action. */
  best_action: string;
  /** Frequency of the best action (0–1). */
  best_action_freq: number;
  /** Range-wide aggregated frequencies. */
  range_summary: Record<string, number>;
  /** Where the strategy came from. */
  source: StrategySource;
}

/** Structured GTO advice breakdown for UI rendering. */
export interface StructuredAdviceResponse {
  /** Top recommended plays ranked by frequency. */
  top_plays: TopPlayResponse[];
  /** Per-street analysis text, keyed by street name. */
  street_reviews: Record<string, string>;
  /** Forward-looking advice for upcoming streets. */
  future_streets: string;
  /** Short heuristic rule-of-thumb for this spot. */
  table_rule: string;
  /** Full unstructured advisor text (fallback display). */
  raw_advice: string;
}

/** POST /api/analyze — response body. */
export interface AnalyzeResponse {
  /** Full natural-language GTO advice. */
  advice: string;
  /** Where the strategy came from. */
  source: StrategySource;
  /** Confidence level: "low" | "medium" | "high". */
  confidence: string;

  /** Analysis mode used. */
  mode: AnalysisMode;
  /** Whether the result was served from cache. */
  cached: boolean;
  /** Solver wall-clock time in seconds. */
  solve_time: number;
  /** NL parser wall-clock time in seconds. */
  parse_time: number;
  /** Verbosity level used. */
  output_level: OutputLevel;
  /** Optional sanity-checker annotation. */
  sanity_note: string;

  /** Parsed scenario (null on validation errors). */
  scenario: ScenarioResponse | null;
  /** Solver/LLM strategy (null on validation errors). */
  strategy: StrategyResponse | null;
  /** Structured advice breakdown (null on validation errors). */
  structured_advice: StructuredAdviceResponse | null;
}

/** GET /api/health — response body. */
export interface HealthResponse {
  /** Service health: "ok" | "degraded" | "error". */
  status: "ok" | "degraded" | "error";
  /** Whether the TexasSolver binary is reachable. */
  solver_available: boolean;
  /** API version string. */
  version: string;
}

/** Standard error envelope for all 4xx/5xx responses. */
export interface ErrorResponse {
  /** Human-readable error message. */
  detail: string;
  /** Machine-readable error code. */
  error_code: string;
}

// ══════════════════════════════════════════════
// Zod schemas — runtime validation
// ══════════════════════════════════════════════

export const TopPlayResponseSchema = z.object({
  action: z.string(),
  frequency: z.number().min(0).max(1),
  ev_signal: z.enum(["positive", "negative", "neutral"]),
  explanation: z.string(),
});

export const ScenarioResponseSchema = z.object({
  hero_hand: z.string(),
  hero_position: z.string(),
  board: z.string(),
  pot_size_bb: z.number(),
  effective_stack_bb: z.number(),
  current_street: z.string(),
  hero_is_ip: z.boolean(),
  num_players_preflop: z.number().int(),
  game_type: z.string(),
  stack_depth_bb: z.number(),
  oop_range: z.string(),
  ip_range: z.string(),
});

export const StrategyResponseSchema = z.object({
  hand: z.string(),
  actions: z.record(z.string(), z.number()),
  best_action: z.string(),
  best_action_freq: z.number().min(0).max(1),
  range_summary: z.record(z.string(), z.number()),
  source: z.enum(["solver", "gemini", "gpt_fallback", "validation_error"]),
});

export const StructuredAdviceResponseSchema = z.object({
  top_plays: z.array(TopPlayResponseSchema),
  street_reviews: z.record(z.string(), z.string()),
  future_streets: z.string(),
  table_rule: z.string(),
  raw_advice: z.string(),
});

export const AnalyzeResponseSchema = z.object({
  advice: z.string(),
  source: z.enum(["solver", "gemini", "gpt_fallback", "validation_error"]),
  confidence: z.string(),
  mode: z.enum(["fast", "default", "pro"]),
  cached: z.boolean(),
  solve_time: z.number(),
  parse_time: z.number(),
  output_level: z.enum(["beginner", "advanced"]),
  sanity_note: z.string(),
  scenario: ScenarioResponseSchema.nullable(),
  strategy: StrategyResponseSchema.nullable(),
  structured_advice: StructuredAdviceResponseSchema.nullable(),
});

export const HealthResponseSchema = z.object({
  status: z.enum(["ok", "degraded", "error"]),
  solver_available: z.boolean(),
  version: z.string(),
});

export const ErrorResponseSchema = z.object({
  detail: z.string(),
  error_code: z.string(),
});

// ──────────────────────────────────────────────
// Type-safe parse helpers
// ──────────────────────────────────────────────

/**
 * Parse and validate an AnalyzeResponse from raw JSON.
 * Throws ZodError if the shape doesn't match.
 */
export function parseAnalyzeResponse(data: unknown): AnalyzeResponse {
  return AnalyzeResponseSchema.parse(data) as AnalyzeResponse;
}

/**
 * Parse and validate a HealthResponse from raw JSON.
 */
export function parseHealthResponse(data: unknown): HealthResponse {
  return HealthResponseSchema.parse(data) as HealthResponse;
}

/**
 * Parse and validate an ErrorResponse from raw JSON.
 */
export function parseErrorResponse(data: unknown): ErrorResponse {
  return ErrorResponseSchema.parse(data) as ErrorResponse;
}

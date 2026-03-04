/**
 * NeuralGTO shared TypeScript types.
 * Mirrors backend Pydantic schemas (app/models/schemas.py).
 */

/** Poker action in a hand history */
export interface ActionEntry {
  player: string
  action: string
  amount?: number
}

/** Parsed scenario from NL input (mirrors backend ScenarioResponse) */
export interface ScenarioData {
  hero_hand: string
  hero_position: string
  hero_is_ip: boolean
  board: string
  current_street: 'preflop' | 'flop' | 'turn' | 'river' | string
  pot_size_bb: number
  effective_stack_bb: number
  num_players_preflop: number
  game_type: string
  stack_depth_bb: number
  oop_range: string
  ip_range: string
}

/** Strategy source */
export type StrategySource = 'solver' | 'gemini' | 'gpt_fallback' | 'validation_error'

/** Strategy result from solver or LLM (mirrors backend StrategyResponse) */
export interface StrategyResult {
  hand: string
  source: StrategySource
  best_action: string
  best_action_freq: number
  actions: Record<string, number>
  range_summary: Record<string, number>
}

/** EV direction for a play */
export type EvSignal = 'positive' | 'negative' | 'neutral'

/** A single recommended play (mirrors backend TopPlayResponse) */
export interface TopPlay {
  action: string
  frequency: number
  ev_signal: EvSignal
  explanation: string
}

/** Structured advice breakdown (mirrors backend StructuredAdviceResponse) */
export interface StructuredAdvice {
  top_plays: TopPlay[]
  street_reviews: Record<string, string>
  future_streets: string
  table_rule: string
  raw_advice: string
}

/** Analysis mode */
export type AnalysisMode = 'fast' | 'default' | 'pro'

/** Output verbosity level */
export type OutputLevel = 'beginner' | 'advanced'

/** POST /api/analyze request body */
export interface AnalyzeRequest {
  query?: string
  hero_hand?: string
  hero_position?: string
  board?: string
  pot_size_bb?: number
  effective_stack_bb?: number
  villain_position?: string
  mode?: AnalysisMode
  opponent_notes?: string
  output_level?: OutputLevel
}

/** POST /api/reanalyze-street request body */
export interface ReanalyzeStreetRequest {
  hero_hand: string
  hero_position: string
  current_board: string
  pot_size_bb: number
  effective_stack_bb: number
  villain_position?: string
  new_board_cards: string
  mode?: AnalysisMode
  opponent_notes?: string
  output_level?: OutputLevel
}

/** POST /api/analyze response body (mirrors backend AnalyzeResponse) */
export interface AnalyzeResponse {
  advice: string
  source: StrategySource
  confidence: string
  mode: AnalysisMode
  cached: boolean
  solve_time: number
  parse_time: number
  output_level: OutputLevel
  sanity_note: string
  scenario: ScenarioData | null
  strategy: StrategyResult | null
  structured_advice: StructuredAdvice | null
}

/** API error envelope */
export interface ApiError {
  detail: string
  error_code: string
}

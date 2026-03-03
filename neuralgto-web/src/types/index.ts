/**
 * NeuralGTO shared TypeScript types.
 * Mirror key backend types here for frontend use.
 */

/** Poker action in a hand history */
export interface ActionEntry {
  player: string
  action: string
  amount?: number
}

/** Parsed scenario from NL input (mirrors backend ScenarioData) */
export interface ScenarioData {
  hero_hand: string
  hero_position: string
  hero_is_ip: boolean
  board: string
  current_street: 'preflop' | 'flop' | 'turn' | 'river'
  pot_size_bb: number
  effective_stack_bb: number
  villain_range: string
  hero_range: string
  actions_history: ActionEntry[]
}

/** Strategy result from solver or LLM (mirrors backend StrategyResult) */
export interface StrategyResult {
  hand: string
  source: 'solver' | 'gemini'
  best_action: string
  best_action_freq: number
  actions: Record<string, number>
  range_summary: Record<string, number>
}

/** Analysis response from /api/analyze */
export interface AnalysisResponse {
  advice: string
  strategy: StrategyResult | null
  scenario: ScenarioData | null
  mode: string
  cached: boolean
}

/** Analysis mode */
export type AnalysisMode = 'fast' | 'default' | 'pro'

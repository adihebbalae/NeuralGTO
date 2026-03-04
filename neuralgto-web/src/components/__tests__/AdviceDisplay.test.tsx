import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import AdviceDisplay from '../AdviceDisplay'
import type { AnalyzeResponse, StructuredAdvice } from '../../types'

const fullAdvice: StructuredAdvice = {
  top_plays: [
    { action: 'Raise', frequency: 0.78, ev_signal: 'positive', explanation: 'Value raise.' },
    { action: 'Call', frequency: 0.15, ev_signal: 'neutral', explanation: 'Flat sometimes.' },
    { action: 'Fold', frequency: 0.07, ev_signal: 'negative', explanation: 'Rarely fold.' },
  ],
  street_reviews: {
    preflop: 'Standard 3-bet spot with QQ.',
    flop: 'Continue on dry boards.',
  },
  future_streets: 'Barrel most turns.',
  table_rule: 'Raise ~78% of the time with QQ on the button.',
  raw_advice: 'You should raise with QQ here.',
}

const makeResult = (overrides: Partial<AnalyzeResponse> = {}): AnalyzeResponse => ({
  advice: 'You should raise with QQ here.',
  source: 'solver',
  confidence: '0.95',
  mode: 'default',
  cached: false,
  solve_time: 2.1,
  parse_time: 0.3,
  output_level: 'beginner',
  sanity_note: '',
  scenario: {
    hero_hand: 'QhQd',
    hero_position: 'BTN',
    hero_is_ip: true,
    board: '',
    current_street: 'preflop',
    pot_size_bb: 6.5,
    effective_stack_bb: 100,
    num_players_preflop: 2,
    game_type: 'cash',
    stack_depth_bb: 100,
    oop_range: '',
    ip_range: '',
  },
  strategy: {
    hand: 'QhQd',
    source: 'solver',
    best_action: 'Raise',
    best_action_freq: 0.78,
    actions: { Raise: 0.78, Call: 0.15, Fold: 0.07 },
    range_summary: {},
  },
  structured_advice: fullAdvice,
  ...overrides,
})

describe('AdviceDisplay', () => {
  it('renders top plays from structured advice', () => {
    render(<AdviceDisplay result={makeResult()} />)
    expect(screen.getByText('Raise')).toBeInTheDocument()
    expect(screen.getByText('Call')).toBeInTheDocument()
    expect(screen.getByText('Fold')).toBeInTheDocument()
  })

  it('renders frequency badges', () => {
    render(<AdviceDisplay result={makeResult()} />)
    // Frequency is rendered as "{pct}%" — two JSX children
    expect(screen.getByText(/78\.0\s*%/)).toBeInTheDocument()
    expect(screen.getByText(/15\.0\s*%/)).toBeInTheDocument()
    expect(screen.getByText(/7\.0\s*%/)).toBeInTheDocument()
  })

  it('renders the table rule', () => {
    render(<AdviceDisplay result={makeResult()} />)
    expect(screen.getByText(/raise.*78%/i)).toBeInTheDocument()
  })

  it('renders street reviews', () => {
    render(<AdviceDisplay result={makeResult()} />)
    // "preflop" appears in both street_reviews and scenario grid
    expect(screen.getAllByText('preflop').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Standard 3-bet spot with QQ.')).toBeInTheDocument()
  })

  it('renders source badge — solver shows verified text', () => {
    render(<AdviceDisplay result={makeResult()} />)
    expect(screen.getByText(/solver-verified/i)).toBeInTheDocument()
  })

  it('renders mode value', () => {
    render(<AdviceDisplay result={makeResult()} />)
    // Mode is rendered lowercase inside a span
    expect(screen.getByText('default')).toBeInTheDocument()
  })

  it('renders confidence value', () => {
    render(<AdviceDisplay result={makeResult()} />)
    // Confidence is rendered as the raw string from the API
    expect(screen.getByText('0.95')).toBeInTheDocument()
  })

  it('renders solve time', () => {
    render(<AdviceDisplay result={makeResult()} />)
    // toFixed(1) → "2.1", rendered as "{val}s" — two JSX children
    expect(screen.getByText(/2\.1\s*s/)).toBeInTheDocument()
  })

  it('renders scenario details when present', () => {
    render(<AdviceDisplay result={makeResult()} />)
    expect(screen.getByText('QhQd')).toBeInTheDocument()
    expect(screen.getByText('BTN')).toBeInTheDocument()
  })

  it('shows raw advice when no structured advice', () => {
    render(<AdviceDisplay result={makeResult({ structured_advice: null })} />)
    expect(screen.getByText('You should raise with QQ here.')).toBeInTheDocument()
  })

  it('shows sanity note when present', () => {
    render(<AdviceDisplay result={makeResult({ sanity_note: 'Check this spot again.' })} />)
    expect(screen.getByText('Check this spot again.')).toBeInTheDocument()
  })

  it('shows cached badge when result is cached', () => {
    render(<AdviceDisplay result={makeResult({ cached: true })} />)
    expect(screen.getByText('CACHED')).toBeInTheDocument()
  })

  it('shows LLM approximation for gemini source', () => {
    render(<AdviceDisplay result={makeResult({ source: 'gemini' })} />)
    expect(screen.getByText(/llm approximation/i)).toBeInTheDocument()
  })

  it('renders future streets when present', () => {
    render(<AdviceDisplay result={makeResult()} />)
    expect(screen.getByText('Barrel most turns.')).toBeInTheDocument()
  })

  it('renders parsed scenario grid fields', () => {
    render(<AdviceDisplay result={makeResult()} />)
    // Pot and stack — split JSX children
    expect(screen.getByText(/6\.5\s*BB/)).toBeInTheDocument()
    expect(screen.getByText(/100\s*BB/)).toBeInTheDocument()
    // Street appears in both street_reviews and scenario
    expect(screen.getAllByText('preflop').length).toBeGreaterThanOrEqual(2)
  })
})

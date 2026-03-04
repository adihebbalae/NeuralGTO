import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import Home from './Home'
import type { AnalyzeResponse } from '../types'

/** Minimal valid AnalyzeResponse fixture */
const MOCK_RESULT: AnalyzeResponse = {
  advice: 'You should raise with QQ here. This is a profitable spot.',
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
  structured_advice: {
    top_plays: [
      { action: 'Raise', frequency: 0.78, ev_signal: 'positive', explanation: 'Strong value raise' },
      { action: 'Call', frequency: 0.15, ev_signal: 'neutral', explanation: 'Flat sometimes' },
      { action: 'Fold', frequency: 0.07, ev_signal: 'negative', explanation: 'Rarely fold' },
    ],
    street_reviews: { preflop: 'Standard 3-bet spot with QQ.' },
    future_streets: 'Continue on most flops.',
    table_rule: 'Raise ~78% of the time with QQ on the button.',
    raw_advice: 'You should raise with QQ here.',
  },
}

describe('Home', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders the brand heading', () => {
    render(<Home />)
    expect(screen.getByText('GTO')).toBeInTheDocument()
  })

  it('renders the Surprise me button', () => {
    render(<Home />)
    expect(screen.getByRole('button', { name: /random example/i })).toBeInTheDocument()
  })

  it('fills the textarea with an example when Surprise me is clicked', () => {
    render(<Home />)
    const btn = screen.getByRole('button', { name: /random example/i })
    fireEvent.click(btn)
    const textarea = screen.getByLabelText('Hand description input') as HTMLTextAreaElement
    expect(textarea.value.length).toBeGreaterThan(10)
  })

  it('does not repeat the same example on consecutive clicks', () => {
    render(<Home />)
    const btn = screen.getByRole('button', { name: /random example/i })
    fireEvent.click(btn)
    const textarea = screen.getByLabelText('Hand description input') as HTMLTextAreaElement
    const first = textarea.value
    const seen = new Set([first])
    for (let i = 0; i < 20; i++) {
      fireEvent.click(btn)
      seen.add(textarea.value)
    }
    expect(seen.size).toBeGreaterThan(1)
  })

  it('disables Analyze when textarea is empty', () => {
    render(<Home />)
    const analyze = screen.getByRole('button', { name: /analyze hand/i })
    expect(analyze).toBeDisabled()
  })

  it('enables Analyze after typing', () => {
    render(<Home />)
    const textarea = screen.getByLabelText('Hand description input')
    fireEvent.change(textarea, { target: { value: 'I have AA on the BTN' } })
    const analyze = screen.getByRole('button', { name: /analyze hand/i })
    expect(analyze).not.toBeDisabled()
  })

  it('renders mode selector buttons', () => {
    render(<Home />)
    expect(screen.getByRole('button', { name: /mode: fast/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /mode: default/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /mode: pro/i })).toBeInTheDocument()
  })

  it('calls analyzeHand and displays results on submit', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.resolve(MOCK_RESULT),
      }),
    )

    render(<Home />)
    const textarea = screen.getByLabelText('Hand description input')
    fireEvent.change(textarea, { target: { value: 'I have QQ on the button' } })
    const analyze = screen.getByRole('button', { name: /analyze hand/i })
    fireEvent.click(analyze)

    // Loading state should appear
    expect(await screen.findByText(/analyzing/i)).toBeInTheDocument()

    // Wait for result to render
    await waitFor(() => {
      expect(screen.getByText('Raise')).toBeInTheDocument()
    })

    // Top plays should render — frequency uses split JSX children
    expect(screen.getByText(/78\.0\s*%/)).toBeInTheDocument()

    // Table rule should render
    expect(screen.getByText(/raise.*78%/i)).toBeInTheDocument()
  })

  it('shows error on API failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: () => Promise.resolve({ detail: 'Solver timed out', error_code: 'SOLVER_TIMEOUT' }),
      }),
    )

    render(<Home />)
    const textarea = screen.getByLabelText('Hand description input')
    fireEvent.change(textarea, { target: { value: 'I have QQ on the button' } })
    const analyze = screen.getByRole('button', { name: /analyze hand/i })
    fireEvent.click(analyze)

    await waitFor(() => {
      expect(screen.getByText('Analysis failed')).toBeInTheDocument()
    })
    expect(screen.getByText('Solver timed out')).toBeInTheDocument()
  })

  it('shows error on network failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new Error('Failed to fetch')),
    )

    render(<Home />)
    const textarea = screen.getByLabelText('Hand description input')
    fireEvent.change(textarea, { target: { value: 'I have QQ on the button' } })
    const analyze = screen.getByRole('button', { name: /analyze hand/i })
    fireEvent.click(analyze)

    await waitFor(() => {
      expect(screen.getByText('Analysis failed')).toBeInTheDocument()
    })
    expect(screen.getByText('Failed to fetch')).toBeInTheDocument()
  })

  it('demo table is shown initially and hidden after result', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.resolve(MOCK_RESULT),
      }),
    )

    render(<Home />)

    // Demo visible before analysis
    expect(screen.getByText(/board visualization.*demo/i)).toBeInTheDocument()

    const textarea = screen.getByLabelText('Hand description input')
    fireEvent.change(textarea, { target: { value: 'I have QQ on the button' } })
    fireEvent.click(screen.getByRole('button', { name: /analyze hand/i }))

    // After result loads, demo should vanish
    await waitFor(() => {
      expect(screen.queryByText(/board visualization.*demo/i)).not.toBeInTheDocument()
    })
  })
})

import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import TopPlayCard from '../TopPlayCard'
import type { TopPlay } from '../../types'

const positivePlay: TopPlay = {
  action: 'Raise',
  frequency: 0.78,
  ev_signal: 'positive',
  explanation: 'Strong value raise with overpair.',
}

const negativePlay: TopPlay = {
  action: 'Fold',
  frequency: 0.07,
  ev_signal: 'negative',
  explanation: 'Rarely fold here.',
}

const neutralPlay: TopPlay = {
  action: 'Call',
  frequency: 0.15,
  ev_signal: 'neutral',
  explanation: 'Flat-call occasionally.',
}

describe('TopPlayCard', () => {
  it('renders the action name and frequency', () => {
    render(<TopPlayCard play={positivePlay} rank={0} />)
    expect(screen.getByText('Raise')).toBeInTheDocument()
    // freq-badge renders "{pct}%" as two JSX children — use regex
    expect(screen.getByText(/78\.0\s*%/)).toBeInTheDocument()
  })

  it('renders the rank number (rank is 0-indexed, display is 1-indexed)', () => {
    render(<TopPlayCard play={positivePlay} rank={0} />)
    // Component renders "#{rank + 1}" as two JSX children
    expect(screen.getByText(/^#\s*1$/)).toBeInTheDocument()
  })

  it('renders the explanation text', () => {
    render(<TopPlayCard play={positivePlay} rank={0} />)
    expect(screen.getByText('Strong value raise with overpair.')).toBeInTheDocument()
  })

  it('renders correct rank for different positions', () => {
    render(<TopPlayCard play={negativePlay} rank={2} />)
    // rank=2 → display #3
    expect(screen.getByText(/^#\s*3$/)).toBeInTheDocument()
    expect(screen.getByText('Fold')).toBeInTheDocument()
    expect(screen.getByText(/7\.0\s*%/)).toBeInTheDocument()
  })

  it('renders neutral play', () => {
    render(<TopPlayCard play={neutralPlay} rank={1} />)
    expect(screen.getByText('Call')).toBeInTheDocument()
    expect(screen.getByText(/15\.0\s*%/)).toBeInTheDocument()
    expect(screen.getByText('Flat-call occasionally.')).toBeInTheDocument()
  })

  it('renders 100% frequency correctly', () => {
    const fullPlay: TopPlay = {
      action: 'All-in',
      frequency: 1.0,
      ev_signal: 'positive',
      explanation: 'Jam it.',
    }
    render(<TopPlayCard play={fullPlay} rank={0} />)
    expect(screen.getByText(/100\.0\s*%/)).toBeInTheDocument()
  })

  it('renders 0% frequency correctly', () => {
    const zeroPlay: TopPlay = {
      action: 'Check',
      frequency: 0,
      ev_signal: 'neutral',
      explanation: 'Never check.',
    }
    render(<TopPlayCard play={zeroPlay} rank={3} />)
    expect(screen.getByText(/0\.0\s*%/)).toBeInTheDocument()
  })

  it('has a progressbar with correct aria attributes', () => {
    render(<TopPlayCard play={positivePlay} rank={0} />)
    const bar = screen.getByRole('progressbar', { name: 'Raise frequency' })
    expect(bar).toBeInTheDocument()
    expect(bar.getAttribute('aria-valuenow')).toBe('78')
  })
})

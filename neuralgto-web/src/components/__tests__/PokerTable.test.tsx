import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import PokerTable from '../PokerTable'
import type { Position } from '../PokerTable'

const defaults = {
  heroPosition: 'BTN' as Position,
  villainPosition: 'SB' as Position,
  potSize: 6.5,
  heroStack: 100,
}

describe('PokerTable', () => {
  it('renders without crashing (BTN vs SB)', () => {
    render(<PokerTable {...defaults} />)
    expect(screen.getByRole('img', { name: /poker table/i })).toBeInTheDocument()
  })

  it('highlights hero position in green (emerald-400)', () => {
    const { container } = render(<PokerTable {...defaults} />)
    const heroSeat = container.querySelector('[data-testid="seat-BTN"]')
    expect(heroSeat).toBeInTheDocument()
    const rect = heroSeat!.querySelector('rect')
    expect(rect).toHaveAttribute('stroke', '#34d399')
  })

  it('highlights villain position in red (rose-400)', () => {
    const { container } = render(<PokerTable {...defaults} />)
    const villainSeat = container.querySelector('[data-testid="seat-SB"]')
    expect(villainSeat).toBeInTheDocument()
    const rect = villainSeat!.querySelector('rect')
    expect(rect).toHaveAttribute('stroke', '#fb7185')
  })

  it('renders 5 community board cells', () => {
    const { container } = render(<PokerTable {...defaults} />)
    const boardCards = container.querySelectorAll('[data-testid^="board-card-"]')
    expect(boardCards).toHaveLength(5)
  })

  it('displays correct pot and stack values', () => {
    render(<PokerTable {...defaults} />)
    expect(screen.getByTestId('pot-display')).toHaveTextContent('6.5 BB')
    expect(screen.getByTestId('stack-display')).toHaveTextContent('100 BB')
  })

  it('renders filled board cards when board is provided', () => {
    render(<PokerTable {...defaults} board="Ts9d4h" />)
    expect(screen.getByText('T')).toBeInTheDocument()
    expect(screen.getByText('9')).toBeInTheDocument()
    expect(screen.getByText('4')).toBeInTheDocument()
  })

  it('renders hero hole cards when provided', () => {
    render(<PokerTable {...defaults} heroHand="AsKh" />)
    expect(screen.getByText('A')).toBeInTheDocument()
    expect(screen.getByText('K')).toBeInTheDocument()
  })
})

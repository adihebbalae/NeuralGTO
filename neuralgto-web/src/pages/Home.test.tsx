import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import Home from './Home'

describe('Home', () => {
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
    // click many times — at least one should differ
    const seen = new Set([first])
    for (let i = 0; i < 20; i++) {
      fireEvent.click(btn)
      seen.add(textarea.value)
    }
    expect(seen.size).toBeGreaterThan(1)
  })

  it('disables Analyze when textarea is empty', () => {
    render(<Home />)
    const analyze = screen.getByRole('button', { name: /analyze/i })
    expect(analyze).toBeDisabled()
  })

  it('enables Analyze after typing', () => {
    render(<Home />)
    const textarea = screen.getByLabelText('Hand description input')
    fireEvent.change(textarea, { target: { value: 'I have AA on the BTN' } })
    const analyze = screen.getByRole('button', { name: /analyze/i })
    expect(analyze).not.toBeDisabled()
  })
})

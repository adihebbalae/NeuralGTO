import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import Layout from './Layout'

describe('Layout', () => {
  it('renders the NeuralGTO header brand', () => {
    render(<Layout><p>child</p></Layout>)
    expect(screen.getByText('NeuralGTO')).toBeInTheDocument()
  })

  it('renders children in the main area', () => {
    render(<Layout><p>test content</p></Layout>)
    expect(screen.getByText('test content')).toBeInTheDocument()
  })

  it('renders navigation links', () => {
    render(<Layout><p>x</p></Layout>)
    expect(screen.getByLabelText('Analyze a hand')).toBeInTheDocument()
    expect(screen.getByLabelText('Hand history')).toBeInTheDocument()
  })

  it('renders the footer', () => {
    render(<Layout><p>x</p></Layout>)
    expect(screen.getByText(/Neuro-symbolic GTO/i)).toBeInTheDocument()
  })
})

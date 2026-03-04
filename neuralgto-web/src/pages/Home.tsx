'use client'

import { useState } from 'react'
import type { AnalyzeResponse, AnalysisMode } from '../types'
import { analyzeHand, reanalyzeStreet } from '../api/client'
import PokerTable from '../components/PokerTable'
import AdviceDisplay from '../components/AdviceDisplay'
import ErrorBoundary from '../components/ErrorBoundary'
import CardPicker from '../components/CardPicker'
import type { Position } from '../components/PokerTable'

const EXAMPLES = [
  "I have QQ on the button, 100bb deep. Villain opens 2.5x from CO. What's my move?",
  "I'm on the SB with AcKc, 50bb effective. BB limps. I check. Flop is 2h7d9s, 3bb pot. They bet 1bb. Call or fold?",
  "Button, 75bb. I raise to 2.5x with AsQs. Big blind calls 50bb. Flop: Kh 9h 6d. They check, I bet 3bb. They call. Turn: 4c. They check again.",
  "Small blind with 8h8d, 80bb. Hero in HJ raised to 2.5x, I 3-bet to 8bb, they call. 16bb pot, flop Ac Kd 8s. I bet 6bb, they call.",
]

const MODE_OPTIONS: { value: AnalysisMode; label: string; description: string }[] = [
  { value: 'fast', label: 'Fast', description: 'LLM-only — instant' },
  { value: 'default', label: 'Default', description: 'Solver — 2% accuracy' },
  { value: 'pro', label: 'Pro', description: 'Solver — 0.3% accuracy' },
]

/** Home page — hand analyzer with PokerTable and advice display. */
export default function Home() {
  const [input, setInput] = useState('')
  const [mode, setMode] = useState<AnalysisMode>('default')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<AnalyzeResponse | null>(null)
  const [showCardPicker, setShowCardPicker] = useState(false)

  const handleSurprise = () => {
    const example = EXAMPLES[Math.floor(Math.random() * EXAMPLES.length)]
    setInput(example)
  }

  const handleAnalyze = async () => {
    const query = input.trim()
    if (!query) return

    setLoading(true)
    setError(null)
    setResult(null)
    setShowCardPicker(false)

    try {
      const response = await analyzeHand({ query, mode })
      setResult(response)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'An unexpected error occurred.'
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  const handleCardsSelected = async (cards: string[]) => {
    if (!result?.scenario) return

    const newBoardCards = cards.join(',')
    setLoading(true)
    setError(null)
    setShowCardPicker(false)

    try {
      const response = await reanalyzeStreet({
        hero_hand: result.scenario.hero_hand,
        hero_position: result.scenario.hero_position,
        current_board: result.scenario.board,
        pot_size_bb: result.scenario.pot_size_bb,
        effective_stack_bb: result.scenario.effective_stack_bb,
        villain_position: '', // Could extract from scenario if available
        new_board_cards: newBoardCards,
        mode,
      })
      setResult(response)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Reanalysis failed.'
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  const canAddCards = () => {
    if (!result?.scenario?.board) return false
    const boardCards = result.scenario.board.split(',').filter(c => c.trim())
    return boardCards.length < 5 // Can add cards if board has < 5 cards
  }

  const getMaxNewCards = () => {
    if (!result?.scenario?.board) return 0
    const boardCards = result.scenario.board.split(',').filter(c => c.trim())
    
    if (boardCards.length === 0) return 3 // Preflop → flop (3 cards)
    if (boardCards.length === 3) return 1 // Flop → turn (1 card)
    if (boardCards.length === 4) return 1 // Turn → river (1 card)
    return 0 // River (no more cards)
  }

  const getNextStreet = () => {
    if (!result?.scenario?.board) return 'flop'
    const boardCards = result.scenario.board.split(',').filter(c => c.trim())
    
    if (boardCards.length === 0) return 'flop'
    if (boardCards.length === 3) return 'turn'
    if (boardCards.length === 4) return 'river'
    return ''
  }

  // Extract table props from the result scenario
  const heroPos = (result?.scenario?.hero_position || 'BTN') as Position
  const board = result?.scenario?.board?.replace(/,/g, '') || ''
  const heroHand = result?.scenario?.hero_hand || ''
  const potSize = result?.scenario?.pot_size_bb || 0
  const heroStack = result?.scenario?.effective_stack_bb || 100

  return (
    <div
      className="animate-fade-in flex flex-col items-center justify-center gap-8 py-16"
      style={{ animationDuration: '600ms' }}
    >
      <h1 className="font-mono text-4xl font-bold tracking-tight text-primary">
        Neural<span className="text-signal-positive">GTO</span>
      </h1>
      <p className="max-w-md text-center text-secondary">
        Describe a poker hand in plain English. Get GTO strategy with an
        explanation of <em>why</em> — not just what.
      </p>

      {/* Input card with Surprise me button + mode selector */}
      <div className="card w-full max-w-xl">
        <div className="mb-2 flex items-center justify-between">
          <label htmlFor="hand-input" className="label">
            Describe your hand
          </label>
          <button
            type="button"
            onClick={handleSurprise}
            className="group flex items-center gap-1.5 rounded-md border border-border px-3 py-1 font-sans text-xs font-medium text-secondary transition-colors hover:border-signal-neutral/40 hover:text-signal-neutral"
            aria-label="Fill with a random example hand"
          >
            <span
              aria-hidden="true"
              className="inline-block transition-transform group-hover:rotate-180 group-hover:scale-110"
            >
              🎲
            </span>
            Surprise me
          </button>
        </div>
        <textarea
          id="hand-input"
          rows={3}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="I have QQ on the button, 100bb deep. Villain opens 2.5x from CO..."
          className="w-full resize-none rounded-md border border-border bg-base px-4 py-3 font-sans text-sm text-primary placeholder:text-secondary/40 focus:outline-none focus:ring-1 focus:ring-signal-positive/50"
          aria-label="Hand description input"
          disabled={loading}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && input.trim()) {
              e.preventDefault()
              handleAnalyze()
            }
          }}
        />

        {/* Mode selector + Analyze button */}
        <div className="mt-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            {MODE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setMode(opt.value)}
                disabled={loading}
                className={`rounded-md border px-3 py-1.5 font-sans text-xs font-medium transition-colors ${
                  mode === opt.value
                    ? 'border-signal-positive/50 bg-signal-positive/10 text-signal-positive'
                    : 'border-border text-secondary hover:border-border hover:text-primary'
                }`}
                title={opt.description}
                aria-label={`Mode: ${opt.label} — ${opt.description}`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={handleAnalyze}
            disabled={!input.trim() || loading}
            className="h-9 rounded-md bg-emerald-500 px-4 font-sans text-sm font-medium text-slate-950 transition-colors hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="Analyze hand"
          >
            {loading ? 'Analyzing...' : 'Analyze'}
          </button>
        </div>
      </div>

      {/* Loading spinner */}
      {loading && (
        <div className="flex items-center gap-3" role="status" aria-label="Analyzing hand">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-signal-positive border-t-transparent" />
          <span className="font-sans text-sm text-secondary">
            Running GTO analysis…
          </span>
        </div>
      )}

      {/* Error display */}
      {error && (
        <div className="card w-full max-w-xl border-signal-negative/30" role="alert">
          <p className="font-sans text-sm font-bold text-signal-negative">Analysis failed</p>
          <p className="mt-1 text-sm text-secondary">{error}</p>
          <button
            type="button"
            onClick={() => setError(null)}
            className="mt-3 h-9 rounded-md border border-border px-4 font-sans text-xs text-secondary transition-colors hover:text-primary"
            aria-label="Dismiss error"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* PokerTable (show when we have a result with scenario) */}
      {result?.scenario && (
        <div className="card w-full max-w-2xl">
          <div className="mb-4 flex items-center justify-between">
            <p className="label">Board</p>
            {canAddCards() && !showCardPicker && (
              <button
                type="button"
                onClick={() => setShowCardPicker(true)}
                disabled={loading}
                className="flex items-center gap-2 rounded-md border border-signal-neutral/40 bg-signal-neutral/10 px-3 py-1.5 font-sans text-xs font-medium text-signal-neutral transition-colors hover:bg-signal-neutral/20 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <span>+</span>
                Add {getNextStreet()} card{getMaxNewCards() > 1 ? 's' : ''}
              </button>
            )}
          </div>
          <div className="flex justify-center">
            <PokerTable
              heroPosition={heroPos}
              villainPosition="BB"
              board={board}
              heroHand={heroHand}
              potSize={potSize}
              heroStack={heroStack}
            />
          </div>
        </div>
      )}

      {/* Card Picker (interactive turn/river selection) */}
      {result?.scenario && showCardPicker && !loading && (
        <div className="w-full max-w-2xl">
          <CardPicker
            currentBoard={result.scenario.board}
            heroHand={result.scenario.hero_hand}
            maxCards={getMaxNewCards()}
            onCardsSelected={handleCardsSelected}
            onCancel={() => setShowCardPicker(false)}
          />
        </div>
      )}

      {/* Advice display */}
      {result && (
        <ErrorBoundary>
          <div className="w-full max-w-2xl">
            <AdviceDisplay result={result} />
          </div>
        </ErrorBoundary>
      )}

      {/* Demo placeholder (only show when no result) */}
      {!result && !loading && !error && (
        <>
          <div className="card w-full max-w-2xl">
            <p className="label mb-4">Board Visualization (Demo)</p>
            <div className="flex justify-center">
              <PokerTable
                heroPosition="BTN"
                villainPosition="SB"
                board="Ts9d4h"
                heroHand="AsKh"
                potSize={6.5}
                heroStack={100}
              />
            </div>
            <p className="mt-4 text-center text-xs text-secondary">
              BTN (hero) vs SB (villain) — board runs out Ts9d4h
            </p>
          </div>

          <div className="card w-full max-w-xl opacity-50">
            <p className="label mb-2">Strategy</p>
            <div className="flex items-baseline gap-4">
              <span className="data-value text-2xl text-signal-positive">
                Raise
              </span>
              <span className="freq-badge">78.3%</span>
            </div>
            <p className="mt-2 text-sm text-secondary">
              Solver result will appear here after analysis.
            </p>
          </div>
        </>
      )}
    </div>
  )
}

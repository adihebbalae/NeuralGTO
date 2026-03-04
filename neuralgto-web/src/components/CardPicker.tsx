/**
 * CardPicker — Interactive card selector for turn/river cards.
 * 
 * Displays remaining cards in the deck (excluding hero hand + board)
 * and allows user to select new cards to append to the board.
 */

import { useState, useMemo } from 'react'

const RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']
const SUITS = {
  h: { symbol: '♥', color: 'text-rose-400' },
  d: { symbol: '♦', color: 'text-rose-400' },
  c: { symbol: '♣', color: 'text-slate-100' },
  s: { symbol: '♠', color: 'text-slate-100' },
}

interface CardPickerProps {
  /** Current board cards (comma-separated, e.g. "Ah,Kd,Qs") */
  currentBoard: string
  /** Hero's hole cards (e.g. "AhKs") */
  heroHand: string
  /** Max number of cards to select (e.g., 1 for turn, 1 for river) */
  maxCards: number
  /** Callback when cards are selected */
  onCardsSelected: (cards: string[]) => void
  /** Callback when selection is cancelled */
  onCancel: () => void
}

/** Build set of cards already in use (hero hand + board) */
function getUsedCards(heroHand: string, currentBoard: string): Set<string> {
  const used = new Set<string>()
  
  // Parse hero hand (e.g., "AhKs" → ["Ah", "Ks"])
  if (heroHand.length >= 4) {
    const card1 = heroHand.slice(0, 2)
    const card2 = heroHand.slice(2, 4)
    used.add(card1.toUpperCase())
    used.add(card2.toUpperCase())
  }
  
  // Parse board (comma-separated or concatenated)
  const boardCards = currentBoard.includes(',')
    ? currentBoard.split(',').map(c => c.trim())
    : currentBoard.match(/.{1,2}/g) || []
  
  boardCards.forEach(card => {
    if (card) used.add(card.toUpperCase())
  })
  
  return used
}

export default function CardPicker({
  currentBoard,
  heroHand,
  maxCards,
  onCardsSelected,
  onCancel,
}: CardPickerProps) {
  const [selectedCards, setSelectedCards] = useState<string[]>([])
  
  const usedCards = useMemo(
    () => getUsedCards(heroHand, currentBoard),
    [heroHand, currentBoard]
  )
  
  const handleCardClick = (rank: string, suit: string) => {
    const card = `${rank}${suit}`
    const cardKey = card.toUpperCase()
    
    if (usedCards.has(cardKey)) return // Already in use
    
    if (selectedCards.includes(card)) {
      // Deselect
      setSelectedCards(prev => prev.filter(c => c !== card))
    } else if (selectedCards.length < maxCards) {
      // Select (if under limit)
      setSelectedCards(prev => [...prev, card])
    }
  }
  
  const handleConfirm = () => {
    if (selectedCards.length > 0) {
      onCardsSelected(selectedCards)
    }
  }
  
  const isCardUsed = (rank: string, suit: string) => {
    const cardKey = `${rank}${suit}`.toUpperCase()
    return usedCards.has(cardKey)
  }
  
  const isCardSelected = (rank: string, suit: string) => {
    const card = `${rank}${suit}`
    return selectedCards.includes(card)
  }
  
  return (
    <div className="card border-signal-neutral/20">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="label">Pick {maxCards === 1 ? 'a card' : `${maxCards} cards`}</p>
          {selectedCards.length > 0 && (
            <p className="mt-1 font-mono text-sm text-signal-neutral">
              Selected: {selectedCards.join(', ')}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-border px-3 py-1.5 font-sans text-xs text-secondary transition-colors hover:text-primary"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={selectedCards.length === 0}
            className="rounded-md bg-emerald-500 px-3 py-1.5 font-sans text-xs font-medium text-slate-950 transition-colors hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Confirm ({selectedCards.length}/{maxCards})
          </button>
        </div>
      </div>
      
      {/* Card grid organized by suit */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {Object.entries(SUITS).map(([suitChar, suitInfo]) => (
          <div key={suitChar} className="rounded-md border border-border bg-base p-3">
            <div className="mb-2 flex items-center gap-1.5">
              <span className={`text-xl ${suitInfo.color}`}>{suitInfo.symbol}</span>
              <span className="font-mono text-xs uppercase tracking-wide text-secondary">
                {suitChar === 'h' ? 'Hearts' : suitChar === 'd' ? 'Diamonds' : suitChar === 'c' ? 'Clubs' : 'Spades'}
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {RANKS.map(rank => {
                const used = isCardUsed(rank, suitChar)
                const selected = isCardSelected(rank, suitChar)
                
                return (
                  <button
                    key={`${rank}${suitChar}`}
                    type="button"
                    onClick={() => handleCardClick(rank, suitChar)}
                    disabled={used}
                    className={`
                      h-10 w-10 rounded border font-mono text-sm font-bold transition-all
                      ${used 
                        ? 'cursor-not-allowed border-border/30 bg-base text-secondary/30' 
                        : selected
                        ? 'border-signal-neutral bg-signal-neutral/20 text-signal-neutral'
                        : 'border-border hover:border-signal-neutral/40 hover:bg-raised'
                      }
                      ${suitInfo.color}
                    `}
                    aria-label={`${rank}${suitInfo.symbol} ${used ? '(in use)' : selected ? '(selected)' : ''}`}
                  >
                    {rank}
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

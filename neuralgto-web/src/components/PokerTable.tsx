import type { FC } from 'react'

/* ── Types ── */

/** Valid 6-max table positions */
export type Position = 'UTG' | 'HJ' | 'CO' | 'BTN' | 'SB' | 'BB'

export interface PokerTableProps {
  /** Hero's table position */
  heroPosition: Position
  /** Villain's table position */
  villainPosition: Position
  /** Community board cards, e.g. "Ts9d4h" */
  board?: string
  /** Hero's hole cards, e.g. "AsKh" */
  heroHand?: string
  /** Current pot size in big blinds */
  potSize: number
  /** Hero's remaining stack in big blinds */
  heroStack: number
}

/* ── SVG color constants (matching design tokens) ── */
const C = {
  raised: '#0f172a',
  overlay: '#1e293b',
  border: 'rgba(255,255,255,0.08)',
  textPrimary: '#f1f5f9',
  textSecondary: '#94a3b8',
  positive: '#34d399',
  negative: '#fb7185',
  neutral: '#fbbf24',
  felt: '#022c22',
  feltBorder: '#064e3b',
} as const

const SUIT_SYMBOL: Record<string, string> = { h: '♥', d: '♦', c: '♣', s: '♠' }
const SUIT_COLOR: Record<string, string> = {
  h: C.negative, d: C.negative, c: C.textPrimary, s: C.textPrimary,
}

/** Seat coordinates (viewBox 600×400) arranged around the table */
const SEAT_XY: Record<Position, [number, number]> = {
  BTN: [440, 330],
  SB:  [160, 330],
  BB:  [55,  200],
  UTG: [160, 70],
  HJ:  [440, 70],
  CO:  [545, 200],
}

const ALL_POSITIONS: Position[] = ['UTG', 'HJ', 'CO', 'BTN', 'SB', 'BB']

/* ── Helpers ── */

interface Card { rank: string; suit: string }

function parseCards(s: string): Card[] {
  const out: Card[] = []
  for (let i = 0; i + 1 < s.length; i += 2) out.push({ rank: s[i], suit: s[i + 1] })
  return out
}

/* ── Card slot (empty or filled) ── */
const CW = 34
const CH = 48

function CardSlot({ x, y, card, testId }: { x: number; y: number; card?: Card; testId?: string }) {
  if (!card) {
    return (
      <rect data-testid={testId} x={x} y={y} width={CW} height={CH} rx={4}
        fill={C.overlay} stroke={C.border} strokeWidth={1} strokeDasharray="4 2" />
    )
  }
  const sc = SUIT_COLOR[card.suit] ?? C.textPrimary
  return (
    <g data-testid={testId}>
      <rect x={x} y={y} width={CW} height={CH} rx={4}
        fill={C.raised} stroke={sc} strokeWidth={1} strokeOpacity={0.5} />
      <text x={x + CW / 2} y={y + 20} textAnchor="middle"
        fill={sc} fontSize={14} fontWeight={700} fontFamily="'IBM Plex Mono',monospace">
        {card.rank}
      </text>
      <text x={x + CW / 2} y={y + 38} textAnchor="middle"
        fill={sc} fontSize={14} fontFamily="'IBM Plex Mono',monospace">
        {SUIT_SYMBOL[card.suit] ?? '?'}
      </text>
    </g>
  )
}

/* ── Seat marker ── */
const SW = 52
const SH = 28

function Seat({ pos, x, y, role }: {
  pos: Position; x: number; y: number; role: 'hero' | 'villain' | 'empty'
}) {
  const stroke = role === 'hero' ? C.positive : role === 'villain' ? C.negative : C.border
  const sw = role === 'empty' ? 1 : 2
  return (
    <g data-testid={`seat-${pos}`}>
      <rect x={x - SW / 2} y={y - SH / 2} width={SW} height={SH} rx={6}
        fill={C.raised} stroke={stroke} strokeWidth={sw} />
      <text x={x} y={y + 4} textAnchor="middle"
        fill={role === 'empty' ? C.textSecondary : C.textPrimary}
        fontSize={11} fontWeight={role === 'empty' ? 200 : 700}
        fontFamily="'IBM Plex Sans',sans-serif">
        {pos}
      </text>
    </g>
  )
}

/* ── Main component ── */

const PokerTable: FC<PokerTableProps> = ({
  heroPosition, villainPosition, board, heroHand, potSize, heroStack,
}) => {
  const boardCards = board ? parseCards(board) : []
  const holeCards = heroHand ? parseCards(heroHand) : []

  /* Community cards: 5 slots centered at x=300, y=188 */
  const gap = 6
  const totalW = 5 * CW + 4 * gap
  const bx0 = 300 - totalW / 2
  const by = 188

  /* Hero hole cards: 80px from hero seat toward table center */
  const [hx, hy] = SEAT_XY[heroPosition]
  const dx = 300 - hx
  const dy = 200 - hy
  const dist = Math.sqrt(dx * dx + dy * dy) || 1
  const hcx = hx + (dx / dist) * 80
  const hcy = hy + (dy / dist) * 80
  const holeX0 = hcx - CW - 2
  const holeY = hcy - CH / 2

  return (
    <svg viewBox="0 0 600 400" className="w-full max-w-2xl"
      role="img" aria-label="Poker table visualization"
      preserveAspectRatio="xMidYMid meet">

      {/* Rail (outer ring) */}
      <ellipse cx={300} cy={200} rx={248} ry={150}
        fill="none" stroke={C.overlay} strokeWidth={8} />

      {/* Felt surface */}
      <ellipse cx={300} cy={200} rx={232} ry={138}
        fill={C.felt} stroke={C.feltBorder} strokeWidth={2.5} />

      {/* Pot display */}
      <text x={300} y={162} textAnchor="middle"
        fill={C.textSecondary} fontSize={10} fontWeight={200}
        fontFamily="'IBM Plex Sans',sans-serif">
        POT
      </text>
      <text x={300} y={178} textAnchor="middle" data-testid="pot-display"
        fill={C.neutral} fontSize={14} fontWeight={700}
        fontFamily="'IBM Plex Mono',monospace">
        {potSize} BB
      </text>

      {/* Community board cards (5 slots) */}
      {Array.from({ length: 5 }, (_, i) => (
        <CardSlot key={i} testId={`board-card-${i}`}
          x={bx0 + i * (CW + gap)} y={by} card={boardCards[i]} />
      ))}

      {/* Player seats */}
      {ALL_POSITIONS.map(pos => {
        const [sx, sy] = SEAT_XY[pos]
        const role = pos === heroPosition ? 'hero'
          : pos === villainPosition ? 'villain' : 'empty'
        return <Seat key={pos} pos={pos} x={sx} y={sy} role={role} />
      })}

      {/* Hero hole cards (2 slots) */}
      <CardSlot x={holeX0} y={holeY} card={holeCards[0]} testId="hero-card-0" />
      <CardSlot x={holeX0 + CW + 4} y={holeY} card={holeCards[1]} testId="hero-card-1" />

      {/* Hero stack label */}
      <text x={hx} y={hy > 200 ? hy + 26 : hy - 22} textAnchor="middle"
        fill={C.textSecondary} fontSize={9} fontWeight={200}
        fontFamily="'IBM Plex Sans',sans-serif">
        STACK
      </text>
      <text x={hx} y={hy > 200 ? hy + 38 : hy - 10} textAnchor="middle"
        data-testid="stack-display"
        fill={C.textPrimary} fontSize={12} fontWeight={700}
        fontFamily="'IBM Plex Mono',monospace">
        {heroStack} BB
      </text>
    </svg>
  )
}

export default PokerTable

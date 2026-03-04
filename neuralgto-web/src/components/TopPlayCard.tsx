import type { FC } from 'react'
import type { TopPlay } from '../types'

/* ── Signal color mapping ── */
const SIGNAL_CLASSES: Record<string, string> = {
  positive: 'text-signal-positive',
  negative: 'text-signal-negative',
  neutral: 'text-signal-neutral',
}

const SIGNAL_BG: Record<string, string> = {
  positive: 'bg-emerald-400/10',
  negative: 'bg-rose-400/10',
  neutral: 'bg-amber-400/10',
}

const SIGNAL_BORDER: Record<string, string> = {
  positive: 'border-emerald-400/20',
  negative: 'border-rose-400/20',
  neutral: 'border-amber-400/20',
}

interface TopPlayCardProps {
  play: TopPlay
  rank: number
}

/** Single recommended play card with frequency slider and explanation. */
const TopPlayCard: FC<TopPlayCardProps> = ({ play, rank }) => {
  const signal = play.ev_signal || 'neutral'
  const pct = (play.frequency * 100).toFixed(1)

  return (
    <div
      className={`card flex flex-col gap-3 border ${SIGNAL_BORDER[signal]}`}
      style={{ animationDelay: `${rank * 80}ms` }}
    >
      {/* Header: rank + action + frequency */}
      <div className="flex items-baseline justify-between gap-3">
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-xs font-extralight text-secondary">
            #{rank + 1}
          </span>
          <span className={`font-mono text-lg font-bold ${SIGNAL_CLASSES[signal]}`}>
            {play.action}
          </span>
        </div>
        <span className="freq-badge">{pct}%</span>
      </div>

      {/* Frequency bar */}
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-overlay">
        <div
          className={`h-full rounded-full transition-all duration-700 ease-out ${SIGNAL_BG[signal].replace('/10', '/40')}`}
          style={{ width: `${Math.min(play.frequency * 100, 100)}%` }}
          role="progressbar"
          aria-valuenow={play.frequency * 100}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`${play.action} frequency`}
        />
      </div>

      {/* Explanation */}
      {play.explanation && (
        <p className="text-sm font-extralight leading-relaxed text-secondary">
          {play.explanation}
        </p>
      )}
    </div>
  )
}

export default TopPlayCard

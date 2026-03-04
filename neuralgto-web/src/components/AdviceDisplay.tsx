import type { FC } from 'react'
import type { AnalyzeResponse } from '../types'
import TopPlayCard from './TopPlayCard'

interface AdviceDisplayProps {
  result: AnalyzeResponse
}

/* ── Source badge labels ── */
const SOURCE_BADGES: Record<string, { text: string; cls: string }> = {
  solver: { text: '✅ Solver-verified', cls: 'text-signal-positive' },
  gemini: { text: '⚠️ LLM approximation', cls: 'text-signal-neutral' },
  gpt_fallback: { text: '⚠️ LLM fallback', cls: 'text-signal-neutral' },
  validation_error: { text: '❌ Validation error', cls: 'text-signal-negative' },
}

/* ── Confidence bar width ── */
const CONFIDENCE_WIDTH: Record<string, string> = {
  high: 'w-full',
  medium: 'w-3/4',
  low: 'w-1/2',
}

/** Full advice display: top plays + metadata + street reviews + raw advice. */
const AdviceDisplay: FC<AdviceDisplayProps> = ({ result }) => {
  const sa = result.structured_advice
  const badge = SOURCE_BADGES[result.source] ?? SOURCE_BADGES.gemini

  return (
    <div className="animate-fade-in flex flex-col gap-6" style={{ animationDuration: '500ms' }}>
      {/* ── Metadata bar ── */}
      <div className="card flex flex-wrap items-center gap-4">
        <span className={`font-sans text-xs font-bold ${badge.cls}`}>{badge.text}</span>
        <span className="text-xs text-secondary">
          Mode: <span className="font-mono font-bold text-primary">{result.mode}</span>
        </span>
        {result.solve_time > 0 && (
          <span className="text-xs text-secondary">
            Solve: <span className="font-mono font-bold text-primary">{result.solve_time.toFixed(1)}s</span>
          </span>
        )}
        <span className="text-xs text-secondary">
          Parse: <span className="font-mono font-bold text-primary">{result.parse_time.toFixed(1)}s</span>
        </span>
        {result.cached && (
          <span className="rounded-sm bg-amber-400/10 px-2 py-0.5 font-mono text-xs text-signal-neutral">
            CACHED
          </span>
        )}

        {/* Confidence bar */}
        <div className="ml-auto flex items-center gap-2">
          <span className="label text-xs">Confidence</span>
          <div className="h-1.5 w-16 overflow-hidden rounded-full bg-overlay">
            <div
              className={`h-full rounded-full bg-signal-positive/60 ${CONFIDENCE_WIDTH[result.confidence] ?? 'w-1/2'}`}
            />
          </div>
          <span className="font-mono text-xs font-bold text-primary">{result.confidence}</span>
        </div>
      </div>

      {/* ── Top plays ── */}
      {sa && sa.top_plays.length > 0 && (
        <div>
          <p className="label mb-3">Top Plays</p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {sa.top_plays.map((play, i) => (
              <TopPlayCard key={play.action} play={play} rank={i} />
            ))}
          </div>
        </div>
      )}

      {/* ── Table rule ── */}
      {sa?.table_rule && (
        <div className="card border-emerald-400/20">
          <p className="label mb-1">Rule of Thumb</p>
          <p className="font-sans text-sm font-bold text-signal-positive">
            {sa.table_rule}
          </p>
        </div>
      )}

      {/* ── Street reviews ── */}
      {sa && Object.keys(sa.street_reviews).length > 0 && (
        <div className="card">
          <p className="label mb-3">Street-by-Street</p>
          <div className="flex flex-col gap-4">
            {Object.entries(sa.street_reviews).map(([street, review]) => (
              <div key={street}>
                <p className="font-sans text-xs font-bold uppercase tracking-wide text-signal-neutral">
                  {street}
                </p>
                <p className="mt-1 font-sans text-sm font-extralight leading-relaxed text-secondary">
                  {review}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Future streets ── */}
      {sa?.future_streets && (
        <div className="card">
          <p className="label mb-1">Looking Ahead</p>
          <p className="font-sans text-sm font-extralight leading-relaxed text-secondary">
            {sa.future_streets}
          </p>
        </div>
      )}

      {/* ── Scenario details (if parsed) ── */}
      {result.scenario && (
        <div className="card">
          <p className="label mb-2">Parsed Scenario</p>
          <div className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3">
            <div>
              <span className="label text-xs">Hand</span>
              <p className="data-value">{result.scenario.hero_hand || '—'}</p>
            </div>
            <div>
              <span className="label text-xs">Position</span>
              <p className="data-value">{result.scenario.hero_position || '—'}</p>
            </div>
            <div>
              <span className="label text-xs">Board</span>
              <p className="data-value">{result.scenario.board || 'preflop'}</p>
            </div>
            <div>
              <span className="label text-xs">Pot</span>
              <p className="data-value">{result.scenario.pot_size_bb} BB</p>
            </div>
            <div>
              <span className="label text-xs">Eff. Stack</span>
              <p className="data-value">{result.scenario.effective_stack_bb} BB</p>
            </div>
            <div>
              <span className="label text-xs">Street</span>
              <p className="data-value">{result.scenario.current_street}</p>
            </div>
          </div>
        </div>
      )}

      {/* ── Sanity note ── */}
      {result.sanity_note && (
        <div className="card border-signal-neutral/30">
          <p className="label mb-1">⚠ Sanity Check</p>
          <p className="text-sm text-signal-neutral">{result.sanity_note}</p>
        </div>
      )}

      {/* ── Raw advice (fallback / full text) ── */}
      <div className="card">
        <p className="label mb-2">Full Analysis</p>
        <div className="whitespace-pre-wrap font-sans text-sm font-extralight leading-relaxed text-secondary">
          {sa?.raw_advice || result.advice}
        </div>
      </div>
    </div>
  )
}

export default AdviceDisplay

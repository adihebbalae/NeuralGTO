/** Home page — placeholder for the hand analyzer UI. */
export default function Home() {
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

      {/* Input stub */}
      <div className="card w-full max-w-xl">
        <label htmlFor="hand-input" className="label mb-2 block">
          Describe your hand
        </label>
        <textarea
          id="hand-input"
          rows={3}
          placeholder="I have QQ on the button, 100bb deep. Villain opens 2.5x from CO..."
          className="w-full resize-none rounded-md border border-border bg-base px-4 py-3 font-sans text-sm text-primary placeholder:text-secondary/40 focus:outline-none focus:ring-1 focus:ring-signal-positive/50"
          aria-label="Hand description input"
        />
        <button
          type="button"
          className="mt-4 h-9 rounded-md bg-emerald-500 px-4 font-sans text-sm font-medium text-slate-950 transition-colors hover:bg-emerald-400"
          aria-label="Analyze hand"
        >
          Analyze
        </button>
      </div>

      {/* Strategy result placeholder */}
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
    </div>
  )
}

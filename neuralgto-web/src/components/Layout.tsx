import type { ReactNode } from 'react'

interface LayoutProps {
  children: ReactNode
}

/** Top-level page layout: header + sidebar stub + main content + footer. */
export default function Layout({ children }: LayoutProps) {
  return (
    <div className="flex min-h-screen flex-col">
      {/* ── Header ── */}
      <header className="flex h-12 items-center justify-between border-b border-border px-6">
        <div className="flex items-center gap-3">
          <span className="font-mono text-lg font-bold text-signal-positive tracking-tight">
            NeuralGTO
          </span>
          <span className="text-xs font-extralight text-secondary tracking-widest uppercase">
            GTO Study Tool
          </span>
        </div>
        <nav className="flex items-center gap-4">
          <a
            href="#"
            className="text-sm text-secondary transition-colors hover:text-primary"
            aria-label="Analyze a hand"
          >
            Analyze
          </a>
          <a
            href="#"
            className="text-sm text-secondary transition-colors hover:text-primary"
            aria-label="Hand history"
          >
            History
          </a>
        </nav>
      </header>

      {/* ── Body: sidebar + main ── */}
      <div className="flex flex-1">
        {/* Sidebar stub */}
        <aside className="hidden w-56 border-r border-border bg-raised p-4 lg:block">
          <p className="label mb-4">Navigation</p>
          <ul className="space-y-2">
            <li>
              <a
                href="#"
                className="block rounded-md px-3 py-2 text-sm text-secondary transition-colors hover:bg-overlay hover:text-primary"
              >
                Hand Analyzer
              </a>
            </li>
            <li>
              <a
                href="#"
                className="block rounded-md px-3 py-2 text-sm text-secondary transition-colors hover:bg-overlay hover:text-primary"
              >
                Range Viewer
              </a>
            </li>
            <li>
              <a
                href="#"
                className="block rounded-md px-3 py-2 text-sm text-secondary transition-colors hover:bg-overlay hover:text-primary"
              >
                Quiz Mode
              </a>
            </li>
          </ul>
        </aside>

        {/* Main content */}
        <main className="flex-1 p-6">{children}</main>
      </div>

      {/* ── Footer ── */}
      <footer className="flex h-10 items-center justify-center border-t border-border px-6">
        <p className="text-xs font-extralight text-secondary">
          NeuralGTO &middot; Neuro-symbolic GTO poker study tool
        </p>
      </footer>
    </div>
  )
}

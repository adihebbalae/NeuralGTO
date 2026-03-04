import { Component, type ErrorInfo, type ReactNode } from 'react'

interface ErrorBoundaryProps {
  children: ReactNode
  fallback?: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

/** Error boundary that catches render errors and shows a fallback UI. */
export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info)
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback
      return (
        <div className="card border-signal-negative/30">
          <p className="font-sans text-sm font-bold text-signal-negative">
            Something went wrong
          </p>
          <p className="mt-1 font-sans text-xs text-secondary">
            {this.state.error?.message ?? 'An unexpected error occurred.'}
          </p>
          <button
            type="button"
            onClick={() => this.setState({ hasError: false, error: null })}
            className="mt-3 h-9 rounded-md border border-border px-4 font-sans text-xs text-secondary transition-colors hover:text-primary"
            aria-label="Try again"
          >
            Try Again
          </button>
        </div>
      )
    }

    return this.props.children
  }
}

import { Component, type ReactNode, type ErrorInfo } from 'react'

interface ErrorBoundaryProps {
  children: ReactNode
  fallbackTitle?: string
  fallbackMessage?: string
  onReset?: () => void
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  public override state: ErrorBoundaryState = {
    hasError: false,
    error: null,
  }

  public static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  public override componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught rendering error:', error, errorInfo)
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null })
    this.props.onReset?.()
  }

  public override render() {
    if (this.state.hasError) {
      return (
        <div className="panel error-boundary-panel" style={{ borderLeft: '4px solid var(--status-err)' }}>
          <div className="panel-header">
            <h3 className="panel-title" style={{ color: 'var(--status-err)' }}>
              {this.props.fallbackTitle ?? 'Component Rendering Error'}
            </h3>
            <span className="badge badge-err">RECOVERED</span>
          </div>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-charcoal)', marginBottom: '0.75rem' }}>
            {this.props.fallbackMessage ??
              'A rendering issue occurred while displaying this section. The rest of the workbench remains fully operational.'}
          </p>
          {this.state.error && (
            <pre
              style={{
                fontSize: '0.75rem',
                fontFamily: 'var(--font-mono)',
                backgroundColor: 'var(--bg-cream)',
                padding: '0.5rem 0.75rem',
                border: '1px solid var(--border-sand)',
                borderRadius: '2px',
                overflowX: 'auto',
                marginBottom: '1rem',
              }}
            >
              {this.state.error.message}
            </pre>
          )}
          <button className="btn btn-secondary" onClick={this.handleReset} type="button">
            Try Reloading Component
          </button>
        </div>
      )
    }

    return this.props.children
  }
}

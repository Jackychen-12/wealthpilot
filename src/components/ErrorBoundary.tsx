import { Component, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100vh',
          background: '#0F172A',
          color: '#E2E8F0',
          fontFamily: 'Inter, sans-serif',
          gap: 16,
          padding: 24,
          textAlign: 'center',
        }}>
          <div style={{ fontSize: 48 }}>&#9888;</div>
          <h2 style={{ fontSize: 20, fontWeight: 600, margin: 0 }}>Something went wrong</h2>
          <p style={{ color: '#64748B', fontSize: 14, margin: 0 }}>
            Please refresh the page to try again.
          </p>
          <button
            onClick={() => window.location.reload()}
            style={{
              marginTop: 8,
              padding: '10px 24px',
              background: '#2563EB',
              color: '#fff',
              border: 'none',
              borderRadius: 8,
              fontSize: 14,
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            Refresh
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

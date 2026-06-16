import { Component } from 'react';

// Catches render-time crashes anywhere below it so one bad response can't white-screen
// the whole app. Shows a recoverable message instead.
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('Niha UI crashed:', error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="nx-main">
          <div className="nx-col">
            <div className="nx-card nx-pad" style={{ textAlign: 'center' }}>
              <div className="nx-empty">
                <div className="ic">⚠️</div>
                <h3 style={{ marginTop: 10 }}>Something went wrong</h3>
                <p>The UI hit an unexpected error. This is usually a malformed response or a
                  transient glitch.</p>
                <p style={{ color: 'var(--text-3)', fontSize: '.75rem' }}>{String(this.state.error?.message || this.state.error)}</p>
                <button className="nx-btn primary" style={{ marginTop: 14 }} onClick={() => window.location.reload()}>Reload</button>
              </div>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

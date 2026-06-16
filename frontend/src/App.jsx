import { useState, useEffect } from 'react';
import Console from './components/Console';
import Configure from './components/Configure';
import ErrorBoundary from './components/ErrorBoundary';
import { loadAllModels, getHealth, getApiInfo } from './api/modelIntelligenceApi';
import './index.css';

export default function App() {
  const [view, setView] = useState('console');
  const [theme, setTheme] = useState(
    () => (document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light')
  );
  const [ready, setReady] = useState(false);
  const [health, setHealth] = useState(null);
  const [info, setInfo] = useState(null);
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    document.documentElement.dataset.theme = theme === 'dark' ? 'dark' : '';
    try { localStorage.setItem('niha-theme', theme); } catch { /* ignore */ }
  }, [theme]);

  useEffect(() => {
    let cancelled = false;
    loadAllModels()
      .then(() => { if (!cancelled) setLoadError(''); })
      .catch(e => { if (!cancelled) setLoadError(e.message || 'Could not reach the backend'); })
      .finally(() => { if (!cancelled) setReady(true); });
    getHealth().then(h => !cancelled && setHealth(h)).catch(() => !cancelled && setHealth({ status: 'down' }));
    getApiInfo().then(i => !cancelled && setInfo(i)).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="nx-shell">
      <header className="nx-header">
        <div className="nx-brand">
          <span className="dot">n</span>
          <span>niha</span>
          <small>Model Intelligence</small>
        </div>
        <div className="nx-spacer" />
        {health && (
          <span title={info ? `${info.name} · mode ${health.mode || '—'} · ${health.semantic ? 'semantic' : 'keyword'}` : 'API'}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: '.72rem', fontWeight: 600, color: 'var(--text-2)' }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: health.status === 'ok' ? 'var(--green-500)' : 'var(--red-600)' }} />
            {info?.version ? `v${info.version}` : 'API'}{health.mode ? ` · ${health.mode}` : ''}
          </span>
        )}
        <nav className="nx-nav">
          <button className={view === 'console' ? 'on' : ''} onClick={() => setView('console')}>Console</button>
          <button className={view === 'configure' ? 'on' : ''} onClick={() => setView('configure')}>Configure</button>
        </nav>
        <button className="nx-icon-btn" title="Toggle theme"
          onClick={() => setTheme(t => (t === 'dark' ? 'light' : 'dark'))}>
          {theme === 'dark' ? '☀' : '☾'}
        </button>
      </header>

      <main className="nx-main">
        <div className={`nx-col ${view === 'configure' ? 'wide' : ''}`}>
          {(loadError || health?.status === 'down') && (
            <div className="nx-note warn" style={{ marginBottom: 18 }}>
              <b>Backend unreachable.</b> {loadError || 'The API at this origin is not responding.'} Start it with
              {' '}<code>uvicorn app.main:app --port 8000</code> (or set <code>VITE_API_BASE_URL</code>), then reload.
            </div>
          )}
          <ErrorBoundary>
            {view === 'console' && <Console />}
            {view === 'configure' && (ready ? <Configure /> : <div className="nx-loading">Loading catalog…</div>)}
          </ErrorBoundary>
        </div>
      </main>
    </div>
  );
}

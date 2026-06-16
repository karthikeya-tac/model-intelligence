import { useState } from 'react';
import { allModels, runComparison, runSingleTest } from '../api/modelIntelligenceApi';

const lat = (ms) => (ms == null ? '—' : ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`);

export default function Compare() {
  const [mode, setMode] = useState('compare');   // compare | single
  const [prompt, setPrompt] = useState('');
  const [picked, setPicked] = useState([]);
  const [single, setSingle] = useState(allModels[0]?.id || '');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const toggle = (id) => setPicked(p => p.includes(id) ? p.filter(x => x !== id) : p.length < 4 ? [...p, id] : p);

  const run = async () => {
    if (!prompt.trim()) return;
    setLoading(true); setError(''); setResults([]);
    try {
      if (mode === 'single') {
        if (!single) return;
        const r = await runSingleTest(single, prompt);
        setResults([{ model_id: r.model_id, latency_ms: r.latency_ms, cost_usd: r.cost_usd, value_score: r.value_score, output: r.output }]);
      } else {
        if (picked.length < 2) return;
        setResults(await runComparison(prompt, picked));
      }
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  const best = results.length ? Math.max(...results.map(r => r.value_score || 0)) : 0;
  const cheap = results.length ? Math.min(...results.map(r => r.cost_usd ?? Infinity)) : 0;
  const canRun = !loading && prompt.trim() && (mode === 'single' ? !!single : picked.length >= 2);

  return (
    <div>
      <div className="nx-toolbar">
        <div className="nx-segments">
          <button className={mode === 'compare' ? 'on' : ''} onClick={() => setMode('compare')}>Compare</button>
          <button className={mode === 'single' ? 'on' : ''} onClick={() => setMode('single')}>Single</button>
        </div>
        <div className="nx-note" style={{ flex: 1, marginLeft: 8 }}>
          {mode === 'compare' ? 'Run one prompt through 2–4 models (EP17).' : 'Run one prompt through a single model (EP18).'} Simulated from catalog data.
        </div>
      </div>

      <textarea className="nx-input" style={{ marginBottom: 12 }} rows={3} placeholder="Prompt…" value={prompt} onChange={e => setPrompt(e.target.value)} />

      {mode === 'single' ? (
        <div className="nx-field" style={{ maxWidth: 320, marginBottom: 12 }}><label>Model</label>
          <select className="nx-input" value={single} onChange={e => setSingle(e.target.value)}>{allModels.map(m => <option key={m.id} value={m.id}>{m.identity.display_name}</option>)}</select>
        </div>
      ) : (<>
        <div className="nx-mini" style={{ marginBottom: 6 }}>Pick 2–4 models ({picked.length} selected)</div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
          {allModels.map(m => <button key={m.id} className={`nx-pillbtn ${picked.includes(m.id) ? 'on' : ''}`} onClick={() => toggle(m.id)}>{m.identity.display_name}</button>)}
        </div>
      </>)}

      <button className="nx-btn primary" onClick={run} disabled={!canRun}>{loading ? 'Running…' : mode === 'single' ? 'Run test' : 'Run comparison'}</button>
      {error && <div className="nx-note warn" style={{ marginTop: 14 }}>{error}</div>}

      {results.length > 0 && (
        <div className="nx-grid" style={{ marginTop: 18 }}>
          {results.map(r => (
            <div className="nx-card nx-pad" key={r.model_id}>
              <div className="nx-mcard-h"><div className="nx-mcard-name">{r.model_id}</div>{results.length > 1 && r.value_score === best && <span className="nx-chip">top value</span>}</div>
              <div className="nx-kv" style={{ gridTemplateColumns: '1fr 1fr 1fr', marginTop: 12 }}>
                <div><div className="k">Value</div><div className="v">{r.value_score ?? '—'}</div></div>
                <div><div className="k">Cost</div><div className="v">${(r.cost_usd ?? 0).toFixed(5)}{results.length > 1 && r.cost_usd === cheap && <span className="nx-chip" style={{ marginLeft: 4 }}>min</span>}</div></div>
                <div><div className="k">Latency</div><div className="v">{lat(r.latency_ms)}</div></div>
              </div>
              {r.output && <div className="nx-out-body" style={{ maxHeight: 160, marginTop: 10, padding: 0 }}>{r.output}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

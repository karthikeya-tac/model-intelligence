import { useState, useEffect } from 'react';
import { consoleAsk, getIntents } from '../api/modelIntelligenceApi';

const PROVIDER = { anthropic: 'Anthropic', openai: 'OpenAI', google: 'Google', xai: 'xAI', ollama: 'Ollama' };
const tc = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
const fmt = (n) => (n == null ? '—' : Number(n).toLocaleString('en-US'));
const lat = (ms) => (ms == null ? '—' : ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`);

export default function Console() {
  const [prompt, setPrompt] = useState('');
  const [showOpts, setShowOpts] = useState(false);
  const [agent, setAgent] = useState('');
  const [workspace, setWorkspace] = useState('');
  const [sessionTokens, setSessionTokens] = useState('');
  const [intentId, setIntentId] = useState('');
  const [intents, setIntents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [showWhy, setShowWhy] = useState(false);
  const [history, setHistory] = useState([]);

  useEffect(() => { getIntents().then(setIntents).catch(() => {}); }, []);

  const ask = async () => {
    if (!prompt.trim() || loading) return;
    setLoading(true); setError(''); setResult(null); setShowWhy(false);
    try {
      const body = { prompt, execute: true };
      if (agent) body.agent = agent;
      if (workspace) body.workspace = workspace;
      if (sessionTokens) body.session_tokens = Number(sessionTokens);
      if (intentId) body.intent_id = intentId;
      const data = await consoleAsk(body);
      setResult(data);
      setHistory(h => [{ id: Date.now(), prompt, model: data.decision.model_id, data }, ...h].slice(0, 6));
    } catch (e) {
      setError(e.message || 'Request failed');
    } finally {
      setLoading(false);
    }
  };
  const onKey = (e) => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') ask(); };

  return (
    <div>
      <div className="nx-hero">
        <div className="nx-eyebrow">Niha · Routing Console</div>
        <h1 className="nx-h1">Ask anything. <span className="g">We route it.</span></h1>
        <div className="nx-sub">See which model the router picks, why — and the answer.</div>
      </div>

      <div className="nx-cmd">
        <textarea rows={2} value={prompt} onChange={e => setPrompt(e.target.value)} onKeyDown={onKey}
          placeholder="e.g. write a function to dedupe a list… (⌘/Ctrl + Enter)" />
        <div className="nx-cmd-bar">
          <span className="nx-mini" style={{ alignSelf: 'center' }}>Auto-routes to the best model for your question</span>
          <button className="nx-opts-toggle" onClick={() => setShowOpts(o => !o)}>{showOpts ? '− options' : '+ options'}</button>
          <button className="nx-ask" onClick={ask} disabled={loading || !prompt.trim()}>
            {loading ? 'Routing…' : 'Ask'}<span>→</span>
          </button>
        </div>
        {showOpts && (
          <div className="nx-opts">
            <div className="nx-field">
              <label>Intent override</label>
              <select className="nx-input" value={intentId} onChange={e => setIntentId(e.target.value)}>
                <option value="">Auto — classify from prompt</option>
                {intents.map(i => <option key={i.id} value={i.id}>{i.name} · {i.category}</option>)}
              </select>
            </div>
            <div className="nx-field"><label>Agent</label>
              <input className="nx-input" value={agent} onChange={e => setAgent(e.target.value)} placeholder="doc-writer, codex…" /></div>
            <div className="nx-field"><label>Workspace</label>
              <input className="nx-input" value={workspace} onChange={e => setWorkspace(e.target.value)} placeholder="payment-service…" /></div>
            <div className="nx-field"><label>Session tokens</label>
              <input className="nx-input" type="number" value={sessionTokens} onChange={e => setSessionTokens(e.target.value)} placeholder="180000" /></div>
          </div>
        )}
      </div>

      {error && <div className="nx-note warn" style={{ marginTop: 16 }}>{error}</div>}
      {loading && <div className="nx-note" style={{ marginTop: 16 }}>Classifying intent → resolving tier → scoring models…</div>}

      {result && <Result result={result} showWhy={showWhy} setShowWhy={setShowWhy} />}

      {history.length > 0 && (
        <div className="nx-recent">
          <h4>Recent</h4>
          {history.map(h => (
            <button key={h.id} className="nx-recent-item" onClick={() => { setResult(h.data); setPrompt(h.prompt); setShowWhy(false); }}>
              <span className="q">{h.prompt.slice(0, 80)}</span><span className="m">{h.model}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Result({ result, showWhy, setShowWhy }) {
  const d = result.decision, m = result.model || {}, est = result.estimate || {}, out = result.output || {};
  const tier = d.tier;
  const caps = (m.benchmarks && m.benchmarks.capability_scores) || {};
  const intentScore = d.intent_id && caps[d.intent_id];

  return (
    <div className="nx-result">
      <div className="nx-card nx-pad nx-model">
        <div className="nx-model-top"><span className="nx-tag">Router selected</span></div>
        <div className="nx-model-name">
          {m.display_name || d.model_id}
          <span className={`nx-tier ${tier}`}>{tier}</span>
        </div>
        <div className="nx-model-meta">{PROVIDER[m.provider] || tc(m.provider)} · {tc(m.classification?.status || 'active')}</div>
        <div className="nx-reason">{d.reason}</div>

        <div className="nx-kv">
          <div><div className="k">Intent</div><div className="v">{d.intent_id || '—'}</div></div>
          <div><div className="k">Confidence</div><div className="v">{d.intent_source}</div></div>
          {intentScore != null
            ? <div><div className="k">Capability</div><div className="v">{intentScore}/100</div></div>
            : <div><div className="k">Input price</div><div className="v">${m.pricing?.input ?? '—'}</div></div>}
          <div><div className="k">Est. cost</div><div className="v">${(est.cost_usd ?? 0).toFixed(5)}</div></div>
          <div><div className="k">Context</div><div className="v">{fmt(m.capability?.context_window)}</div></div>
          <div><div className="k">Max output</div><div className="v">{fmt(m.capability?.max_output_tokens)}</div></div>
          <div><div className="k">In / Out $/1M</div><div className="v">{m.pricing?.input ?? '—'}/{m.pricing?.output ?? '—'}</div></div>
          <div><div className="k">Est. latency</div><div className="v">{lat(est.latency_ms)}</div></div>
        </div>

        {d.matched_rules?.length > 0 && (
          <div className="nx-chips">{d.matched_rules.map(r => <span key={r.rule_id} className="nx-chip">⚙ {r.rule_id}</span>)}</div>
        )}

        <button className="nx-link" onClick={() => setShowWhy(w => !w)}>{showWhy ? 'Hide routing detail' : 'Why this model? →'}</button>
        {showWhy && (
          <div className="nx-why">
            {(d.candidates || []).slice(0, 5).map(c => (
              <div key={c.model_id} className={`nx-cand ${c.model_id === d.model_id ? 'win' : ''}`}>
                <span className="name">{c.model_id}</span>
                <span className="nx-bars">
                  <i title="capability fit" style={{ width: `${(c.quality || 0) * 130}px` }} />
                </span>
                <span className="sc">{Math.round((c.quality ?? 0) * 100)}</span>
              </div>
            ))}
            <div className="nx-mini">ranked by capability fit for this intent (0–100) · ties broken by cost then latency</div>
          </div>
        )}
      </div>

      <div className="nx-card">
        <div className="nx-out-head">
          <h3>Output</h3>
          {out.output && out.real_model && <span className="nx-live">live via {out.real_model}</span>}
        </div>
        {out.output ? (
          <div className="nx-out-body">{out.output}</div>
        ) : out.configured && out.error ? (
          <div className="nx-note warn" style={{ margin: '16px 20px' }}>Live call failed — {out.error}</div>
        ) : (
          <div className="nx-empty">
            <div className="ic">🔌</div>
            <p>No live output yet. Set <code>{out.env_var || 'the provider key'}</code> in <code>backend/.env</code> to run this
              through {PROVIDER[m.provider] || tc(m.provider)}’s real model{out.real_model ? ` (${out.real_model})` : ''}.</p>
          </div>
        )}
        <div className="nx-out-foot">Estimated <b>${(est.cost_usd ?? 0).toFixed(5)}</b> · <b>{lat(est.latency_ms)}</b> · value <b>{est.value_score ?? '—'}</b></div>
      </div>
    </div>
  );
}

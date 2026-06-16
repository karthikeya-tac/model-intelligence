import { useEffect, useState } from 'react';
import { getModelBenchmarks, getModelUsage, saveModelConfig } from '../api/modelIntelligenceApi';

const PROVIDER = { anthropic: 'Anthropic', openai: 'OpenAI', google: 'Google', xai: 'xAI', ollama: 'Ollama' };
const tc = (s) => (s ? String(s).charAt(0).toUpperCase() + String(s).slice(1) : s);
const pretty = (k) => String(k).replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
const TIERS = ['fast', 'standard', 'powerful'];
const STATUSES = ['active', 'preview', 'standby', 'deprecated', 'disabled'];

function clean(v) {
  if (v == null || v === '') return undefined;
  if (Array.isArray(v)) { const a = v.map(clean).filter(x => x !== undefined); return a.length ? a : undefined; }
  if (typeof v === 'object') {
    const o = {}; for (const [k, val] of Object.entries(v)) { const c = clean(val); if (c !== undefined) o[k] = c; }
    return Object.keys(o).length ? o : undefined;
  }
  return v;
}
function fmtVal(v) {
  if (Array.isArray(v)) return v.map(fmtVal).join(', ');
  if (typeof v === 'object') return Object.entries(v).map(([k, val]) => `${pretty(k)} ${fmtVal(val)}`).join(' · ');
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  if (typeof v === 'number') return v.toLocaleString('en-US');
  return String(v);
}
function DefList({ obj, order, omit = [] }) {
  const keys = (order || Object.keys(obj || {})).filter(k => !omit.includes(k));
  const rows = keys.map(k => [k, clean(obj?.[k])]).filter(([, v]) => v !== undefined);
  if (!rows.length) return <div className="nx-na" style={{ fontSize: '.8rem' }}>Not available</div>;
  return <div className="nx-deflist">{rows.map(([k, v]) => <div className="row" key={k}><span>{pretty(k)}</span><b>{fmtVal(v)}</b></div>)}</div>;
}
function Bars({ scores }) {
  const rows = Object.entries(scores || {});
  if (!rows.length) return <div className="nx-na" style={{ fontSize: '.8rem' }}>Not available</div>;
  return (
    <div className="nx-bench">
      {rows.map(([k, v]) => (
        <div className="nx-bench-row" key={k}>
          <span className="lbl">{pretty(k)}</span>
          <span className="track"><span className="fill" style={{ width: `${v}%` }} /></span>
          <span className="num">{v}</span>
        </div>
      ))}
    </div>
  );
}

export default function ModelDetail({ model, onClose }) {
  const id = model?.id;
  const raw = model?._raw || {};
  const cap = raw.capability || {};
  const pricing = raw.pricing || {};
  const controls = raw.controls || {};
  const cls = raw.classification || {};
  const tunable = (controls.sampling || '').toLowerCase() === 'tunable';

  const [bench, setBench] = useState(null);
  const [usage, setUsage] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('info');
  const [cfg, setCfg] = useState({ tier: cls.tier, status: cls.status, rate_limit_rpm: '', temperature: '' });
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState('');

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    Promise.all([getModelBenchmarks(id).catch(() => null), getModelUsage(id).catch(() => null)])
      .then(([b, u]) => { if (!cancelled) { setBench(b); setUsage(u); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [id]);

  if (!model) return null;

  const specOrder = ['context_window', 'max_output_tokens', 'input_modalities', 'output_modalities',
    'reasoning_level', 'supports_tools', 'supports_streaming', 'knowledge_cutoff'];

  const save = async () => {
    setSaving(true);
    try {
      const patch = {};
      if (cfg.tier && cfg.tier !== cls.tier) patch.tier = cfg.tier;
      if (cfg.status && cfg.status !== cls.status) patch.status = cfg.status;
      if (cfg.rate_limit_rpm !== '') patch.rate_limit_rpm = Number(cfg.rate_limit_rpm);
      if (tunable && cfg.temperature !== '') patch.temperature = Number(cfg.temperature);
      if (!Object.keys(patch).length) { setToast('No changes'); }
      else { await saveModelConfig(id, patch); setToast('Saved to overlay (Phase 0)'); }
      setTimeout(() => setToast(''), 2400);
    } catch (e) { setToast(e.message); setTimeout(() => setToast(''), 3000); }
    finally { setSaving(false); }
  };

  return (
    <div className="nx-drawer-bg" onClick={onClose}>
      <aside className="nx-drawer" onClick={e => e.stopPropagation()}>
        <div className="nx-drawer-h">
          <div>
            <div className="nx-tag">{PROVIDER[model._provider] || tc(model._provider)}</div>
            <h2>{model.identity.display_name} <span className={`nx-tier ${model._tier}`}>{model._tier}</span></h2>
          </div>
          <button className="nx-icon-btn" onClick={onClose}>✕</button>
        </div>

        <div className="nx-subnav" style={{ padding: '0 22px', marginBottom: 0 }}>
          {[['info', 'Overview'], ['bench', 'Benchmarks'], ['usage', 'Usage'], ['config', 'Config']].map(([k, l]) => (
            <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>
          ))}
        </div>

        <div className="nx-drawer-body">
          {tab === 'info' && (<>
            {model.identity.description
              ? <p style={{ fontSize: '.86rem', color: 'var(--text-2)', lineHeight: 1.6 }}>{model.identity.description}</p>
              : <p className="nx-na" style={{ fontSize: '.86rem' }}>No description available.</p>}
            <div className="nx-sublabel">Identity</div>
            <DefList obj={{ api_model_name: model.identity.api_model_name, release_date: model.identity.release_date, status: tc(cls.status), role: tc(cls.role), latency_class: cls.latency_class }} />
            <div className="nx-sublabel">Specifications</div>
            <DefList obj={cap} order={specOrder} />
            <div className="nx-sublabel">Pricing — USD / 1M tokens</div>
            <DefList obj={pricing} omit={['currency']} />
            <div className="nx-sublabel">Controls</div>
            <DefList obj={controls} />
          </>)}

          {tab === 'bench' && (loading ? <div className="nx-loading">Loading benchmarks…</div> : <>
            <div className="nx-sublabel">Capability estimates <span style={{ color: 'var(--text-3)', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>· catalog’s own 0–100 (EP5)</span></div>
            <Bars scores={bench?.capabilities} />
            <div className="nx-sublabel">Standard benchmark results</div>
            <DefList obj={bench?.standard} />
          </>)}

          {tab === 'usage' && (loading ? <div className="nx-loading">Loading usage…</div> : <>
            <div className="nx-note" style={{ marginBottom: 12 }}>Usage telemetry is <b>simulated (Phase 0)</b> — seeded in-memory, not real traffic.</div>
            <div className="nx-kv" style={{ gridTemplateColumns: '1fr 1fr' }}>
              <div><div className="k">Requests ({usage?.period || 'month'})</div><div className="v">{usage?.requests ?? '—'}</div></div>
              <div><div className="k">Share of traffic</div><div className="v">{usage?.pct ?? '—'}%</div></div>
              <div><div className="k">Cost</div><div className="v">${(usage?.cost_usd ?? 0).toFixed(4)}</div></div>
              <div><div className="k">Avg latency</div><div className="v">{usage?.avg_latency_ms ?? '—'}ms</div></div>
            </div>
          </>)}

          {tab === 'config' && (<>
            <div className="nx-note" style={{ marginBottom: 14 }}>Edits write to the in-memory overlay (EP4). They reset on registry reload — Phase 0 has no persistence.</div>
            <div className="nx-opts" style={{ marginTop: 0, paddingTop: 0, borderTop: 'none', gridTemplateColumns: '1fr 1fr' }}>
              <div className="nx-field"><label>Tier</label><select className="nx-input" value={cfg.tier} onChange={e => setCfg({ ...cfg, tier: e.target.value })}>{TIERS.map(t => <option key={t}>{t}</option>)}</select></div>
              <div className="nx-field"><label>Status</label><select className="nx-input" value={cfg.status} onChange={e => setCfg({ ...cfg, status: e.target.value })}>{STATUSES.map(s => <option key={s}>{s}</option>)}</select></div>
              <div className="nx-field"><label>Rate limit (rpm)</label><input className="nx-input" type="number" value={cfg.rate_limit_rpm} placeholder="unset" onChange={e => setCfg({ ...cfg, rate_limit_rpm: e.target.value })} /></div>
              <div className="nx-field"><label>Temperature {tunable ? '' : '(locked)'}</label><input className="nx-input" type="number" step="0.1" disabled={!tunable} value={cfg.temperature} placeholder={tunable ? 'e.g. 0.7' : 'sampling locked'} onChange={e => setCfg({ ...cfg, temperature: e.target.value })} /></div>
            </div>
            <button className="nx-btn primary" style={{ marginTop: 14 }} onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save config'}</button>
          </>)}
        </div>
        <div className={`nx-toast ${toast ? 'show' : ''}`}>{toast}</div>
      </aside>
    </div>
  );
}

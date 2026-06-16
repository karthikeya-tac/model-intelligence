import { useEffect, useMemo, useState } from 'react';
import { getModels, createModel } from '../api/modelIntelligenceApi';
import ModelDetail from './ModelDetail';

const TIERS = ['', 'fast', 'standard', 'powerful'];
const PROVIDER = { anthropic: 'Anthropic', openai: 'OpenAI', google: 'Google' };

export default function Catalog() {
  const [models, setModels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [q, setQ] = useState('');
  const [tier, setTier] = useState('');
  const [provider, setProvider] = useState('');
  const [selected, setSelected] = useState(null);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ provider_id: '', model_ref: '', tier: 'standard', display_name: '' });
  const [creating, setCreating] = useState(false);
  const [toast, setToast] = useState('');

  const load = () => {
    setLoading(true);
    getModels()
      .then(list => { setModels(list); setError(''); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const providers = useMemo(() => [...new Set(models.map(m => m._provider))], [models]);
  const shown = useMemo(() => models.filter(m =>
    (!tier || m._tier === tier) && (!provider || m._provider === provider) &&
    (!q || m.identity.display_name.toLowerCase().includes(q.toLowerCase()) || m.id.toLowerCase().includes(q.toLowerCase()))
  ), [models, tier, provider, q]);

  const flash = (m) => { setToast(m); setTimeout(() => setToast(''), 3200); };
  const create = async () => {
    if (!form.provider_id || !form.model_ref.trim()) return;
    setCreating(true);
    try {
      const res = await createModel({ provider_id: form.provider_id, model_ref: form.model_ref.trim(), tier: form.tier, display_name: form.display_name || undefined });
      flash(`Registered “${res.model_id}” in the overlay · Phase 0 keeps the catalog file-backed, so it won’t appear in the list until Phase 1.`);
      setShowAdd(false); setForm({ provider_id: '', model_ref: '', tier: 'standard', display_name: '' });
    } catch (e) { flash(e.message); }
    finally { setCreating(false); }
  };

  return (
    <div>
      <div className="nx-toolbar">
        <input className="nx-input" style={{ maxWidth: 240 }} placeholder="Search models…" value={q} onChange={e => setQ(e.target.value)} />
        <div style={{ display: 'flex', gap: 6 }}>
          {TIERS.map(t => <button key={t || 'all'} className={`nx-pillbtn ${tier === t ? 'on' : ''}`} onClick={() => setTier(t)}>{t || 'All tiers'}</button>)}
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button className={`nx-pillbtn ${provider === '' ? 'on' : ''}`} onClick={() => setProvider('')}>All providers</button>
          {providers.map(p => <button key={p} className={`nx-pillbtn ${provider === p ? 'on' : ''}`} onClick={() => setProvider(p)}>{PROVIDER[p] || p}</button>)}
        </div>
        <button className="nx-btn primary" style={{ marginLeft: 'auto' }} onClick={() => setShowAdd(s => !s)}>{showAdd ? 'Cancel' : '+ Add model'}</button>
      </div>

      {showAdd && (
        <div className="nx-card nx-pad" style={{ marginBottom: 16 }}>
          <div className="nx-opts" style={{ marginTop: 0, paddingTop: 0, borderTop: 'none' }}>
            <div className="nx-field"><label>Provider</label>
              <select className="nx-input" value={form.provider_id} onChange={e => setForm({ ...form, provider_id: e.target.value })}>
                <option value="">choose…</option>{providers.map(p => <option key={p} value={p}>{PROVIDER[p] || p}</option>)}
              </select></div>
            <div className="nx-field"><label>Model ref (api name)</label><input className="nx-input" value={form.model_ref} onChange={e => setForm({ ...form, model_ref: e.target.value })} placeholder="e.g. claude-opus-5" /></div>
            <div className="nx-field"><label>Tier</label><select className="nx-input" value={form.tier} onChange={e => setForm({ ...form, tier: e.target.value })}>{['fast', 'standard', 'powerful'].map(t => <option key={t}>{t}</option>)}</select></div>
            <div className="nx-field"><label>Display name (optional)</label><input className="nx-input" value={form.display_name} onChange={e => setForm({ ...form, display_name: e.target.value })} /></div>
          </div>
          <button className="nx-btn primary" style={{ marginTop: 14 }} onClick={create} disabled={creating || !form.provider_id || !form.model_ref.trim()}>{creating ? 'Registering…' : 'Register model'}</button>
        </div>
      )}

      {loading && <div className="nx-loading">Loading catalog…</div>}
      {error && <div className="nx-note warn">{error}</div>}

      <div className="nx-grid">
        {shown.map(m => (
          <div className="nx-mcard" key={m.id} onClick={() => setSelected(m)}>
            <div className="nx-mcard-h">
              <div><div className="nx-mcard-name">{m.identity.display_name}</div><div className="nx-mcard-prov">{PROVIDER[m._provider] || m._provider}</div></div>
              <span className={`nx-tier ${m._tier}`}>{m._tier}</span>
            </div>
            <div className="nx-mcard-row">
              <span>ctx <b>{m.capability.context_window}</b></span>
              <span>in <b>${m.pricing_in ?? '—'}</b></span>
              <span>out <b>${m.pricing_out ?? '—'}</b></span>
            </div>
            <div className="nx-mcard-row" style={{ marginTop: 8 }}>
              <span className={`nx-status ${m.classify.status?.toLowerCase() === 'active' ? '' : 'muted'}`}>{m.classify.status}</span>
            </div>
          </div>
        ))}
      </div>
      {!loading && shown.length === 0 && <div className="nx-loading">No models match.</div>}

      {selected && <ModelDetail model={selected} onClose={() => setSelected(null)} />}
      <div className={`nx-toast ${toast ? 'show' : ''}`}>{toast}</div>
    </div>
  );
}

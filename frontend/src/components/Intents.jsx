import { useEffect, useMemo, useState } from 'react';
import { getIntents, saveIntentTiers, classifyPrompt } from '../api/modelIntelligenceApi';

const TIERS = ['fast', 'standard', 'powerful'];

export default function Intents() {
  const [intents, setIntents] = useState([]);
  const [draft, setDraft] = useState({});   // id -> {tier, min_tier}
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState('');
  const [open, setOpen] = useState({});
  const [probe, setProbe] = useState('');
  const [probeRes, setProbeRes] = useState(null);
  const [probing, setProbing] = useState(false);

  const classify = async () => {
    if (!probe.trim()) return;
    setProbing(true); setProbeRes(null);
    try { setProbeRes(await classifyPrompt(probe)); }
    catch (e) { setProbeRes({ error: e.message }); }
    finally { setProbing(false); }
  };

  const load = () => {
    setLoading(true);
    getIntents()
      .then(list => {
        setIntents(list);
        const d = {};
        list.forEach(i => { d[i.id] = { tier: i.tier, min_tier: i.min_tier || 'fast' }; });
        setDraft(d);
        setError('');
        const cats = {}; list.forEach(i => { cats[i.category] = true; }); setOpen(cats);
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const groups = useMemo(() => {
    const g = {};
    intents.forEach(i => { (g[i.category] = g[i.category] || []).push(i); });
    return g;
  }, [intents]);

  const dirty = useMemo(() => intents.filter(i =>
    draft[i.id] && (draft[i.id].tier !== i.tier || (draft[i.id].min_tier || 'fast') !== (i.min_tier || 'fast'))
  ), [intents, draft]);

  const set = (id, field, val) => setDraft(d => ({ ...d, [id]: { ...d[id], [field]: val } }));

  const save = async () => {
    if (!dirty.length) return;
    setSaving(true);
    try {
      await saveIntentTiers(dirty.map(i => ({ id: i.id, tier: draft[i.id].tier, min_tier: draft[i.id].min_tier })));
      setToast(`Saved ${dirty.length} intent${dirty.length > 1 ? 's' : ''}`);
      setTimeout(() => setToast(''), 2200);
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="nx-loading">Loading intents…</div>;
  if (error) return <div className="nx-note warn">{error}</div>;

  return (
    <div>
      <div className="nx-toolbar">
        <div className="nx-note" style={{ flex: 1 }}>
          Each intent maps to a <b>default tier</b> (Level-1 pick) with a <b>min tier</b> floor the router can’t go below. Backend-driven from <code>intents.yaml</code>.
        </div>
        <button className="nx-btn primary" onClick={save} disabled={!dirty.length || saving}>
          {saving ? 'Saving…' : dirty.length ? `Save ${dirty.length}` : 'No changes'}
        </button>
      </div>

      <div className="nx-card nx-pad" style={{ marginBottom: 16 }}>
        <div className="nx-sublabel" style={{ marginTop: 0 }}>Classify a prompt <span style={{ color: 'var(--text-3)', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>· the real Level-1 engine (EP9)</span></div>
        <div style={{ display: 'flex', gap: 8 }}>
          <input className="nx-input" style={{ flex: 1 }} value={probe} placeholder="e.g. refactor this function and add unit tests"
            onChange={e => setProbe(e.target.value)} onKeyDown={e => e.key === 'Enter' && classify()} />
          <button className="nx-btn primary" onClick={classify} disabled={probing || !probe.trim()}>{probing ? '…' : 'Classify'}</button>
        </div>
        {probeRes && (probeRes.error
          ? <div className="nx-note warn" style={{ marginTop: 12 }}>{probeRes.error}</div>
          : <div className="nx-kv" style={{ gridTemplateColumns: 'repeat(4,1fr)', marginTop: 12 }}>
              <div><div className="k">Intent</div><div className="v">{probeRes.intent_id || '—'}</div></div>
              <div><div className="k">Category</div><div className="v">{probeRes.category || '—'}</div></div>
              <div><div className="k">Source</div><div className="v">{probeRes.source}</div></div>
              <div><div className="k">Confidence</div><div className="v">{probeRes.confidence != null ? `${Math.round(probeRes.confidence * 100)}%` : '—'}</div></div>
            </div>)}
      </div>

      {Object.entries(groups).map(([cat, items]) => (
        <div className="nx-cat" key={cat}>
          <div className="nx-cat-h" onClick={() => setOpen(o => ({ ...o, [cat]: !o[cat] }))}>
            <span className="nm">{cat}</span>
            <span className="ct">{items.length} intent{items.length > 1 ? 's' : ''}</span>
            <span style={{ color: 'var(--text-3)' }}>{open[cat] ? '▾' : '▸'}</span>
          </div>
          {open[cat] && items.map(i => (
            <div className="nx-irow" key={i.id}>
              <div className="nm"><b>{i.name}</b><span>{i.description || i.id}</span></div>
              <div className="sel">
                <div>
                  <div className="nx-mini">default</div>
                  <select className="nx-input" style={{ height: 34, width: 120 }} value={draft[i.id]?.tier}
                    onChange={e => set(i.id, 'tier', e.target.value)}>
                    {TIERS.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div>
                  <div className="nx-mini">min</div>
                  <select className="nx-input" style={{ height: 34, width: 120 }} value={draft[i.id]?.min_tier}
                    onChange={e => set(i.id, 'min_tier', e.target.value)}>
                    {TIERS.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
              </div>
            </div>
          ))}
        </div>
      ))}

      <div className={`nx-toast ${toast ? 'show' : ''}`}>{toast}</div>
    </div>
  );
}

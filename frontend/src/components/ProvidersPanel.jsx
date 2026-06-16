import { useEffect, useRef, useState } from 'react';
import {
  getProviders, getProviderHealth, getFallbackChains, saveFallbackChains,
  getTriggerConfig, saveTriggerConfig, getArchitectConfig, saveArchitectConfig,
  connectProvider, testProvider, saveProvider, deleteProvider, discoverProviderModels,
} from '../api/modelIntelligenceApi';

const TIERS = ['fast', 'standard', 'powerful'];
const ROLES = ['primary', 'secondary', 'fallback'];

export default function ProvidersPanel() {
  const [providers, setProviders] = useState([]);
  const [health, setHealth] = useState(null);
  const [chains, setChains] = useState({});
  const [trigger, setTrigger] = useState({ trigger: 'error_or_timeout', retries: '2', notify: 'none' });
  const [arch, setArch] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [busy, setBusy] = useState('');
  const [edit, setEdit] = useState(null);          // provider_id being edited
  const [editForm, setEditForm] = useState({});
  const [showConnect, setShowConnect] = useState(false);
  const [connectForm, setConnectForm] = useState({ kind: '', base_url: '' });
  const [testResult, setTestResult] = useState({});
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);   // guard setState after unmount

  const flash = (m) => { setToast(m); setTimeout(() => setToast(''), 2600); };
  const load = () => {
    setLoading(true);
    Promise.all([getProviders(), getProviderHealth(), getFallbackChains(), getTriggerConfig(), getArchitectConfig()])
      .then(([p, h, c, t, a]) => { if (alive.current) { setProviders(p); setHealth(h); setChains(c); setTrigger(t); setArch(a); setError(''); } })
      .catch(e => { if (alive.current) setError(e.message); })
      .finally(() => { if (alive.current) setLoading(false); });
  };
  useEffect(load, []);

  const healthFor = (id) => health?.providers?.find(p => p.provider_id === id);

  const saveArch = async (patch) => {
    setArch(a => ({ ...a, ...patch }));
    try { const s = await saveArchitectConfig({ ...arch, ...patch }); setArch(s); flash('Architect mode saved'); }
    catch (e) { flash(e.message); load(); }
  };

  const test = async (id) => {
    setBusy(`test:${id}`);
    try {
      const [r, models] = await Promise.all([testProvider(id), discoverProviderModels(id)]);  // EP21 + EP22
      setTestResult(t => ({ ...t, [id]: { ...r, models } }));
      flash(r.configured ? `${id}: key configured · ${models.length} models` : `${id}: no API key set · ${models.length} models`);
    } catch (e) { flash(e.message); }
    finally { setBusy(''); }
  };

  const del = async (id) => {
    if (!window.confirm(`Delete provider "${id}"?`)) return;
    setBusy(`del:${id}`);
    try { await deleteProvider(id); flash('Provider deleted'); load(); }
    catch (e) {
      if (/force/i.test(e.message) && window.confirm(`${e.message}\n\nForce delete anyway?`)) {
        try { await deleteProvider(id, true); flash('Provider force-deleted'); load(); } catch (e2) { flash(e2.message); }
      } else flash(e.message);
    } finally { setBusy(''); }
  };

  const openEdit = (p) => { setEdit(p.provider_id); setEditForm({ role: (p.role || '').toLowerCase(), base_url: p.base_url || '' }); };
  const saveEdit = async (id) => {
    setBusy(`edit:${id}`);
    try { await saveProvider(id, { role: editForm.role, base_url: editForm.base_url || undefined }); flash('Provider updated'); setEdit(null); load(); }
    catch (e) { flash(e.message); }
    finally { setBusy(''); }
  };

  const connect = async () => {
    if (!connectForm.kind.trim()) return;
    setBusy('connect');
    try { await connectProvider(connectForm.kind.trim(), null, connectForm.base_url || undefined); flash(`Connected “${connectForm.kind}” (key goes in backend/.env as ${connectForm.kind.toUpperCase()}_API_KEY)`); setShowConnect(false); setConnectForm({ kind: '', base_url: '' }); load(); }
    catch (e) { flash(e.message); }
    finally { setBusy(''); }
  };

  const saveChains = async () => {
    setBusy('chains');
    try { await saveFallbackChains(chains); await saveTriggerConfig(trigger); flash('Fallback saved'); }
    catch (e) { flash(e.message); }
    finally { setBusy(''); }
  };
  const setChain = (tier, val) => setChains(c => ({ ...c, [tier]: val.split(',').map(s => s.trim()).filter(Boolean) }));

  if (loading) return <div className="nx-loading">Loading providers…</div>;
  if (error) return <div className="nx-note warn">{error}</div>;

  return (
    <div>
      {/* Architect mode (EP26) */}
      {arch && (
        <div className="nx-card nx-pad" style={{ marginBottom: 18 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ flex: 1 }}>
              <div className="nx-mcard-name">Architect Mode</div>
              <div className="nx-mcard-prov">Split a request into plan (high tier) + exec (lower tier) to cut cost. EP26.</div>
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '.82rem', fontWeight: 600 }}>
              <input type="checkbox" checked={!!arch.enabled} onChange={e => saveArch({ enabled: e.target.checked })} />
              {arch.enabled ? 'On' : 'Off'}
            </label>
          </div>
          {arch.enabled && (
            <div className="nx-opts" style={{ marginTop: 14, paddingTop: 14, gridTemplateColumns: '1fr 1fr' }}>
              <div className="nx-field"><label>Plan tier</label><select className="nx-input" value={arch.plan_tier} onChange={e => saveArch({ plan_tier: e.target.value })}>{TIERS.map(t => <option key={t}>{t}</option>)}</select></div>
              <div className="nx-field"><label>Exec tier</label><select className="nx-input" value={arch.exec_tier} onChange={e => saveArch({ exec_tier: e.target.value })}>{TIERS.map(t => <option key={t}>{t}</option>)}</select></div>
            </div>
          )}
        </div>
      )}

      {/* Providers (EP19/20/21/23/24) */}
      <div className="nx-secthead"><h3>Providers</h3><button className="nx-btn primary" onClick={() => setShowConnect(s => !s)}>{showConnect ? 'Cancel' : '+ Connect provider'}</button></div>
      {showConnect && (
        <div className="nx-card nx-pad" style={{ marginBottom: 12 }}>
          <div className="nx-note" style={{ marginBottom: 12 }}>The key is never stored — it’s referenced as <code>{(connectForm.kind || 'KIND').toUpperCase()}_API_KEY</code> from <code>backend/.env</code>.</div>
          <div className="nx-opts" style={{ marginTop: 0, paddingTop: 0, borderTop: 'none', gridTemplateColumns: '1fr 1fr' }}>
            <div className="nx-field"><label>Kind</label><input className="nx-input" value={connectForm.kind} onChange={e => setConnectForm({ ...connectForm, kind: e.target.value })} placeholder="e.g. xai, mistral, ollama" /></div>
            <div className="nx-field"><label>Base URL (optional)</label><input className="nx-input" value={connectForm.base_url} onChange={e => setConnectForm({ ...connectForm, base_url: e.target.value })} placeholder="https://…" /></div>
          </div>
          <button className="nx-btn primary" style={{ marginTop: 14 }} onClick={connect} disabled={busy === 'connect' || !connectForm.kind.trim()}>{busy === 'connect' ? 'Connecting…' : 'Connect'}</button>
        </div>
      )}

      {providers.map(p => {
        const t = testResult[p.provider_id];
        return (
          <div className="nx-prov" key={p.provider_id} style={{ flexWrap: 'wrap' }}>
            <span className="ic">{p.icon}</span>
            <div className="info">
              <div className="nm">{p.name}</div>
              <div className="mt">{p.role} · {p.models_summary} · key {p.api_key_hint ? <code>{p.api_key_hint}</code> : <span className="nx-na">not configured</span>}{t && <> · <b style={{ color: t.configured ? 'var(--green-700)' : 'var(--text-3)' }}>{t.configured ? 'key live' : 'no key'}</b></>}</div>
            </div>
            <span className={`nx-status ${p.status === 'connected' ? '' : 'muted'}`}>{p.status}</span>
            {t?.models?.length > 0 && (
              <div className="nx-chips" style={{ width: '100%', marginTop: 4 }}>
                {t.models.map(m => <span key={m.ref} className="nx-chip">{m.name}</span>)}
              </div>
            )}
            <div className="nx-rule-actions" style={{ width: '100%', marginTop: 4, justifyContent: 'flex-end' }}>
              <button className="nx-btn" disabled={busy === `test:${p.provider_id}`} onClick={() => test(p.provider_id)}>{busy === `test:${p.provider_id}` ? '…' : 'Test'}</button>
              <button className="nx-btn" onClick={() => (edit === p.provider_id ? setEdit(null) : openEdit(p))}>{edit === p.provider_id ? 'Close' : 'Edit'}</button>
              <button className="nx-btn danger" disabled={busy === `del:${p.provider_id}`} onClick={() => del(p.provider_id)}>{busy === `del:${p.provider_id}` ? '…' : 'Delete'}</button>
            </div>
            {edit === p.provider_id && (
              <div style={{ width: '100%', borderTop: '1px solid var(--border)', paddingTop: 12, marginTop: 4 }}>
                <div className="nx-opts" style={{ marginTop: 0, paddingTop: 0, borderTop: 'none', gridTemplateColumns: '1fr 1fr' }}>
                  <div className="nx-field"><label>Role</label><select className="nx-input" value={editForm.role} onChange={e => setEditForm({ ...editForm, role: e.target.value })}>{ROLES.map(r => <option key={r}>{r}</option>)}</select></div>
                  <div className="nx-field"><label>Base URL</label><input className="nx-input" value={editForm.base_url} onChange={e => setEditForm({ ...editForm, base_url: e.target.value })} placeholder="https://…" /></div>
                </div>
                <button className="nx-btn primary" style={{ marginTop: 12 }} disabled={busy === `edit:${p.provider_id}`} onClick={() => saveEdit(p.provider_id)}>Save</button>
              </div>
            )}
          </div>
        );
      })}

      {/* Fallback chains (EP27) */}
      <div className="nx-secthead"><h3>Fallback chains</h3><button className="nx-btn primary" disabled={busy === 'chains'} onClick={saveChains}>{busy === 'chains' ? 'Saving…' : 'Save fallback'}</button></div>
      <div className="nx-note" style={{ marginBottom: 12 }}>Order the router tries within a tier when a call fails or escalates (comma-separated model ids). EP27.</div>
      {TIERS.map(t => (
        <div className="nx-field" key={t} style={{ marginBottom: 10 }}>
          <label><span className={`nx-tier ${t}`} style={{ marginRight: 8 }}>{t}</span></label>
          <input className="nx-input" value={(chains[t] || []).join(', ')} onChange={e => setChain(t, e.target.value)} placeholder="model-a, model-b, …" />
        </div>
      ))}
      <div className="nx-opts" style={{ marginTop: 6, paddingTop: 0, borderTop: 'none', gridTemplateColumns: '1fr 1fr' }}>
        <div className="nx-field"><label>Trigger</label><select className="nx-input" value={trigger.trigger} onChange={e => setTrigger({ ...trigger, trigger: e.target.value })}>{['error_or_timeout', 'error', 'timeout'].map(x => <option key={x}>{x}</option>)}</select></div>
        <div className="nx-field"><label>Retries</label><input className="nx-input" type="number" value={trigger.retries} onChange={e => setTrigger({ ...trigger, retries: e.target.value })} /></div>
      </div>

      {/* Health (EP25) */}
      <div className="nx-secthead"><h3>Health <span style={{ fontSize: '.7rem', fontWeight: 500, color: 'var(--text-3)' }}>· simulated (Phase 0)</span></h3></div>
      <div className="nx-grid">
        {(health?.providers || []).map(h => (
          <div className="nx-mcard" key={h.provider_id} style={{ cursor: 'default' }}>
            <div className="nx-mcard-h"><div className="nx-mcard-name">{h.name}</div><span className={`nx-status ${h.status === 'healthy' ? '' : 'muted'}`}>{h.status}</span></div>
            <div className="nx-mcard-row" style={{ marginTop: 12 }}>
              <span>uptime <b>{h.uptime_pct ?? '—'}%</b></span><span>latency <b>{h.avg_latency_ms ?? '—'}ms</b></span><span>errors <b>{h.error_rate_pct ?? '—'}%</b></span>
            </div>
            <div className="nx-mcard-row" style={{ color: 'var(--text-3)', marginTop: 6 }}>checked {h.last_check_label || '—'}</div>
          </div>
        ))}
      </div>

      <div className={`nx-toast ${toast ? 'show' : ''}`}>{toast}</div>
    </div>
  );
}

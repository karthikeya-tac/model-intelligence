import { useEffect, useState } from 'react';
import {
  allModels, getContextProfile, saveContextProfile,
  getCompaction, saveCompaction, getBudget, saveBudget, fitCheck,
} from '../api/modelIntelligenceApi';

const VERDICT = { fits: { c: 'var(--green-700)', bg: 'var(--green-100)' }, compact: { c: 'var(--bark-700)', bg: 'var(--gold-100)' }, overflow: { c: 'var(--red-600)', bg: 'var(--red-100)' }, unknown: { c: 'var(--text-3)', bg: 'var(--surface-2)' } };

export default function ContextPanel() {
  const models = allModels;
  const [modelId, setModelId] = useState(models[0]?.id || '');
  const [profile, setProfile] = useState(null);
  const [compaction, setCompaction] = useState(null);
  const [budget, setBudget] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [toast, setToast] = useState('');
  // fit-check
  const [fcPrompt, setFcPrompt] = useState('');
  const [fcModels, setFcModels] = useState(models.slice(0, 3).map(m => m.id));
  const [fcTokens, setFcTokens] = useState('');
  const [fcResults, setFcResults] = useState([]);
  const [fcLoading, setFcLoading] = useState(false);

  const flash = (m) => { setToast(m); setTimeout(() => setToast(''), 2600); };

  useEffect(() => {
    Promise.all([getCompaction(), getBudget()])
      .then(([c, b]) => { setCompaction(c); setBudget(b); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!modelId) return;
    let cancelled = false;
    getContextProfile(modelId).then(p => { if (!cancelled) setProfile(p); }).catch(() => { if (!cancelled) setProfile(null); });
    return () => { cancelled = true; };
  }, [modelId]);

  const saveProfile = async () => {
    setBusy('profile');
    try {
      await saveContextProfile(modelId, {
        native_window: Number(profile.native_window), effective_window: Number(profile.effective_window),
        compaction_floor_pct: Number(profile.compaction_floor_pct), memory_budget_tokens: Number(profile.memory_budget_tokens),
        context_budget_total: Number(profile.context_budget_total),
      });
      flash('Context profile saved (overlay)');
    } catch (e) { flash(e.message); } finally { setBusy(''); }
  };

  const saveComp = async () => {
    setBusy('comp');
    try { await saveCompaction({ thresholds: compaction.thresholds, summariser_model_id: compaction.summariser_model_id }); flash('Compaction saved'); }
    catch (e) { flash(e.message); } finally { setBusy(''); }
  };
  const saveBud = async () => {
    setBusy('budget');
    try { await saveBudget({ total: Number(budget.total), layers: budget.layers }); flash('Budget saved'); }
    catch (e) { flash(e.message); } finally { setBusy(''); }
  };

  const runFit = async () => {
    if (!fcPrompt.trim() || !fcModels.length) return;
    setFcLoading(true); setFcResults([]);
    try { setFcResults(await fitCheck(fcPrompt, fcModels, fcTokens)); }
    catch (e) { flash(e.message); } finally { setFcLoading(false); }
  };
  const toggleFc = (id) => setFcModels(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id]);

  if (loading) return <div className="nx-loading">Loading context settings…</div>;
  if (error) return <div className="nx-note warn">{error}</div>;

  return (
    <div>
      <div className="nx-note" style={{ marginBottom: 16 }}>Context profiles are <b>computed Phase-0 defaults</b> (the catalog has no context-profile data) — editable in the overlay, reset on reload.</div>

      {/* Context profile per model (EP29/30) */}
      <div className="nx-secthead"><h3>Context profile</h3>
        <select className="nx-input" style={{ maxWidth: 240 }} value={modelId} onChange={e => setModelId(e.target.value)}>
          {models.map(m => <option key={m.id} value={m.id}>{m.identity.display_name}</option>)}
        </select>
      </div>
      {profile ? (
        <div className="nx-card nx-pad">
          <div className="nx-opts" style={{ marginTop: 0, paddingTop: 0, borderTop: 'none', gridTemplateColumns: 'repeat(3,1fr)' }}>
            {[['native_window', 'Native window'], ['effective_window', 'Effective window'], ['context_budget_total', 'Budget total'], ['memory_budget_tokens', 'Memory budget'], ['compaction_floor_pct', 'Compaction floor %']].map(([k, l]) => (
              <div className="nx-field" key={k}><label>{l}</label><input className="nx-input" type="number" value={profile[k] ?? ''} onChange={e => setProfile({ ...profile, [k]: e.target.value })} /></div>
            ))}
          </div>
          <button className="nx-btn primary" style={{ marginTop: 14 }} disabled={busy === 'profile'} onClick={saveProfile}>{busy === 'profile' ? 'Saving…' : 'Save profile'}</button>
        </div>
      ) : <div className="nx-note">No profile for this model.</div>}

      {/* Fit-check (EP31) */}
      <div className="nx-secthead"><h3>Fit-check</h3></div>
      <div className="nx-note" style={{ marginBottom: 12 }}>Will a prompt + injected memory fit a model’s window, need compaction, or overflow? EP31.</div>
      <textarea className="nx-input" rows={2} style={{ marginBottom: 10 }} placeholder="Prompt to check…" value={fcPrompt} onChange={e => setFcPrompt(e.target.value)} />
      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginBottom: 10, flexWrap: 'wrap' }}>
        <div className="nx-field" style={{ width: 180 }}><label>Session tokens (optional)</label><input className="nx-input" type="number" value={fcTokens} onChange={e => setFcTokens(e.target.value)} placeholder="0" /></div>
        <button className="nx-btn primary" onClick={runFit} disabled={fcLoading || !fcPrompt.trim() || !fcModels.length}>{fcLoading ? 'Checking…' : 'Run fit-check'}</button>
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
        {models.map(m => <button key={m.id} className={`nx-pillbtn ${fcModels.includes(m.id) ? 'on' : ''}`} onClick={() => toggleFc(m.id)}>{m.identity.display_name}</button>)}
      </div>
      {fcResults.map(r => {
        const v = VERDICT[r.verdict] || VERDICT.unknown;
        return (
          <div className="nx-prov" key={r.model_id}>
            <div className="info"><div className="nm">{r.model_id}</div><div className="mt">{r.total_tokens != null ? `${r.total_tokens.toLocaleString()} tokens vs ${r.window?.toLocaleString()} window` : r.reason}</div></div>
            <span className="nx-status" style={{ background: v.bg, color: v.c }}>{r.verdict}</span>
          </div>
        );
      })}

      {/* Compaction (EP32) + Budget (EP33) */}
      <div className="nx-secthead"><h3>Compaction thresholds</h3><button className="nx-btn primary" disabled={busy === 'comp'} onClick={saveComp}>{busy === 'comp' ? 'Saving…' : 'Save'}</button></div>
      {compaction && (
        <div className="nx-card nx-pad">
          <div className="nx-opts" style={{ marginTop: 0, paddingTop: 0, borderTop: 'none', gridTemplateColumns: 'repeat(3,1fr)' }}>
            {['mask_pct', 'summarise_pct', 'emergency_pct'].map(k => (
              <div className="nx-field" key={k}><label>{k.replace('_pct', '')} %</label><input className="nx-input" type="number" value={compaction.thresholds[k]} onChange={e => setCompaction({ ...compaction, thresholds: { ...compaction.thresholds, [k]: Number(e.target.value) } })} /></div>
            ))}
          </div>
          <div className="nx-field" style={{ marginTop: 12 }}><label>Summariser model</label>
            <select className="nx-input" value={compaction.summariser_model_id} onChange={e => setCompaction({ ...compaction, summariser_model_id: e.target.value })}>
              {models.map(m => <option key={m.id} value={m.id}>{m.identity.display_name}</option>)}
            </select></div>
        </div>
      )}

      <div className="nx-secthead"><h3>Context budget</h3><button className="nx-btn primary" disabled={busy === 'budget'} onClick={saveBud}>{busy === 'budget' ? 'Saving…' : 'Save'}</button></div>
      {budget && (
        <div className="nx-card nx-pad">
          <div className="nx-field"><label>Total tokens</label><input className="nx-input" type="number" value={budget.total} onChange={e => setBudget({ ...budget, total: e.target.value })} /></div>
          <div className="nx-opts" style={{ marginTop: 12, paddingTop: 0, borderTop: 'none', gridTemplateColumns: `repeat(${Object.keys(budget.layers || {}).length || 1},1fr)` }}>
            {Object.entries(budget.layers || {}).map(([k, v]) => (
              <div className="nx-field" key={k}><label>{k}</label><input className="nx-input" type="number" value={v} onChange={e => setBudget({ ...budget, layers: { ...budget.layers, [k]: Number(e.target.value) } })} /></div>
            ))}
          </div>
        </div>
      )}

      <div className={`nx-toast ${toast ? 'show' : ''}`}>{toast}</div>
    </div>
  );
}

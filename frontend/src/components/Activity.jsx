import { useEffect, useState } from 'react';
import { getRoutingStats, getRegistrySource, reloadRegistry, getAudit } from '../api/modelIntelligenceApi';

const rel = (iso) => {
  if (!iso) return '—';
  const t = Date.parse(iso); if (Number.isNaN(t)) return iso;
  const m = Math.max(0, Math.round((Date.now() - t) / 60000));
  if (m < 1) return 'just now'; if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60); return h < 24 ? `${h}h ago` : `${Math.round(h / 24)}d ago`;
};

export default function Activity() {
  const [stats, setStats] = useState(null);
  const [source, setSource] = useState(null);
  const [audit, setAudit] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reloading, setReloading] = useState(false);
  const [toast, setToast] = useState('');

  const load = () => {
    setLoading(true);
    Promise.all([getRoutingStats(), getRegistrySource(), getAudit()])
      .then(([s, src, a]) => { setStats(s); setSource(src); setAudit(a); setError(''); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const reload = async () => {
    setReloading(true);
    try { const r = await reloadRegistry(); setToast(`Reloaded · ${Object.entries(r.counts).map(([k, v]) => `${v} ${k}`).join(', ')}`); setTimeout(() => setToast(''), 3000); load(); }
    catch (e) { setToast(e.message); setTimeout(() => setToast(''), 3000); }
    finally { setReloading(false); }
  };

  if (loading) return <div className="nx-loading">Loading activity…</div>;
  if (error) return <div className="nx-note warn">{error}</div>;

  const split = [['fast', stats.tier_fast_pct], ['standard', stats.tier_standard_pct], ['powerful', stats.tier_powerful_pct]];

  return (
    <div>
      {/* Registry source + reload (EP35 / EP34) */}
      <div className="nx-card nx-pad" style={{ marginBottom: 18, display: 'flex', alignItems: 'center', gap: 14 }}>
        <div style={{ flex: 1 }}>
          <div className="nx-mcard-name">Registry</div>
          <div className="nx-mcard-prov">mode <b>{source?.mode}</b> · version <b>{source?.version || '—'}</b> · loaded {rel(source?.last_loaded)}</div>
        </div>
        <button className="nx-btn" onClick={reload} disabled={reloading}>{reloading ? 'Reloading…' : '↻ Reload registry'}</button>
      </div>

      {/* Routing stats (EP16) */}
      <div className="nx-secthead"><h3>Routing stats <span style={{ fontSize: '.7rem', fontWeight: 500, color: 'var(--text-3)' }}>· simulated telemetry (Phase 0)</span></h3></div>
      <div className="nx-kv" style={{ gridTemplateColumns: 'repeat(4,1fr)' }}>
        <div><div className="k">Decisions</div><div className="v">{stats.routing_decisions?.toLocaleString?.() ?? stats.routing_decisions}</div></div>
        <div><div className="k">Active models</div><div className="v">{stats.active_models}</div></div>
        <div><div className="k">Active rules</div><div className="v">{stats.active_rules}</div></div>
        <div><div className="k">Optimal match</div><div className="v">{stats.optimal_match_pct}%</div></div>
        <div><div className="k">Escalated</div><div className="v">{stats.escalated_pct}%</div></div>
      </div>
      <div className="nx-sublabel">Tier split</div>
      <div className="nx-bars" style={{ height: 14, borderRadius: 7, overflow: 'hidden', display: 'flex' }}>
        {split.map(([t, v]) => <i key={t} title={`${t} ${v}%`} className={t === 'standard' ? 'c' : t === 'fast' ? 'l' : ''} style={{ width: `${v}%`, height: 14, borderRadius: 0 }} />)}
      </div>
      <div style={{ display: 'flex', gap: 14, marginTop: 8, fontSize: '.74rem', color: 'var(--text-2)' }}>
        {split.map(([t, v]) => <span key={t}><span className={`nx-tier ${t}`} style={{ padding: '1px 7px' }}>{t}</span> {v}%</span>)}
      </div>

      {/* Audit log (EP28) */}
      <div className="nx-secthead"><h3>Audit log <span style={{ fontSize: '.7rem', fontWeight: 500, color: 'var(--text-3)' }}>· in-memory writes since boot</span></h3></div>
      {audit.length === 0
        ? <div className="nx-note">No writes yet. Edit an intent, model config, provider, or setting and it shows here (EP28).</div>
        : audit.map(e => (
          <div className="nx-prov" key={e.id} style={{ alignItems: 'flex-start' }}>
            <div className="info">
              <div className="nm" style={{ fontSize: '.82rem' }}><span className="nx-rtype">{e.entity}</span> {e.entity_id}</div>
              <div className="mt">by {e.actor} · {rel(e.ts)}</div>
            </div>
          </div>
        ))}

      <div className={`nx-toast ${toast ? 'show' : ''}`}>{toast}</div>
    </div>
  );
}

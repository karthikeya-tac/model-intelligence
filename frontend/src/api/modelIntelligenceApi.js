// Niha Model Intelligence — API client.
// Talks to the FastAPI backend (canonical /api/v1 spec) and ADAPTS each response
// into the shapes the components consume. No mock data — everything is live.

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// A production build with no VITE_API_BASE_URL silently talks to localhost — warn loudly so a
// misconfigured deploy is obvious in the console instead of "nothing loads".
if (import.meta.env.PROD && !import.meta.env.VITE_API_BASE_URL) {
  // eslint-disable-next-line no-console
  console.warn('[niha] VITE_API_BASE_URL is not set — falling back to http://localhost:8000. Set it for production.');
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = body?.detail || body?.message || message;
    } catch { /* non-JSON */ }
    throw new Error(message);
  }
  if (response.status === 204) return null;
  return response.json();
}

// --------------------------------------------------------------------------- //
//  small formatting helpers
// --------------------------------------------------------------------------- //
const PROVIDER_NAME = { anthropic: 'Anthropic', openai: 'OpenAI', google: 'Google', xai: 'xAI', ollama: 'Ollama' };
const PROVIDER_ICON = { anthropic: '🟢', openai: '🔵', google: '🔴', xai: '⚫', ollama: '🟣', custom: '⚪' };
const titleCase = (s) => (s ? String(s).charAt(0).toUpperCase() + String(s).slice(1) : s);
const providerName = (slug) => PROVIDER_NAME[slug] || titleCase(slug);
const providerIcon = (kind) => PROVIDER_ICON[kind] || '⚪';
const fmtInt = (n) => (n == null ? '—' : Number(n).toLocaleString('en-US'));
const prettify = (k) => String(k).replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
const money = (n) => (n == null ? '—' : `${Number(n).toFixed(2)} / 1M tokens`);

function scoreLabel(v) {
  if (v >= 90) return 'Excellent';
  if (v >= 80) return 'Very good';
  if (v >= 70) return 'Good';
  if (v >= 50) return 'Fair';
  if (v > 0) return 'Limited';
  return 'N/A';
}

function relTime(iso) {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const mins = Math.max(0, Math.round((Date.now() - t) / 60000));
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

function hoursLeft(iso) {
  if (!iso) return null;
  const ms = Date.parse(iso) - Date.now();
  if (Number.isNaN(ms) || ms <= 0) return 'expired';
  const h = Math.round(ms / 3600000);
  return h < 48 ? `${h}h left` : `${Math.round(h / 24)}d left`;
}

function scopeLabel(scope) {
  if (!scope) return 'All agents';
  const agents = scope.agents || [];
  const ws = scope.workspaces || [];
  if (agents.length && !agents.includes('all')) return agents.join(', ');
  if (ws.length && !ws.includes('all')) return ws.join(', ');
  return 'All agents';
}

function describeRule(r) {
  const a = r.action || {};
  if (a.route_to_tier) return `Route to ${a.route_to_tier} tier`;
  if (a.min_tier) return `Boost to at least ${a.min_tier}`;
  if (a.max_tier) return `Limit to ${a.max_tier} or below`;
  if (a.redirect_to_model) return `Redirect to ${a.redirect_to_model}`;
  if (a.boost_to_long_context) return 'Boost to a long-context model';
  if (a.max_cost_per_request_usd != null) return `Cap cost at $${a.max_cost_per_request_usd}/request`;
  return r.match_by ? `Match by ${r.match_by}` : 'Routing rule';
}

// --------------------------------------------------------------------------- //
//  adapters: backend shape -> component shape
// --------------------------------------------------------------------------- //
function adaptModel(b) {
  const cap = b.capability || {};
  const cls = b.classification || {};
  const pr = b.pricing || {};
  const scores = (b.benchmarks && b.benchmarks.capability_scores) || {};
  const standard = (b.benchmarks && b.benchmarks.standard) || {};
  return {
    id: b.id,
    identity: {
      display_name: b.identity?.display_name || b.id,
      api_model_name: b.identity?.api_model_name || b.id,
      description: b.identity?.description || '',
      provider: providerName(b.provider),
      release_date: b.identity?.release_date || '',
    },
    capability: {
      context_window: fmtInt(cap.context_window),
      max_output_tokens: fmtInt(cap.max_output_tokens),
      input_modalities: (cap.input_modalities || []).map(titleCase).join(', ') || 'Text',
      output_modalities: (cap.output_modalities || []).map(titleCase).join(', ') || 'Text',
      reasoning_level: cap.reasoning_level || '—',
      supports_tools: cap.supports_tools ? 'Yes' : 'No',
      supports_streaming: cap.supports_streaming ? 'Yes' : 'No',
      knowledge_cutoff: cap.knowledge_cutoff || '—',
    },
    pricing: { cost: 'Per-token', input_price: money(pr.input), output_price: money(pr.output) },
    classify: {
      tier: titleCase(cls.tier),
      status: titleCase(cls.status),
      latency_class: cls.latency_class || '—',
    },
    capability_scores: Object.entries(scores).map(([k, v]) => ({ capability: prettify(k), score: v, label: scoreLabel(v) })),
    benchmarks: Object.entries(standard).map(([k, v]) => ({ benchmark: prettify(k), value: v, source: 'catalog', measured_at: '' })),
    // raw backend fields kept for config/pricing/specs
    _raw: b,
    _tier: cls.tier,
    _provider: b.provider,
    pricing_in: pr.input,
    pricing_out: pr.output,
    control_params: [],   // backend has no per-param list in Phase 0 (config modal degrades gracefully)
  };
}

function adaptRule(b) {
  return {
    rule_id: b.id || b.rule_id,
    name: b.name,
    type: b.type,
    match_by: b.match_by,
    description: b.description || describeRule(b),
    scope_label: scopeLabel(b.scope),
    priority: b.priority,
    status: b.status,
    expires_in_label: b.expires_at ? hoursLeft(b.expires_at) : undefined,
    stats: b.stats || { matches: 0 },
    _raw: b,
  };
}

// --------------------------------------------------------------------------- //
//  shared full-model cache (read by Providers / TestWorkbench / Modals)
// --------------------------------------------------------------------------- //
export const allModels = [];   // mutated in place so importers always see the latest

export async function loadAllModels() {
  const data = await request('/api/v1/models?limit=500');
  const list = (data.models || []).map(adaptModel);
  allModels.length = 0;
  allModels.push(...list);
  return list;
}

// --------------------------------------------------------------------------- //
//  registry
// --------------------------------------------------------------------------- //
export async function getRegistrySource() {
  return request('/api/v1/registry/source');
}

export async function reloadRegistry() {
  const res = await request('/api/v1/registry/reload', { method: 'POST' });
  await loadAllModels();
  return res;
}

// --------------------------------------------------------------------------- //
//  models
// --------------------------------------------------------------------------- //
export async function getModels(params = {}) {
  const query = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) query.set(k, v);
  query.set('limit', '500');
  const data = await request(`/api/v1/models?${query.toString()}`);
  return (data.models || []).map(adaptModel);
}

export async function getModelDetail(modelId) {
  return adaptModel(await request(`/api/v1/models/${encodeURIComponent(modelId)}`));
}

export async function getModelStats(modelId) {
  const u = await request(`/api/v1/models/${encodeURIComponent(modelId)}/usage`);
  return { requests: u.requests, usage_pct: u.pct, cost_usd: u.cost_usd, avg_latency_ms: u.avg_latency_ms };
}

// EP5 — real fields only. capabilities + standard are catalog-grounded;
// avg_latency_ms / requests are backend telemetry (simulated in Phase 0).
// NO fabricated p95/p99/error-rate (those were invented client-side; removed).
export async function getModelBenchmarks(modelId) {
  const b = await request(`/api/v1/models/${encodeURIComponent(modelId)}/benchmarks`);
  const caps = Object.values(b.capabilities || {});
  return {
    capabilities: b.capabilities || {},
    standard: b.standard || {},
    avg_latency_ms: b.performance?.avg_latency_ms ?? null,
    requests: b.performance?.requests ?? 0,
    value_score: caps.length ? Math.round(caps.reduce((a, c) => a + c, 0) / caps.length) : null,
    pricing: b.pricing || {},
  };
}

export async function getModelPricing(modelId) {
  const m = await request(`/api/v1/models/${encodeURIComponent(modelId)}`);
  const pr = m.pricing || {};
  return {
    input: pr.input ?? 0, output: pr.output ?? 0,
    cache_write: pr.cache_write ?? null, cache_read: pr.cache_read ?? pr.cached_input ?? null,
    unit: '1M tokens',
  };
}

function saveConfig(modelId, body) {
  return request(`/api/v1/models/${encodeURIComponent(modelId)}/config`, { method: 'PATCH', body: JSON.stringify(body) });
}
export const saveModelConfig = (id, config) => saveConfig(id, config);
export const saveModelSettings = (id, settings) => saveConfig(id, settings);
export const saveThinkingConfig = (id, limits) => saveConfig(id, { thinking_budget_by_trust: limits });
export const saveTrustConfig = (id, limits) => saveConfig(id, { max_output_by_trust: limits });

// --------------------------------------------------------------------------- //
//  routing + telemetry
// --------------------------------------------------------------------------- //
export async function getRoutingStats() {
  const s = await request('/api/v1/routing/stats');
  const t = s.tier_split || {};
  return {
    active_models: s.active_models,
    tier_fast_pct: t.fast ?? 0,
    tier_standard_pct: t.standard ?? 0,
    tier_powerful_pct: t.powerful ?? 0,
    active_rules: s.active_rules,
    optimal_match_pct: s.optimal_match_pct,
    routing_decisions: s.decisions,
    escalated_pct: s.escalated_pct,
  };
}

export async function routeRequest(body) {
  return request('/api/v1/route', { method: 'POST', body: JSON.stringify(body) });
}

// The Console: one call → chosen model + all its info + estimate + (live output if a key is set)
export async function consoleAsk(body) {
  return request('/api/v1/console/ask', { method: 'POST', body: JSON.stringify(body) });
}

// fit badges are computed client-side from compare results (no backend call needed)
export async function getFitBadges(prompt, results) {
  const maxCost = Math.max(...results.map((x) => x.cost_usd));
  const minCost = Math.min(...results.map((x) => x.cost_usd));
  const maxValue = Math.max(...results.map((x) => x.value_score));
  return results.map((r) => {
    let fit;
    if (r.value_score === maxValue && r.cost_usd === minCost) fit = 'sweet-spot';
    else if (r.value_score < (maxValue * 0.7)) fit = 'underpowered';
    else if (r.cost_usd === maxCost && r.value_score < maxValue) fit = 'overkill';
    else if (r.value_score >= (maxValue * 0.92)) fit = 'good-fit';
    else fit = 'acceptable';
    return { model_id: r.model_id, fit };
  });
}

// --------------------------------------------------------------------------- //
//  intents
// --------------------------------------------------------------------------- //
export async function getIntents() {
  const data = await request('/api/v1/intents');
  return (data.intents || []).map((i) => ({
    id: i.intent_id, category: i.category, name: i.name,
    description: i.description, tier: i.default_tier, min_tier: i.min_tier,
  }));
}

export async function saveIntentTiers(updates) {
  // backend is per-intent PATCH; fan out the bulk save
  await Promise.all(updates.map((u) =>
    request(`/api/v1/intents/${encodeURIComponent(u.id)}`, {
      method: 'PATCH',
      body: JSON.stringify({ default_tier: u.tier, min_tier: u.min_tier }),
    })));
  return { saved: true, updated: updates.length };
}

// --------------------------------------------------------------------------- //
//  rules
// --------------------------------------------------------------------------- //
export async function getRules(params = {}) {
  const query = new URLSearchParams();
  if (params.status) query.set('status', params.status);
  const data = await request(`/api/v1/rules${query.toString() ? `?${query}` : ''}`);
  return (data.rules || []).map(adaptRule);
}

export async function createRule(rule) {
  const res = await request('/api/v1/rules', { method: 'POST', body: JSON.stringify(rule) });
  return res.rule ? adaptRule(res.rule) : res;
}

export async function updateRule(ruleId, patch) {
  return request(`/api/v1/rules/${encodeURIComponent(ruleId)}`, { method: 'PATCH', body: JSON.stringify(patch) });
}

export async function deleteRule(ruleId) {
  await request(`/api/v1/rules/${encodeURIComponent(ruleId)}`, { method: 'DELETE' });
  return { deleted: true, rule_id: ruleId };
}

export async function simulateRule(ruleForm) {
  return request('/api/v1/rules/simulate', { method: 'POST', body: JSON.stringify({ rule_draft: ruleForm }) });
}

// --------------------------------------------------------------------------- //
//  test workbench
// --------------------------------------------------------------------------- //
export async function runSingleTest(modelId, prompt) {
  return request('/api/v1/test/single', { method: 'POST', body: JSON.stringify({ model_id: modelId, prompt }) });
}

export async function runComparison(prompt, modelIds) {
  const res = await request('/api/v1/test/compare', { method: 'POST', body: JSON.stringify({ prompt, model_ids: modelIds }) });
  return (res.results || []).map((r) => ({
    model_id: r.model_id, latency_ms: r.latency_ms, cost_usd: r.cost_usd,
    value_score: r.value_score, output: r.output,
  }));
}

// --------------------------------------------------------------------------- //
//  providers
// --------------------------------------------------------------------------- //
export async function getProviders() {
  const data = await request('/api/v1/providers');
  return (data.providers || []).map((p) => ({
    provider_id: p.provider_id,
    name: providerName(p.kind) + (p.kind === 'openai' ? '' : ''),
    icon: providerIcon(p.kind),
    status: p.status === 'connected' ? 'connected' : 'disconnected',
    role: titleCase(p.role),
    models_summary: `${p.models_count} models`,
    avg_latency_ms: p.avg_latency_ms,
    uptime_pct: p.uptime,
    api_key_hint: p.api_key_hint,
  }));
}

export async function getProvider(providerId) {
  const p = await request(`/api/v1/providers/${encodeURIComponent(providerId)}`);
  return {
    provider_id: p.provider_id, name: providerName(p.kind), kind: p.kind,
    role: p.role, api_key_hint: p.api_key_hint, base_url: p.base_url || '',
    rate_limit_rpm: p.rate_limit_rpm, monthly_budget_usd: null,
    enabled: p.status === 'connected',
  };
}

export async function saveProvider(providerId, patch) {
  return request(`/api/v1/providers/${encodeURIComponent(providerId)}`, { method: 'PATCH', body: JSON.stringify(patch) });
}

export async function testProviderKey(kind /* apiKey, baseUrl */) {
  try {
    const r = await request(`/api/v1/providers/${encodeURIComponent(kind)}/test`, { method: 'POST' });
    return { ok: r.ok, latency_ms: 0, models_count: (r.models_available || []).length };
  } catch {
    return { ok: false, latency_ms: 0, models_count: 0 };
  }
}

export async function discoverProviderModels(kind /* apiKey, baseUrl */) {
  try {
    const data = await request(`/api/v1/providers/${encodeURIComponent(kind)}/models`);
    return (data.models || []).map((m) => ({
      ref: m.model_id, name: m.display_name, tier: titleCase(m.tier),
      window: fmtInt(m.context_window),
    }));
  } catch {
    return [];
  }
}

export async function connectProvider(kind, apiKey, baseUrl) {
  return request('/api/v1/providers', { method: 'POST', body: JSON.stringify({ kind, api_key: apiKey, base_url: baseUrl }) });
}

export async function enableModels(providerId, modelRefs) {
  // backend models are file-backed in Phase 0; nothing to enable server-side
  return { enabled: modelRefs.length };
}

export async function getProviderHealth() {
  const data = await request('/api/v1/providers/health');
  return {
    providers: (data.providers || []).map((p) => ({
      provider_id: p.provider_id, name: p.name,
      status: p.status === 'connected' ? 'healthy' : 'disconnected',
      uptime_pct: p.uptime_30d, avg_latency_ms: p.avg_latency_ms,
      error_rate_pct: p.error_rate, last_check_label: relTime(p.last_check),
    })),
    fallback_uses_30d: data.fallback_uses_30d || 0,
    fallback_summary: 'fallback chain configured',
  };
}

// --------------------------------------------------------------------------- //
//  settings (architect mode + fallback) — backend /settings/*
// --------------------------------------------------------------------------- //
export async function getArchitectConfig() {
  const s = await request('/api/v1/settings/architect-mode');
  return { enabled: s.enabled, uses_this_month: s.uses_this_month || 0, savings_usd: s.savings_usd || 0 };
}

export async function saveArchitectConfig(patch) {
  const body = typeof patch === 'boolean' ? { enabled: patch } : patch;
  return request('/api/v1/settings/architect-mode', { method: 'PATCH', body: JSON.stringify(body) });
}

export async function getFallbackChains() {
  const s = await request('/api/v1/settings/fallback');
  return s.chains || { fast: [], standard: [], powerful: [] };
}

export async function saveFallbackChains(chains) {
  await request('/api/v1/settings/fallback', { method: 'PATCH', body: JSON.stringify({ chains }) });
  return { saved: true };
}

export async function getTriggerConfig() {
  const s = await request('/api/v1/settings/fallback');
  return { trigger: s.trigger || 'error_or_timeout', retries: String(s.retries ?? 2), notify: s.notify ? 'threshold' : 'none' };
}

export async function saveTriggerConfig(config) {
  await request('/api/v1/settings/fallback', {
    method: 'PATCH',
    body: JSON.stringify({ trigger: config.trigger, retries: Number(config.retries), notify: config.notify !== 'none' }),
  });
  return { saved: true };
}

// --------------------------------------------------------------------------- //
//  newly-wired endpoints (close the audit gap) — all backend-driven
// --------------------------------------------------------------------------- //

// EP3 — register a model config in the overlay (Phase-0; catalog stays file-backed)
export async function createModel(body) {
  return request('/api/v1/models', { method: 'POST', body: JSON.stringify(body) });
}

// EP6 — live usage (simulated telemetry in Phase 0)
export async function getModelUsage(modelId) {
  return request(`/api/v1/models/${encodeURIComponent(modelId)}/usage`);
}

// EP9 — standalone intent classifier (the real Level-1 engine)
export async function classifyPrompt(prompt) {
  return request('/api/v1/intents/classify', { method: 'POST', body: JSON.stringify({ prompt }) });
}

// EP29 / EP30 — context profile (computed Phase-0 defaults, not catalog data)
export async function getContextProfile(modelId) {
  return request(`/api/v1/models/${encodeURIComponent(modelId)}/context-profile`);
}
export async function saveContextProfile(modelId, patch) {
  return request(`/api/v1/models/${encodeURIComponent(modelId)}/context-profile`, { method: 'PATCH', body: JSON.stringify(patch) });
}

// EP31 — context fit-check
export async function fitCheck(prompt, modelIds, sessionTokens) {
  const body = { prompt, model_ids: modelIds };
  if (sessionTokens) body.session_tokens = Number(sessionTokens);
  const data = await request('/api/v1/context/fit-check', { method: 'POST', body: JSON.stringify(body) });
  return data.results || [];
}

// EP32 — compaction settings
export async function getCompaction() { return request('/api/v1/context/compaction'); }
export async function saveCompaction(patch) {
  return request('/api/v1/context/compaction', { method: 'PATCH', body: JSON.stringify(patch) });
}

// EP33 — context budget
export async function getBudget() { return request('/api/v1/context/budget'); }
export async function saveBudget(patch) {
  return request('/api/v1/context/budget', { method: 'PATCH', body: JSON.stringify(patch) });
}

// EP28 — audit log
export async function getAudit(params = {}) {
  const q = new URLSearchParams();
  if (params.entity) q.set('entity', params.entity);
  const data = await request(`/api/v1/audit${q.toString() ? `?${q}` : ''}`);
  return data.entries || [];
}

// EP24 — delete a provider (force when it still has models)
export async function deleteProvider(providerId, force = false) {
  await request(`/api/v1/providers/${encodeURIComponent(providerId)}${force ? '?force=true' : ''}`, { method: 'DELETE' });
  return { deleted: true };
}

// EP21 — connectivity test (raw: configured? + which catalog models it backs)
export async function testProvider(providerId) {
  return request(`/api/v1/providers/${encodeURIComponent(providerId)}/test`, { method: 'POST' });
}

// meta — health + api info (for the header status)
export async function getHealth() { return request('/health'); }
export async function getApiInfo() { return request('/'); }

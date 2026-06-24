# Niha Model Intelligence — Backend

A self-contained **FastAPI** service that decides **which AI model should answer a request**,
and optionally runs it. It implements the spec's **35 endpoints** (43 routes once you count
GET/PATCH pairs + the console + meta) on top of a **hybrid 2-layer router**.

> **Phase 0 = config-as-code, no database.** Six YAML files are loaded at boot into an
> immutable snapshot. Writes go to an **in-memory overlay** (not saved to disk); `reload`
> re-reads the files. Everything maps cleanly to Phase-1 Postgres tables later.

---

## The big idea (in plain words)

You send a prompt. The backend:

1. **Level 1 — what kind of work is this, and how hard?** Classify the prompt into the top *intents*
   (embedding-first via MiniLM, keyword fallback), measure a **difficulty** score from the query text,
   and combine it with the intent's `complexity` to choose a **tier** (`fast`/`standard`/`powerful`).
   Then **rules** can override the tier, a `min_tier` floor applies, and a low-confidence query is
   **escalated** to a stronger tier. (So the *same* intent routes harder questions to higher tiers.)
2. **Level 2 — which model in that tier is best?** Score every model on a **multi-dimension capability
   fit** — quality = the *need-vector* (fused from the top-k intents) · the model's real
   `capability_scores`. Quality-first; cost/latency only break near-ties. Pick the winner + a **failover** order.
3. **Answer it.** Estimate cost/latency (always), and if a provider API key is set, actually
   call that provider's nearest real model and stream the text back.

```
prompt ─▶ [L1: classify → intent → tier → rules] ─▶ [L2: score models → pick + failover] ─▶ estimate (+ live answer)
```

---

## Run

```bash
cd FullWebsite/backend
pip install -r requirements.txt
/Users/.../.venv/bin/uvicorn app.main:app --reload --port 8000   # or just: uvicorn app.main:app --port 8000
# open http://localhost:8000/docs   (interactive API)
```

Optional env (see `.env.example`):

| Var | Default | Meaning |
|---|---|---|
| `REGISTRY_MODE` | `file` | `file` or `db`. Only flips a UI write-gate label — Phase 0 has no real DB. |
| `SEMANTIC` | `1` | `1` = embedding classifier (default; needs `sentence-transformers`). `0` = keyword-only. |
| `CORS_ORIGINS` | `*` | Allowed front-end origins. |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` | unset | If set, the console returns **live** output via that provider's real stand-in model. |

---

## Folder map — what each file does

```
app/
  main.py            FastAPI app: CORS, request-id/timing middleware, lifespan
                     (build Store + Router + Telemetry ONCE at boot), mounts /api/v1/*, /health, /
  config.py          Settings (paths, REGISTRY_MODE, SEMANTIC, CORS) + reads backend/.env
  deps.py            Dependency-injection providers: get_store / get_router / get_telemetry
  errors.py          One error shape ({detail,...}); maps RegistryError → 4xx; not_found() helper

  registry/          ── loads + validates the YAML into typed objects ──
    loader.py        Reads the 6 YAMLs, cross-checks references, fails fast on bad data
    schema.py        Pydantic models (Model, Provider, Intent, Rule…) — extra keys forbidden
    enums.py         Allowed values: tier, role, status, latency_class, sampling…
    errors.py        RegistryError (with file + line for boot failures)

  store/             ── the data source abstraction (Phase-0 file → Phase-1 db is one swap) ──
    base.py          Store interface (read snapshot, write overlay, audit, reload)
    file_store.py    Phase-0 impl: immutable snapshot + in-memory overlay + audit log + atomic reload

  routing/           ── the brain ──
    engine.py        RouterService: L1 (classify + difficulty→tier + rules + escalation) → L2 pick.
    classifier.py    embedding-first intent classifier (MiniLM, softmax top-k) + keyword fallback
    features.py      deterministic query features → difficulty score (0..1)
    difficulty.py    difficulty × intent.complexity → base tier (raise-only)
    selector.py      ScoringSelector (Level 2): multi-dimension capability-vector fit + failover ordering
    sim.py           Deterministic cost/latency/tokens/value_score from catalog data (no network)
    execute.py       Real provider calls (urllib) via a STANDIN map — catalog names are future/
                     fictional, so it calls each provider's nearest REAL model. No key → skipped.
    telemetry.py     In-memory routing-decision log + usage rollups + seeded history (dashboards)

  services/
    secrets.py       Resolves ${ENV_VAR} refs at request time; never returns a key value, only a hint
    health.py        Provider health (configured? + synthetic uptime/latency — Phase 0)

  schemas/api.py     Pydantic request/response bodies for every endpoint
  api/v1/            ── one file per resource (the HTTP layer) ──
    _serial.py       Shared "view" builders (model_view, provider_view, intent_view)
    console.py       POST /console/ask — the front-end's one-shot: decide + estimate + live answer
    models.py        EP1–6, EP29–30  (list/detail/create/config/benchmarks/usage/context-profile)
    intents.py       EP7–9           (list / patch tier / classify)
    rules.py         EP10–14         (list/create/patch/delete/simulate)
    routing.py       EP15–16         (route / routing stats)
    test.py          EP17–18         (compare / single — simulated)
    providers.py     EP19–25         (list/create/get/patch/delete/test/models/health)
    settings.py      EP26–28         (architect-mode / fallback / audit)
    context.py       EP31–33         (fit-check / compaction / budget)
    registry_admin.py EP34–35        (reload / source)

config_data/         ── the single source of truth (Phase 0) ──
    models.yaml      29 models (5 Claude · 17 GPT · 7 Gemini): identity, pricing, capability, controls, benchmarks
    providers.yaml   3 providers (anthropic/openai/google): api, auth (${ENV} ref), param profile
    intents.yaml     19 intents in 6 categories, each with keywords + default/min tier
    rules.yaml       9 routing rules (route/boost/limit/redirect/cost_cap/timed)
    routes.yaml      Utterance examples for the semantic classifier (SEMANTIC=1)
    selection.yaml   routing policy: difficulty weights, complexity→tier map, classifier/escalation
                     thresholds, intent→capability-dimension blends, tie epsilon

requirements.txt     fastapi, uvicorn, pydantic v2, pydantic-settings, pyyaml, numpy (sentence-transformers optional)
```

> `_ux_tmp/` is a cloned design-reference dump (not part of the running app — safe to delete).

---

## Endpoints (prefix `/api/v1`)

| Group | Routes |
|---|---|
| **console** | `POST /console/ask` — decide a model + estimate + live answer (what the UI calls) |
| **models** | `GET /models` · `GET/POST /models` · `PATCH /models/{id}/config` · `GET /models/{id}/benchmarks\|usage` · `GET/PATCH /models/{id}/context-profile` |
| **intents** | `GET /intents` · `PATCH /intents/{id}` · `POST /intents/classify` |
| **rules** | `GET /rules` · `POST /rules` · `PATCH /rules/{id}` · `DELETE /rules/{id}` · `POST /rules/simulate` |
| **routing** | `POST /route` · `GET /routing/stats` |
| **test** | `POST /test/single` · `POST /test/compare` |
| **providers** | `GET/POST /providers` · `GET/PATCH/DELETE /providers/{id}` · `POST /providers/{id}/test` · `GET /providers/{id}/models` · `GET /providers/health` |
| **settings** | `GET/PATCH /settings/architect-mode` · `GET/PATCH /settings/fallback` · `GET /audit` |
| **context** | `POST /context/fit-check` · `GET/PATCH /context/compaction` · `GET/PATCH /context/budget` |
| **registry** | `POST /registry/reload` · `GET /registry/source` |
| **meta** | `GET /health` · `GET /` |

---

## Quick checks (copy-paste)

```bash
curl localhost:8000/health
curl "localhost:8000/api/v1/models?tier=fast"

# the 2-layer router in action
curl -X POST localhost:8000/api/v1/console/ask -H 'content-type: application/json' \
  -d '{"prompt":"write a function to dedupe a list"}'
# → code_generation → standard → claude-sonnet-4-6 (highest capability fit in tier)

curl -X POST localhost:8000/api/v1/console/ask -H 'content-type: application/json' \
  -d '{"prompt":"design a fault-tolerant payment architecture"}'
# → architecture_design → powerful → claude-opus-4-8 (rule architecture_to_powerful fired)

# writes mutate the overlay; audit records them; reload resets to disk
curl -X PATCH localhost:8000/api/v1/intents/code_generation -H 'content-type: application/json' -d '{"default_tier":"standard"}'
curl localhost:8000/api/v1/audit
curl -X POST localhost:8000/api/v1/registry/reload
```

---

## Things worth knowing

- **Atomic reload (EP34):** a bad YAML keeps the *old* config and returns an error — it never
  leaves the service in a broken state.
- **Telemetry is simulated** (in-memory + seeded) in Phase 0, so `/routing/stats`,
  `/models/{id}/usage`, and provider health are populated but not real traffic.
- **Catalog model names are future/fictional** (e.g. "GPT-5.5"), so live calls use a STANDIN
  map in `execute.py` to the provider's nearest real model (labeled "live via …").
- **Secrets** are only `${ENV_VAR}` references; the API returns a configured/unset hint, never a value.

## Phase-0 constraints (read before deploying)

These are **deliberate prototype choices**, with Phase-1 seams already in place. They're called
out here (and guarded in code) so they're not silent surprises:

- **Unauthenticated / single-tenant.** No auth on any endpoint — including writes and
  `/registry/reload`. Do **not** expose this to the internet. Phase-1 adds Bearer + role checks on
  mutations (the `X-Org`/`Bearer` headers are already accepted, just not enforced).
- **Single worker only.** All mutable state (overlay, telemetry, audit) lives in-memory **per
  process**, so run with **one** worker. Multiple workers would each hold a divergent copy; the app
  logs a warning at startup if it detects `WEB_CONCURRENCY`/`UVICORN_WORKERS > 1`. Phase-1's shared
  DB store removes this limit.
- **Non-persistent.** Writes reset on restart or `reload`; the audit log is in-memory since boot.
- **Simulated telemetry/health.** `/routing/stats`, `/models/{id}/usage`, and provider health are
  seeded/simulated, clearly labeled as such in the UI.
- **Live output uses stand-in models.** Catalog names are future/fictional; with a key set, calls go
  to the provider's nearest real model (`execute.py`). Timeout is `NIHA_EXEC_TIMEOUT` (default 20s).

## Out of scope (Phase 1)
Postgres + Alembic, Key Vault + Managed Identity, RLS, real (non-standin) provider calls,
persistent telemetry, scheduled health probes, auth enforcement, multi-worker/horizontal scaling.

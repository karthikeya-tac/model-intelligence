# Niha — Model Intelligence

**Niha is a model-routing platform.** This app is its *Model Intelligence* layer: given a
prompt, it decides **which AI model should answer**, explains **why**, and (if a provider key
is set) **runs it** — all driven by a registry of models, intents, rules and providers kept as
config-as-code.

It has two halves that talk over one HTTP API:

```
┌─────────────────────────┐         /api/v1/*          ┌──────────────────────────────┐
│  frontend  (React+Vite)  │  ───────────────────────▶ │  backend  (FastAPI)           │
│  :5173                    │  ◀─────────────────────── │  :8000                        │
│  Console + Configure      │      JSON over HTTP        │  2-layer router + registry    │
└─────────────────────────┘                            └──────────────┬───────────────┘
                                                                       │ loads at boot
                                                          ┌────────────▼───────────────┐
                                                          │  config_data/*.yaml          │
                                                          │  models · providers · intents│
                                                          │  rules · routes · selection   │
                                                          │  (the single source of truth) │
                                                          └──────────────────────────────┘
```

> 📐 See **[niha-architecture.drawio](niha-architecture.drawio)** for the full visual:
> file structure, the request data-flow, and every endpoint group.

---

## What it does, end to end

A prompt travels through **two layers**:

1. **Level 1 — what kind of work is this, and how hard?**
   Classify the prompt into the top **intents** (embedding-first, MiniLM) and measure a
   **difficulty** score from the text; combine difficulty with the intent's `complexity` to pick a
   **tier** (`fast`/`standard`/`powerful`). **Rules** can override it, a `min_tier` floor applies,
   and low-confidence queries are **escalated**. The same intent routes *harder* questions higher.

2. **Level 2 — which model in that tier is best?**
   Score models on a **multi-dimension capability fit** (a need-vector fused from the top-k intents,
   matched against each model's real `capability_scores`) — quality-first; cost/latency only break
   near-ties — with a **failover** chain behind it.

Then it **estimates** cost/latency and, if a key is configured, returns a **live answer** from
the provider's nearest real model.

**Example:** `"design a fault-tolerant payment architecture"` →
intent `architecture_design` → rule `architecture_to_powerful` → tier `powerful` →
Level-2 pick `claude-opus-4-8` (highest capability fit for the intent).

---

## Run it (two terminals)

**Backend** (port 8000):
```bash
cd FullWebsite/backend
pip install -r requirements.txt
uvicorn app.main:app --port 8000        # docs at http://localhost:8000/docs
```

**Frontend** (port 5173):
```bash
cd FullWebsite/frontend
npm install
npm run dev                             # open http://localhost:5173
```

The Console works immediately (decision + estimate). To get **live model output**, add a key
to `backend/.env` (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GOOGLE_API_KEY`) and restart the
backend — the catalog names are future/fictional, so it calls each provider's nearest *real*
model and labels it "live via …".

---

## Repo layout

```
FullWebsite/
├── README.md                  ← you are here (overall)
├── niha-architecture.drawio   ← the architecture diagram
├── backend/                   ← FastAPI service  (see backend/README.md)
│   ├── app/                   ← main · config · registry · store · routing · services · schemas · api/v1
│   └── config_data/*.yaml     ← the source of truth: models, providers, intents, rules, routes, selection
└── frontend/                  ← React + Vite app (see frontend/README.md)
    └── src/                   ← App · components/ · api/modelIntelligenceApi.js · index.css
```

Each half has its own README with a **file-by-file map**:
- **[backend/README.md](backend/README.md)** — endpoints, the router, the store, what every `app/` file does.
- **[frontend/README.md](frontend/README.md)** — the two screens, every component, and which endpoint each calls.

---

## Core principles

- **Backend is the single source of truth.** The frontend has **zero** hardcoded data — it
  reads everything from `/api/v1/*`. The backend reads everything from `config_data/*.yaml`.
- **No fabrication.** The UI shows only fields the backend actually provides; missing data
  reads "Not available". Backend-*simulated* values (telemetry, health, audit, context
  profiles in Phase 0) are clearly labeled "simulated".
- **Phase 0 → Phase 1 is a clean swap.** Today the registry is YAML in memory (writes go to a
  non-persistent overlay; `reload` re-reads the files). The shapes map directly onto the future
  Postgres tables, so moving to a database is a `Store` implementation change, not a rewrite.

---

## Endpoints at a glance (prefix `/api/v1`)

| Group | What it covers |
|---|---|
| console | `/console/ask` — the one call the UI uses: decide + estimate + live answer |
| models | list/detail/create, config, benchmarks, usage, context-profile |
| intents | list, set tier, classify |
| rules | list/create/patch/delete/simulate |
| routing | route, routing stats |
| test | compare, single |
| providers | list/create/get/patch/delete, test, models, health |
| settings | architect-mode, fallback, audit |
| context | fit-check, compaction, budget |
| registry | reload, source |
| meta | `/health`, `/` |

Full list with methods: see [backend/README.md](backend/README.md).

---

## Tech

**Backend:** FastAPI · Pydantic v2 · PyYAML · NumPy · uvicorn (sentence-transformers optional).
**Frontend:** React 19 · Vite · plain CSS (design tokens). No database in Phase 0.

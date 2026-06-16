# Niha Model Intelligence — Frontend

A **React 19 + Vite** single-page app. Two screens:

- **Console** — a centered command bar. Type a prompt → see **which model the router picked**,
  **why** (intent · tier · rules · candidate scores), the **answer**, and the cost/latency.
- **Configure** — manage everything behind the routing: model catalog, intent→tier map,
  providers, context settings, a compare/test workbench, and live activity.

> **Every byte of data comes from the backend** (`/api/v1/*`). There is **no mock data**.
> Values the backend only *simulates* (telemetry, health, audit, context profiles) are labeled
> "simulated · Phase 0" in the UI so nothing reads as more real than it is.

---

## Run

```bash
cd FullWebsite/frontend
npm install
npm run dev          # http://localhost:5173  (expects the backend on :8000)
npm run build        # production build → dist/
```

Backend URL defaults to `http://localhost:8000` — override with `VITE_API_BASE_URL`.

---

## How it's wired

```
main.jsx ─▶ App.jsx ─┬─▶ Console.jsx                    (the ask experience)
                     └─▶ Configure.jsx ─┬─ Catalog.jsx ─▶ ModelDetail.jsx
                                        ├─ Intents.jsx
                                        ├─ ProvidersPanel.jsx
                                        ├─ ContextPanel.jsx
                                        ├─ Compare.jsx
                                        └─ Activity.jsx

   every component ─▶ src/api/modelIntelligenceApi.js ─▶ FastAPI backend (/api/v1/*)
```

**One data layer.** No component calls `fetch` directly — they all go through
`src/api/modelIntelligenceApi.js`, which (a) talks to the backend and (b) *adapts* each raw
response into the exact shape a component wants. Swap the backend and only this file changes.

---

## File map — what each file does

| File | Purpose |
|---|---|
| `src/main.jsx` | React entry point; mounts `<App/>`. |
| `src/App.jsx` | Shell: header (brand · live health dot + version · Console/Configure nav · theme toggle), loads the model cache at boot, switches between the two screens. |
| `src/index.css` | The whole design system — pine/gold/parchment tokens, dark theme, and all `nx-*` component styles. |
| `src/api/modelIntelligenceApi.js` | **The data layer.** `request()` helper + every endpoint wrapper + adapters (`adaptModel`, `adaptRule`) + the live `allModels` cache. |
| **Console** | |
| `src/components/Console.jsx` | The command bar: prompt + profile (balanced/quality/cost/latency) + options (intent/agent/workspace/session). Shows the routed model, a "why" breakdown with candidate bars, and the live output. Calls `POST /console/ask`. |
| **Configure** | |
| `src/components/Configure.jsx` | Tab strip + renders the active panel. |
| `src/components/Catalog.jsx` | Searchable/filterable model grid + "Add model". Opens the detail drawer. |
| `src/components/ModelDetail.jsx` | Slide-in drawer (Overview / Benchmarks / Usage / Config). Shows only real fields; recursively hides empty ones. Editable config writes to the overlay. |
| `src/components/Intents.jsx` | Intents grouped by category with editable default/min tier + save, plus a live "classify a prompt" tester. |
| `src/components/ProvidersPanel.jsx` | Architect Mode toggle, provider cards (test / edit / delete / connect), editable fallback chains, and a (simulated) health grid. |
| `src/components/ContextPanel.jsx` | Per-model context profile, fit-check tester, compaction thresholds, context budget. |
| `src/components/Compare.jsx` | Run one prompt across 2–4 models (Compare) or one model (Single); compare cost/latency/value. |
| `src/components/Activity.jsx` | Routing stats + tier split, registry source + reload, and the in-memory audit log. |

> **Legacy (pre-redesign, unused — safe to delete):** `Sidebar.jsx`, `Topbar.jsx`, `Tabs.jsx`,
> `Overview.jsx`, `ModelCard.jsx`, `ModelCatalog.jsx`, `IntentMap.jsx`, `RoutingRules.jsx`,
> `Providers.jsx`, `TestWorkbench.jsx`, `Modals.jsx`, `RegistryBanner.jsx`. They are not
> imported anywhere and are excluded from the build.

---

## Which screen calls which endpoint

| Screen / action | Backend endpoint(s) |
|---|---|
| Console ask | `POST /console/ask` |
| Boot model cache | `GET /models` |
| Header status | `GET /health`, `GET /` |
| Catalog grid + Add model | `GET /models`, `POST /models` |
| Model drawer (Benchmarks/Usage/Config) | `GET /models/{id}/benchmarks`, `…/usage`, `PATCH …/config` |
| Intents map + classify | `GET /intents`, `PATCH /intents/{id}`, `POST /intents/classify` |
| Providers | `GET /providers`, `POST /providers`, `GET/PATCH/DELETE /providers/{id}`, `POST /providers/{id}/test`, `GET /providers/{id}/models`, `GET /providers/health` |
| Architect mode + fallback | `GET/PATCH /settings/architect-mode`, `GET/PATCH /settings/fallback` |
| Context tab | `GET/PATCH /models/{id}/context-profile`, `POST /context/fit-check`, `GET/PATCH /context/compaction`, `GET/PATCH /context/budget` |
| Compare / Single | `POST /test/compare`, `POST /test/single` |
| Activity | `GET /routing/stats`, `GET /registry/source`, `POST /registry/reload`, `GET /audit` |

---

## Design

Brand: **pine teal + gold + parchment**, fonts **Clash Display / Manrope / JetBrains Mono**
(loaded in `index.html`). Light/dark via `[data-theme="dark"]` (toggle persists to
`localStorage`). All component classes use an `nx-*` prefix and live in `index.css`.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Blank page / network errors | Make sure the backend is running on `:8000` (`uvicorn app.main:app --port 8000`). |
| Port 5173 in use | `npm run dev -- --port 5174` |
| Calls hit the wrong host | Set `VITE_API_BASE_URL` (e.g. in a `.env`) and restart. |
| No live answer in Console | Expected unless a provider key is set in `backend/.env` — you still get the decision + estimate. |

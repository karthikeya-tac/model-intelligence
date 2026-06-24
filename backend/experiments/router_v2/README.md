# router_v2 — query-aware model selection (experiment)

A candidate routing engine that picks the best model **based on the query**, built side-by-side
with the live router so we could **compare before promoting**.

> **✅ PROMOTED.** This design now ships in `app/routing/` (`engine.py`, `classifier.py`,
> `features.py`, `difficulty.py`, `selector.py` + `selection.yaml`). This folder remains as the
> **eval/compare harness and history** — the results below are the measured *before → after* of that
> promotion. (Re-running `run_compare` now shows near-parity, since the baseline *is* the promoted engine.)

## Why
The live router barely uses the query: `intent (keyword) → STATIC intent→tier → quality on ONE
capability dimension`. It ignores the `complexity` field, hard-codes classifier confidence, and
can't tell an easy code question from a hard one.

## What's different (the four upgrades)
1. **Query features → difficulty** (`features.py`) — deterministic signals (length, code/math,
   multi-step, constraints, ambiguity) → a 0..1 difficulty score.
2. **Difficulty × complexity → tier** (`difficulty.py`) — wires the unused `complexity` field;
   hard queries escalate, trivial ones drop — **raise-only** vs the intent default; rules + min-tier
   floor still apply.
3. **Embedding-first, calibrated, top-k classification** (`classifier.py`) — MiniLM by default
   (keyword fallback if unavailable), softmax-calibrated confidence, top-k intents.
4. **Multi-dimension capability scoring** (`selector_v2.py`) — quality = a **need-vector** (fused
   from the top-k intents) **·** the model's real `capability_scores`. Missing dims are
   dropped & renormalized — never imputed. Plus a confidence **escalation** gate.

Everything is **deterministic** and **fabrication-free**: quality comes only from the real,
dense `capability_scores`; difficulty is computed from the query; `benchmarks.standard` is used
for eval grounding only, never imputed into routing. The decision shape matches the live engine
(additive fields only) so promotion is a drop-in.

## Run it
```bash
cd FullWebsite/backend
# head-to-head report (current vs new) on the held-out eval set
python -m experiments.router_v2.eval.run_compare
python -m experiments.router_v2.eval.run_compare --json     # machine-readable
python -m experiments.router_v2.eval.run_compare --check    # CI gate: fail if candidate regresses
# unit tests (features / difficulty / selector / determinism)
python -m pytest experiments/router_v2/tests/ -q
```
The candidate needs `sentence-transformers` (already a project dep); without it the classifier
falls back to keyword **loudly** and still runs.

## Measured results (36 held-out cases, baseline=current keyword router)
| metric | baseline | candidate |
|---|---:|---:|
| intent accuracy | 0.31 | **0.69** |
| intent top-k recall | 0.31 | **0.83** |
| tier exact | 0.33 | **0.64** |
| tier within-one | 0.97 | 0.92 |
| min-tier floor compliance | 0.97 | **1.00** |
| oracle model agreement | 0.03 | **0.31** |
| mean quality (gold need) | 0.82 | **0.90** |
| mean quality regret | 0.12 | **0.03** |

The candidate wins decisively on intent, quality, oracle-agreement, and regret; tier-within-one is
marginally lower due to ~3 hard-to-classify queries landing on a powerful-default intent (a routes
coverage item, not the selection logic). All thresholds live in `config.yaml` and were tuned via
`--sweep`/iteration against the held-out set (kept disjoint from `routes.yaml`/keywords to avoid
overfitting — the harness asserts low overlap).

## Files
`config.yaml` (policy knobs) · `features.py` · `difficulty.py` · `classifier.py` · `selector_v2.py`
· `router_v2.py` · `eval/{dataset.yaml, oracle.py, run_compare.py}` · `tests/`.

## Promotion path (later, not done here)
When the win holds on a larger eval set: swap `MultiDimSelector` into `app/routing` via the existing
`ModelSelector` ABC, fold `config.yaml` into `selection.yaml`, default the live classifier to
embeddings, and enrich live telemetry (router_v2 already emits `features`/`intents`/`candidates` —
the training signal for a future learned selector).

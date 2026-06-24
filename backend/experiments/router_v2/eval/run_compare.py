"""Head-to-head: CURRENT router (app.routing) vs CANDIDATE (router_v2), on the held-out set.

Run from the backend dir:
    python -m experiments.router_v2.eval.run_compare            # table report
    python -m experiments.router_v2.eval.run_compare --check    # exit 1 if candidate regresses
    python -m experiments.router_v2.eval.run_compare --json      # machine-readable

Read-only, deterministic, no provider calls.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from app.config import settings
from app.routing.engine import RouterService
from app.store.file_store import FileStore

from ..router_v2 import RouterV2
from . import oracle

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
CFG_DIR = Path(settings.config_dir)
TIER_RANK = {"fast": 0, "standard": 1, "powerful": 2}


def _load_dataset():
    return (yaml.safe_load((HERE / "dataset.yaml").read_text(encoding="utf-8")) or {}).get("cases", [])


def _overlap_max(query: str, corpus_tokensets) -> float:
    q = set(query.lower().split())
    best = 0.0
    for ts in corpus_tokensets:
        inter = len(q & ts)
        union = len(q | ts) or 1
        best = max(best, inter / union)
    return best


def _corpus_tokensets(routes_path, intents):
    sets = []
    routes = (yaml.safe_load(Path(routes_path).read_text(encoding="utf-8")) or {}).get("routes", {})
    for utts in routes.values():
        for u in utts:
            sets.append(set(u.lower().split()))
    for i in intents:
        for k in (i.keywords or []):
            sets.append(set(k.lower().split()))
    return sets


def _models_by_id(store):
    return {m.id: m.model_dump(mode="json") for m in store.registry.models}


def evaluate(router, route_fn, cases, models, models_by_id, intent_dims, label):
    agg = dict(n=0, intent=0, intent_topk=0, tier_exact=0, tier_within1=0, floor_ok=0,
               oracle_hit=0, quality=0.0, regret=0.0, escalated=0)
    rows = []
    pm = oracle.pool_mean_quality(models)
    for c in cases:
        gold = c["intent"]
        alts = set(c.get("intent_alt", []))
        need = oracle.normalize(intent_dims.get(gold, intent_dims.get("default", {"reasoning": 1.0})))
        orc_id, orc_q = oracle.oracle_best(models, need)
        dec = route_fn(prompt=c["query"])
        pred = dec.get("intent_id")
        topk = [x.get("intent_id") for x in dec.get("intents", [])] or [pred]
        chosen = dec.get("model_id")
        cq = oracle.quality_for(models_by_id.get(chosen, {}), need, pm) if chosen else 0.0
        tier = dec.get("tier")
        gold_tier = c["tier"]
        floor = c.get("min_tier")
        intent_ok = pred == gold or pred in alts
        agg["n"] += 1
        agg["intent"] += intent_ok
        agg["intent_topk"] += (gold in topk) or (alts & set(topk)) != set() or intent_ok
        agg["tier_exact"] += tier == gold_tier
        agg["tier_within1"] += abs(TIER_RANK.get(tier, 0) - TIER_RANK.get(gold_tier, 0)) <= 1
        agg["floor_ok"] += (floor is None) or TIER_RANK.get(tier, 0) >= TIER_RANK.get(floor, 0)
        agg["oracle_hit"] += chosen == orc_id
        agg["quality"] += cq
        agg["regret"] += max(0.0, orc_q - cq)
        agg["escalated"] += 1 if dec.get("escalated") else 0
        rows.append(dict(id=c["id"], gold=gold, pred=pred, ok=intent_ok, tier=tier, gold_tier=gold_tier,
                         model=chosen, oracle=orc_id, q=round(cq, 3), label=label))
    n = agg["n"] or 1
    summary = {
        "intent_acc": agg["intent"] / n,
        "intent_topk_acc": agg["intent_topk"] / n,
        "tier_exact": agg["tier_exact"] / n,
        "tier_within1": agg["tier_within1"] / n,
        "floor_compliance": agg["floor_ok"] / n,
        "oracle_agreement": agg["oracle_hit"] / n,
        "mean_quality": agg["quality"] / n,
        "mean_regret": agg["regret"] / n,
        "escalated": agg["escalated"],
    }
    return summary, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="exit 1 if candidate regresses vs baseline")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    store = FileStore(settings.config_dir, source_mode=settings.registry_mode)
    baseline = RouterService(store, selection_path=CFG_DIR / "selection.yaml",
                             routes_path=CFG_DIR / "routes.yaml", semantic=settings.semantic)
    candidate = RouterV2(store, config_path=EXP / "config.yaml", routes_path=CFG_DIR / "routes.yaml")

    cases = _load_dataset()
    models = [m.model_dump(mode="json") for m in store.registry.models]
    by_id = _models_by_id(store)
    intent_dims = candidate.cfg.get("intent_dimensions", {})

    # overfit guard: query vs routes/keywords overlap
    corpus = _corpus_tokensets(CFG_DIR / "routes.yaml", store.registry.intents)
    overlaps = sorted(((_overlap_max(c["query"], corpus), c["id"]) for c in cases), reverse=True)
    max_overlap = overlaps[0][0] if overlaps else 0.0

    base_sum, base_rows = evaluate(baseline, baseline.route, cases, models, by_id, intent_dims, "baseline")
    cand_sum, cand_rows = evaluate(candidate, candidate.route, cases, models, by_id, intent_dims, "candidate")

    if args.json:
        print(json.dumps({"baseline": base_sum, "candidate": cand_sum,
                          "baseline_mode": "semantic" if baseline._semantic else "keyword",
                          "candidate_mode": candidate.classifier_mode,
                          "max_query_overlap": max_overlap}, indent=2))
    else:
        print(f"\n=== Router compare · {len(cases)} cases ===")
        print(f"baseline classifier: {'semantic' if baseline._semantic else 'keyword'}   "
              f"candidate classifier: {candidate.classifier_mode}   "
              f"max query↔routes overlap: {max_overlap:.2f} ({'OK' if max_overlap < 0.6 else 'HIGH — possible leakage'})\n")
        metrics = [("intent_acc", "Intent accuracy"), ("intent_topk_acc", "Intent top-k recall"),
                   ("tier_exact", "Tier exact"), ("tier_within1", "Tier within-one"),
                   ("floor_compliance", "Min-tier floor"), ("oracle_agreement", "Oracle model match"),
                   ("mean_quality", "Mean quality (gold need)"), ("mean_regret", "Mean quality regret")]
        print(f"{'metric':<26}{'baseline':>12}{'candidate':>12}{'Δ':>10}")
        print("-" * 60)
        for key, label in metrics:
            b, c = base_sum[key], cand_sum[key]
            d = c - b
            print(f"{label:<26}{b:>12.3f}{c:>12.3f}{d:>+10.3f}")
        print(f"{'Escalations (candidate)':<26}{'':>12}{cand_sum['escalated']:>12}")
        print("\n--- disagreements (different model picked) ---")
        bmap = {r["id"]: r for r in base_rows}
        shown = 0
        for cr in cand_rows:
            br = bmap[cr["id"]]
            if br["model"] != cr["model"]:
                shown += 1
                c = next(x for x in cases if x["id"] == cr["id"])
                print(f"  {cr['id']}: \"{c['query'][:58]}\"")
                print(f"      gold={cr['gold']}/{cr['gold_tier']} | baseline={br['model']}/{br['tier']} "
                      f"| candidate={cr['model']}/{cr['tier']} | oracle={cr['oracle']}")
        if not shown:
            print("  (none)")
        print()

    if args.check:
        regress = []
        if cand_sum["intent_acc"] < base_sum["intent_acc"] - 1e-9:
            regress.append("intent_acc")
        if cand_sum["mean_quality"] < base_sum["mean_quality"] - 1e-9:
            regress.append("mean_quality")
        if cand_sum["floor_compliance"] < 1.0:
            regress.append("floor_compliance<100%")
        if max_overlap >= 0.6:
            regress.append("eval/routes overlap too high")
        if regress:
            print("CHECK FAILED:", ", ".join(regress)); sys.exit(1)
        print("CHECK PASSED: candidate ≥ baseline on intent_acc & mean_quality, floor 100%, no leakage.")


if __name__ == "__main__":
    main()

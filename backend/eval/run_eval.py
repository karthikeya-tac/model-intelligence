"""Offline routing-quality eval for the LIVE engine.

  cd FullWebsite/backend
  python -m eval.run_eval            # table
  python -m eval.run_eval --check    # exit 1 if accuracy is below the committed baseline

Runs each labelled query in dataset.yaml through app.routing and reports intent accuracy,
tier accuracy (exact + within-one), and min-tier floor compliance. Read-only, no provider calls.
Grow dataset.yaml to make the numbers more trustworthy. Queries are kept distinct from
routes.yaml/keywords (generalization, not memorization).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from app.config import settings
from app.routing.engine import RouterService
from app.store.file_store import FileStore

HERE = Path(__file__).resolve().parent
CFG_DIR = Path(settings.config_dir)
TIER_RANK = {"fast": 0, "standard": 1, "powerful": 2}

# committed baselines (current engine on the 36-case set); --check fails below these
MIN_INTENT_ACC = 0.60
MIN_TIER_WITHIN1 = 0.85
MIN_FLOOR = 1.00


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    cases = (yaml.safe_load((HERE / "dataset.yaml").read_text(encoding="utf-8")) or {}).get("cases", [])
    store = FileStore(settings.config_dir, source_mode=settings.registry_mode)
    eng = RouterService(store, selection_path=CFG_DIR / "selection.yaml",
                        routes_path=CFG_DIR / "routes.yaml", semantic=settings.semantic)

    n = intent = tier_exact = tier_w1 = floor_ok = 0
    misses = []
    for ce in cases:
        d = eng.route(prompt=ce["query"])
        pred, tier = d.get("intent_id"), d.get("tier")
        gold, alts = ce["intent"], set(ce.get("intent_alt", []))
        gt, floor = ce["tier"], ce.get("min_tier")
        ok = pred == gold or pred in alts
        n += 1
        intent += ok
        tier_exact += tier == gt
        tier_w1 += abs(TIER_RANK.get(tier, 0) - TIER_RANK.get(gt, 0)) <= 1
        floor_ok += (floor is None) or TIER_RANK.get(tier, 0) >= TIER_RANK.get(floor, 0)
        if not ok:
            misses.append(f"  {ce['id']}: gold={gold} pred={pred}  ({ce['query'][:50]})")

    n = n or 1
    ia, te, tw, fl = intent / n, tier_exact / n, tier_w1 / n, floor_ok / n
    print(f"\nRouting eval · {n} cases · classifier={eng.classifier_mode}")
    print(f"  intent accuracy   {ia:.3f}")
    print(f"  tier exact        {te:.3f}")
    print(f"  tier within-one   {tw:.3f}")
    print(f"  min-tier floor    {fl:.3f}")
    if misses:
        print("\nintent misses:")
        print("\n".join(misses))
    print()

    if args.check:
        bad = []
        if ia < MIN_INTENT_ACC:
            bad.append(f"intent_acc {ia:.3f} < {MIN_INTENT_ACC}")
        if tw < MIN_TIER_WITHIN1:
            bad.append(f"tier_within1 {tw:.3f} < {MIN_TIER_WITHIN1}")
        if fl < MIN_FLOOR:
            bad.append(f"floor {fl:.3f} < {MIN_FLOOR}")
        if bad:
            print("CHECK FAILED:", "; ".join(bad)); sys.exit(1)
        print("CHECK PASSED.")


if __name__ == "__main__":
    main()

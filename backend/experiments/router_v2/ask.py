"""Ask one question, see BOTH routers answer it side by side.

  cd FullWebsite/backend
  python -m experiments.router_v2.ask "write a function to dedupe a list"   # one-shot
  python -m experiments.router_v2.ask                                       # interactive loop
  python -m experiments.router_v2.ask --live "..."                          # also call the real
                                                                            # model each router picked
                                                                            # (needs a provider key in .env)

CURRENT  = the live app/routing engine (baseline).
CANDIDATE = experiments/router_v2 (difficulty-aware, embedding-first, multi-dimension).
Read-only; --live makes real provider calls only if the key is configured.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import settings
from app.routing.engine import RouterService
from app.store.file_store import FileStore

from .router_v2 import RouterV2

CFG_DIR = Path(settings.config_dir)
EXP = Path(__file__).resolve().parent


def _bar(label):
    return f"\n{'─' * 78}\n{label}\n{'─' * 78}"


def _fmt(name, d):
    out = [f"  {name}"]
    intent = d.get("intent_id") or "unknown"
    conf = d.get("confidence", 0.0)
    src = d.get("intent_source", "?")
    line = f"    intent : {intent}  ({src}, conf {conf:.2f})"
    if d.get("difficulty") is not None:
        line += f"   difficulty {d['difficulty']:.2f}"
    out.append(line)
    base, tier = d.get("base_tier"), d.get("tier")
    out.append(f"    tier   : {base}" + (f" → {tier}" if tier != base else f"  ({tier})")
               + ("   [escalated]" if d.get("escalated") else ""))
    out.append(f"    MODEL  : {d.get('model_id')}   ({d.get('provider')})")
    cands = d.get("candidates") or []
    if cands:
        tops = "  ".join(f"{c['model_id']}={c.get('quality', 0):.2f}" for c in cands[:3])
        out.append(f"    top picks (capability fit): {tops}")
    if d.get("matched_rules"):
        out.append("    rules  : " + ", ".join(r["rule_id"] for r in d["matched_rules"]))
    out.append(f"    why    : {d.get('reason', '')}")
    return "\n".join(out)


def _live(store, model_id, tier, prompt):
    from app.routing import execute as ex
    from app.services import secrets
    m = store.registry.model(model_id)
    if not m:
        return "      (model not in catalog)"
    prov = store.registry.provider(m.provider)
    kind = prov.kind.value if prov else m.provider
    key = secrets.resolve(prov.auth.api_key_ref if prov else None)
    r = ex.execute(kind, m.classification.tier.value, prompt, key)
    if r.get("output"):
        return f"      live via {r['real_model']}:\n      " + r["output"].strip().replace("\n", "\n      ")
    if not r.get("configured"):
        return f"      (no live output — set {r.get('env_var') or kind.upper()+'_API_KEY'} in backend/.env)"
    return f"      (live call failed: {r.get('error')})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="*", help="the question (omit for interactive mode)")
    ap.add_argument("--live", action="store_true", help="also call the real model each router picked")
    args = ap.parse_args()

    store = FileStore(settings.config_dir, source_mode=settings.registry_mode)
    baseline = RouterService(store, selection_path=CFG_DIR / "selection.yaml",
                             routes_path=CFG_DIR / "routes.yaml", semantic=settings.semantic)
    candidate = RouterV2(store, config_path=EXP / "config.yaml", routes_path=CFG_DIR / "routes.yaml")
    print(f"baseline classifier: {'semantic' if baseline._semantic else 'keyword'}   "
          f"candidate classifier: {candidate.classifier_mode}")

    def handle(q):
        bd = baseline.route(prompt=q)
        cd = candidate.route(prompt=q)
        print(_bar(f'Q: {q}'))
        print(_fmt("CURRENT  (baseline)", bd))
        print()
        print(_fmt("CANDIDATE (router_v2)", cd))
        if bd.get("model_id") != cd.get("model_id"):
            print("\n    ➜ the two routers picked DIFFERENT models.")
        if args.live:
            print("\n  live output:")
            print("    CURRENT  →", _live(store, bd.get("model_id"), bd.get("tier"), q).lstrip())
            print("    CANDIDATE→", _live(store, cd.get("model_id"), cd.get("tier"), q).lstrip())
        print()

    if args.query:
        handle(" ".join(args.query))
        return
    print("Interactive — type a question (blank line or Ctrl-C to quit).")
    try:
        while True:
            q = input("\n> ").strip()
            if not q:
                break
            handle(q)
    except (EOFError, KeyboardInterrupt):
        print()


if __name__ == "__main__":
    main()

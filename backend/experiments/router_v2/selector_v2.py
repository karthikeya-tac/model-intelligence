"""Level-2 — multi-dimension capability scoring.

Where the live ScoringSelector scores quality on ONE capability dimension per intent, this
scores against a NEED-VECTOR — a weighted blend of the capability dimensions a query actually
needs (fused from the top-k intents). quality(model) = need · capability_scores / 100, a dot
product of two REAL vectors (capability_scores is dense/real; need weights are policy).

Missing dimensions are dropped & renormalized — never imputed (no fabrication).
Implements the existing ModelSelector ABC so it can be promoted into app/routing as a drop-in.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.routing.selector import Features, ModelSelector, Ranked

TIER_RANK = {"fast": 0, "standard": 1, "powerful": 2}
_ROLE_RANK = {"primary": 2, "alternative": 1, "fallback": 0}


class MultiDimSelector(ModelSelector):
    def __init__(self, cfg: Dict):
        self.cfg = cfg or {}
        self.intent_dimensions: Dict[str, Dict[str, float]] = self.cfg.get("intent_dimensions", {}) or {}
        self.latency_scores: Dict[str, float] = self.cfg.get("latency_scores", {}) or {}
        self.default_latency = float(self.cfg.get("default_latency_score", 0.5))
        self.output_weight = float(self.cfg.get("output_weight", 3.0))
        self.eps = float(self.cfg.get("quality_tie_epsilon", 0.05)) or 0.05
        self.allow_standby = True
        self.last_notes: List[str] = []

    # ---- need-vector resolution ----
    def resolve_dimensions(self, intent: Optional[str]) -> Dict[str, float]:
        d = self.intent_dimensions.get(intent or "default") or self.intent_dimensions.get("default", {"reasoning": 1.0})
        return self._normalize(dict(d))

    @staticmethod
    def _normalize(d: Dict[str, float]) -> Dict[str, float]:
        tot = sum(v for v in d.values() if v > 0) or 1.0
        return {k: v / tot for k, v in d.items() if v > 0}

    # ---- helpers ----
    def _has_pricing(self, m):
        pr = m.get("pricing", {}) or {}
        return pr.get("input") is not None or pr.get("output") is not None

    def _price(self, m):
        pr = m.get("pricing", {}) or {}
        return (pr.get("input", 0) or 0) + self.output_weight * (pr.get("output", 0) or 0)

    def _latency(self, m):
        lc = (m.get("classification", {}) or {}).get("latency_class")
        return self.latency_scores.get(lc, self.default_latency)

    # ---- the policy ----
    def select(self, tier, intent, models, *, features=None, budget_usd=None,
               dimensions: Optional[Dict[str, float]] = None,
               pool_tiers: Optional[List[str]] = None) -> List[Ranked]:
        self.last_notes = []
        f = features or Features()
        need = self._normalize(dict(dimensions)) if dimensions else self.resolve_dimensions(intent)
        tiers = set(pool_tiers or [tier])

        def status_ok(m):
            s = (m.get("classification", {}) or {}).get("status")
            return s == "active" or (self.allow_standby and s == "standby")

        base = [m for m in models if (m.get("classification", {}) or {}).get("tier") in tiers and status_ok(m)]
        if not base:
            self.last_notes.append(f"no eligible models at tier(s) {sorted(tiers)}")
            return []

        def meets(m):
            cap = m.get("capability", {}) or {}
            if f.min_context and (cap.get("context_window", 0) or 0) < f.min_context:
                return False
            if f.modalities and not set(f.modalities).issubset(set(cap.get("input_modalities", []) or [])):
                return False
            if f.needs_tools and not cap.get("supports_tools", False):
                return False
            return True

        survivors = [m for m in base if meets(m)] or base
        if survivors is base and (f.min_context or f.modalities or f.needs_tools):
            self.last_notes.append("constraints relaxed (no model met them)")

        priced = [self._price(m) for m in survivors if self._has_pricing(m)]
        pmin, pmax = (min(priced), max(priced)) if priced else (0.0, 0.0)
        catalog_index = {m["id"]: i for i, m in enumerate(models)}

        # pool mean per-dimension fallback signal
        all_scores = [(m.get("benchmarks", {}) or {}).get("capability_scores", {}) or {} for m in survivors]

        ranked: List[Ranked] = []
        for m in survivors:
            cs = (m.get("benchmarks", {}) or {}).get("capability_scores", {}) or {}
            notes: List[str] = []
            present = {d: w for d, w in need.items() if d in cs}
            if present:
                wsum = sum(present.values())
                quality = sum((cs[d] / 100.0) * w for d, w in present.items()) / wsum
                if len(present) < len(need):
                    notes.append("dims renormalized (some missing)")
            elif "reasoning" in cs:
                quality = cs["reasoning"] / 100.0 * 0.9
                notes.append("quality via reasoning proxy")
            else:
                vals = [v for s in all_scores for v in s.values()] or [50]
                quality = (sum(vals) / len(vals) / 100.0) * 0.9
                notes.append("quality via pool mean")

            if self._has_pricing(m):
                price = self._price(m)
                cost = 1.0 if pmax == pmin else 1.0 - (price - pmin) / (pmax - pmin)
            else:
                cost = 0.5
                notes.append("no pricing (neutral cost)")

            latency = self._latency(m)
            available = (m.get("classification", {}) or {}).get("status") == "active"
            if not available:
                notes.append("standby (failover only)")
            top_dims = ", ".join(f"{d} {round(w,2)}" for d, w in sorted(present.items(), key=lambda x: -x[1])[:3])
            ranked.append(Ranked(model=m["id"], provider=m.get("provider", "?"),
                                 score=round(quality, 4), quality=round(quality, 3),
                                 cost=round(cost, 3), latency=round(latency, 3),
                                 available=available,
                                 note="; ".join([f"blend: {top_dims}"] + notes) if top_dims else "; ".join(notes)))

        ranked.sort(key=lambda r: catalog_index.get(r.model, 0))
        ranked.sort(key=lambda r: (r.available, round(r.quality / self.eps), r.cost, r.latency,
                                   _ROLE_RANK.get((next((m.get("classification", {}).get("role", "alternative")
                                                         for m in models if m["id"] == r.model), "alternative")), 1)),
                    reverse=True)
        return ranked

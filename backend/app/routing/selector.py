"""Level 2 — model selection within a tier (multi-dimension, quality-first).

Level 1 decides the TIER. This module decides WHICH model in that tier serves the request, by
scoring every candidate against a NEED-VECTOR — a weighted blend of the capability dimensions the
query needs (fused from the top-k intents):

    quality(model) = need · capability_scores / 100      (dot product of two REAL vectors)
      cost    = cheaper-is-higher, min-max normalised within the tier candidates
      latency = latency_class mapped to 0..1 (see selection.yaml)

Quality-first: a clearly-more-capable model always wins; cost/latency only break NEAR-TIES
(within quality_tie_epsilon). Missing capability dimensions are dropped & renormalized — never
imputed (no fabrication). Hard constraints (context, modality, tools, budget, status) filter first.

`ModelSelector` is the pluggable seam — a learned/bandit/cascading selector can implement the same
interface later without touching the router.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

_ROLE_RANK = {"primary": 2, "alternative": 1, "fallback": 0}


@dataclass
class Ranked:
    model: str
    provider: str
    score: float
    quality: float          # 0..1 (capability-fit)
    cost: float             # 0..1 (cheaper = higher)
    latency: float          # 0..1 (faster = higher)
    available: bool         # active now? (standby ranks below as failover-only)
    note: str = ""


@dataclass
class Features:
    """Per-request signals that drive the hard constraints."""
    min_context: int = 0
    modalities: List[str] = field(default_factory=list)
    needs_tools: bool = False
    est_input_tokens: int = 0
    est_output_tokens: int = 0


class ModelSelector(ABC):
    @abstractmethod
    def select(self, tier: str, intent: Optional[str], models: List[dict], *,
               features: Optional[Features] = None, budget_usd: Optional[float] = None,
               dimensions: Optional[Dict[str, float]] = None,
               pool_tiers: Optional[List[str]] = None) -> List[Ranked]:
        ...


class ScoringSelector(ModelSelector):
    """Deterministic multi-dimension capability scorer driven by selection.yaml."""

    def __init__(self, config_path: Path):
        cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
        self.intent_dimensions: Dict[str, Dict[str, float]] = cfg.get("intent_dimensions", {}) or {}
        self.intent_capability: Dict[str, str] = cfg.get("intent_capability", {}) or {}   # single-dim fallback
        self.latency_scores: Dict[str, float] = cfg.get("latency_scores", {}) or {}
        self.constraints: Dict = cfg.get("constraints", {}) or {}
        self.default_latency = float(self.constraints.get("default_latency_score", 0.5))
        self.output_weight = float(cfg.get("output_weight", 3.0))
        self.eps = float(cfg.get("quality_tie_epsilon", 0.05)) or 0.05
        self.allow_standby = bool(self.constraints.get("allow_standby_as_failover", True))
        self.last_notes: List[str] = []

    # ---- need-vector resolution ----
    def resolve_dimensions(self, intent: Optional[str]) -> Dict[str, float]:
        d = self.intent_dimensions.get(intent or "default")
        if d is None:
            cap = self.intent_capability.get(intent or "default") or self.intent_capability.get("default")
            d = {cap: 1.0} if cap else self.intent_dimensions.get("default", {"reasoning": 1.0})
        return self._normalize(dict(d))

    @staticmethod
    def _normalize(d: Dict[str, float]) -> Dict[str, float]:
        tot = sum(v for v in d.values() if v > 0) or 1.0
        return {k: v / tot for k, v in d.items() if v > 0}

    def _has_pricing(self, m):
        pr = m.get("pricing", {}) or {}
        return pr.get("input") is not None or pr.get("output") is not None

    def _price(self, m):
        pr = m.get("pricing", {}) or {}
        return (pr.get("input", 0) or 0) + self.output_weight * (pr.get("output", 0) or 0)

    def _latency(self, m):
        lc = (m.get("classification", {}) or {}).get("latency_class")
        return self.latency_scores.get(lc, self.default_latency)

    def _est_cost_usd(self, m, f: Features) -> float:
        pr = m.get("pricing", {}) or {}
        return (pr.get("input", 0) or 0) * f.est_input_tokens / 1e6 + \
               (pr.get("output", 0) or 0) * f.est_output_tokens / 1e6

    # ---- the policy ----
    def select(self, tier, intent, models, *, features=None, budget_usd=None,
               dimensions=None, pool_tiers=None):
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

        capable = [m for m in base if meets(m)]
        if not capable:
            self.last_notes.append("no model met context/modality/tool constraints → relaxed")
            capable = base

        if budget_usd is not None:
            within = [m for m in capable if self._est_cost_usd(m, f) <= budget_usd]
            if within:
                survivors = within
            else:
                self.last_notes.append(f"no model fits budget ${budget_usd}/req → cheapest available")
                survivors = sorted(capable, key=lambda m: self._est_cost_usd(m, f))[:1]
        else:
            survivors = capable

        priced = [self._price(m) for m in survivors if self._has_pricing(m)]
        pmin, pmax = (min(priced), max(priced)) if priced else (0.0, 0.0)
        catalog_index = {m["id"]: i for i, m in enumerate(models)}
        roles = {m["id"]: (m.get("classification", {}) or {}).get("role", "alternative") for m in models}
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
            top_dims = ", ".join(f"{d} {round(w, 2)}" for d, w in sorted(present.items(), key=lambda x: -x[1])[:3])
            ranked.append(Ranked(model=m["id"], provider=m.get("provider", "?"),
                                 score=round(quality, 4), quality=round(quality, 3),
                                 cost=round(cost, 3), latency=round(latency, 3), available=available,
                                 note="; ".join(([f"blend: {top_dims}"] if top_dims else []) + notes)))

        # quality-first failover order: available → capability (ε-bucketed) → cheaper → faster → role → catalog
        ranked.sort(key=lambda r: catalog_index.get(r.model, 0))
        ranked.sort(key=lambda r: (r.available, round(r.quality / self.eps), r.cost, r.latency,
                                   _ROLE_RANK.get(roles.get(r.model, "alternative"), 1)),
                    reverse=True)
        return ranked

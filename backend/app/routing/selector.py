"""Level 2 — model selection within a tier.

Level 1 (the hybrid router) decides the TIER. This module decides WHICH model in
that tier serves the request, by scoring every candidate on:

    score = w_quality·quality + w_cost·cost + w_latency·latency      (each 0..1)
      quality = capability_scores[intent's dimension] / 100
      cost    = cheaper-is-higher, min-max normalised within the tier candidates
      latency = latency_class mapped to 0..1 (see selection.yaml)

Hard constraints (context window, modality, tools, budget, status) filter the pool
first; survivors are scored and ranked. The ranking IS the failover order: pick #1,
fall to #2 if it's unavailable.

`ModelSelector` is the pluggable seam — a learned/bandit/cascading selector can
implement the same interface later without touching the router.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml


@dataclass
class Ranked:
    model: str
    provider: str
    score: float
    quality: float          # 0..1 (capability-fit)
    cost: float             # 0..1 (cheaper = higher)
    latency: float          # 0..1 (faster = higher)
    available: bool         # active now? (standby ranks below as failover-only)
    note: str = ""          # e.g. "quality fallback: reasoning", "standby (failover)"


@dataclass
class Features:
    """Per-request signals that drive the hard constraints."""
    min_context: int = 0
    modalities: List[str] = field(default_factory=list)   # e.g. ["image", "pdf"]
    needs_tools: bool = False
    est_input_tokens: int = 0
    est_output_tokens: int = 0


class ModelSelector(ABC):
    """Pluggable interface. Implement `select` to rank a tier's candidates."""

    @abstractmethod
    def select(self, tier: str, intent: Optional[str], models: List[dict], *,
               features: Optional[Features] = None, profile: Optional[str] = None,
               budget_usd: Optional[float] = None) -> List[Ranked]:
        ...


class ScoringSelector(ModelSelector):
    """Deterministic capability × cost × latency scorer driven by selection.yaml."""

    REQUIRED_WEIGHTS = ("quality", "cost", "latency")

    def __init__(self, config_path: Path, *, profile: Optional[str] = None):
        cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
        self.profiles: Dict[str, Dict[str, float]] = cfg.get("profiles", {}) or {}
        if not self.profiles:                                   # never run weightless
            self.profiles = {"balanced": {"quality": 0.5, "cost": 0.3, "latency": 0.2}}
        self.default_profile = profile or cfg.get("default_profile", "balanced")
        if self.default_profile not in self.profiles:
            self.default_profile = next(iter(self.profiles))
        self.latency_scores: Dict[str, float] = cfg.get("latency_scores", {}) or {}
        self.intent_capability: Dict[str, str] = cfg.get("intent_capability", {}) or {}
        self.output_weight: float = float(cfg.get("output_weight", 3.0))
        self.constraints: Dict = cfg.get("constraints", {}) or {}
        self.default_latency: float = float(self.constraints.get("default_latency_score", 0.5))
        self.last_notes: List[str] = []          # per-call diagnostics (what got relaxed, etc.)

    # ---- helpers ------------------------------------------------------------
    def dimension(self, intent: Optional[str]) -> str:
        return self.intent_capability.get(intent or "default",
                                          self.intent_capability.get("default", "reasoning"))

    def _weights(self, profile: Optional[str]) -> Dict[str, float]:
        name = profile or self.default_profile
        if name not in self.profiles:
            self.last_notes.append(f"unknown profile '{name}' → using '{self.default_profile}'")
            name = self.default_profile
        raw = self.profiles[name]
        w = {k: max(0.0, float(raw.get(k, 0.0))) for k in self.REQUIRED_WEIGHTS}  # clamp negatives/missing
        total = sum(w.values()) or 1.0
        return {k: v / total for k, v in w.items()}     # normalise so weights sum to 1

    def _has_pricing(self, m: dict) -> bool:
        pr = m.get("pricing", {}) or {}
        return (pr.get("input") is not None) or (pr.get("output") is not None)

    def _blended_price(self, m: dict) -> float:
        pr = m.get("pricing", {}) or {}
        return (pr.get("input", 0) or 0) + self.output_weight * (pr.get("output", 0) or 0)

    def _latency(self, m: dict) -> float:
        lc = m.get("classification", {}).get("latency_class")
        return self.latency_scores.get(lc, self.default_latency)

    def _est_cost_usd(self, m: dict, f: Features) -> float:
        pr = m.get("pricing", {}) or {}
        return (pr.get("input", 0) or 0) * f.est_input_tokens / 1e6 + \
               (pr.get("output", 0) or 0) * f.est_output_tokens / 1e6

    # ---- the policy ---------------------------------------------------------
    def select(self, tier, intent, models, *, features=None, profile=None, budget_usd=None):
        self.last_notes = []                                    # reset per-call diagnostics
        f = features or Features()
        w = self._weights(profile)
        dim = self.dimension(intent)
        allow_standby = self.constraints.get("allow_standby_as_failover", True)
        catalog_index = {m["id"]: i for i, m in enumerate(models)}
        roles = {m["id"]: (m.get("classification", {}) or {}).get("role", "alternative") for m in models}
        role_rank = {"primary": 2, "alternative": 1, "fallback": 0}

        def status_ok(m):
            s = (m.get("classification", {}) or {}).get("status")
            return s == "active" or (allow_standby and s == "standby")

        # 1. base pool: eligible-status models at this tier
        base = [m for m in models
                if (m.get("classification", {}) or {}).get("tier") == tier and status_ok(m)]
        if not base:
            self.last_notes.append(f"no eligible models at tier '{tier}'")
            return []

        # 2. constraints in stages — so a relax is transparent, never silent
        def meets_capability(m):
            cap = m.get("capability", {}) or {}
            if f.min_context and cap.get("context_window", 0) < f.min_context:
                return False
            if f.modalities and not set(f.modalities).issubset(set(cap.get("input_modalities", []) or [])):
                return False
            if f.needs_tools and not cap.get("supports_tools", False):
                return False
            return True

        capable = [m for m in base if meets_capability(m)]
        if not capable:
            self.last_notes.append("no model met context/modality/tool constraints → relaxed")
            capable = base

        if budget_usd is not None:
            within = [m for m in capable if self._est_cost_usd(m, f) <= budget_usd]
            if within:
                survivors = within
            else:                                              # keep budget honest: cheapest, flagged
                self.last_notes.append(f"no model fits budget ${budget_usd}/req → cheapest available")
                survivors = sorted(capable, key=lambda m: self._est_cost_usd(m, f))[:1]
        else:
            survivors = capable

        # 3. score — cost normalised within survivors that HAVE pricing
        priced = [self._blended_price(m) for m in survivors if self._has_pricing(m)]
        pmin, pmax = (min(priced), max(priced)) if priced else (0.0, 0.0)
        present = [m["benchmarks"]["capability_scores"][dim] / 100.0
                   for m in survivors
                   if dim in ((m.get("benchmarks", {}) or {}).get("capability_scores", {}) or {})]
        mean_q = sum(present) / len(present) if present else 0.5

        ranked: List[Ranked] = []
        for m in survivors:
            cs = (m.get("benchmarks", {}) or {}).get("capability_scores", {}) or {}
            notes: List[str] = []
            if dim in cs:
                quality = cs[dim] / 100.0
            elif "reasoning" in cs:
                quality = cs["reasoning"] / 100.0 * 0.9        # proxy dimension → small penalty
                notes.append(f"quality via reasoning (no '{dim}')")
            else:
                quality = mean_q * 0.9
                notes.append("quality via pool mean")

            if self._has_pricing(m):
                price = self._blended_price(m)
                cost = 1.0 if pmax == pmin else 1.0 - (price - pmin) / (pmax - pmin)
            else:
                cost = 0.5                                     # unknown price → neutral, never auto-cheapest
                notes.append("no pricing (neutral cost)")

            latency = self._latency(m)
            score = w["quality"] * quality + w["cost"] * cost + w["latency"] * latency
            available = (m.get("classification", {}) or {}).get("status") == "active"
            if not available:
                notes.append("standby (failover only)")
            ranked.append(Ranked(model=m["id"], provider=m.get("provider", "?"),
                                 score=round(score, 4), quality=round(quality, 3),
                                 cost=round(cost, 3), latency=round(latency, 3),
                                 available=available, note="; ".join(notes)))

        # 4. deterministic rank = failover order
        #    available first, then score, then cheaper, then role, then catalog order
        ranked.sort(key=lambda r: catalog_index.get(r.model, 0))          # stable base order
        ranked.sort(key=lambda r: (r.available, round(r.score, 6), r.cost,
                                   role_rank.get(roles.get(r.model, "alternative"), 0)),
                    reverse=True)
        return ranked

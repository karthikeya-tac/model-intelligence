"""In-memory telemetry — makes /routing/stats, /usage, /audit feel alive.

Every /route appends a `routing_decision`; stats and per-model usage are computed
from real activity. A deterministic seeded backlog is generated at boot so the
dashboards aren't empty on first load. (Phase 1 swaps this for the
`routing_decisions` → `usage_rollups` tables.)
"""
from __future__ import annotations

import random
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .sim import simulate


class Telemetry:
    def __init__(self, store, *, seed_count: int = 480, seed: int = 7):
        self.store = store
        self.decisions: List[Dict[str, Any]] = []
        self._seed(seed_count, seed)

    def _seed(self, n: int, seed: int) -> None:
        reg = self.store.registry
        rng = random.Random(seed)
        active = [m for m in reg.models if m.classification.status.value == "active"]
        if not active:
            return
        intents = reg.intents or []
        for _ in range(n):
            m = rng.choice(active)
            md = m.model_dump(mode="json")
            sim = simulate(md, "seed", "L1")
            intent = rng.choice(intents).id if intents else None
            self.decisions.append({
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "intent_id": intent, "agent": "seed", "workspace": "seed",
                "model_id": m.id, "tier": m.classification.tier.value,
                "matched_rules": [], "escalated": rng.random() < 0.06,
                "cost_usd": sim["cost_usd"], "latency_ms": sim["latency_ms"], "seeded": True,
            })

    def record(self, decision: Dict[str, Any], *, cost_usd: float = 0.0, latency_ms: int = 0) -> None:
        self.decisions.append({
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "intent_id": decision.get("intent_id"), "agent": decision.get("agent"),
            "workspace": decision.get("workspace"), "model_id": decision.get("model_id"),
            "tier": decision.get("tier"), "matched_rules": [r["rule_id"] for r in decision.get("matched_rules", [])],
            "escalated": decision.get("escalated", False),
            "cost_usd": cost_usd, "latency_ms": latency_ms, "seeded": False,
        })

    # ----- aggregates -------------------------------------------------------
    def stats(self) -> Dict[str, Any]:
        reg = self.store.registry
        n = len(self.decisions) or 1
        tier_counts = Counter(d["tier"] for d in self.decisions)
        escalated = sum(1 for d in self.decisions if d["escalated"])
        active_models = sum(1 for m in reg.models if m.classification.status.value == "active")
        active_rules = len(self.store.rules(status="active"))
        return {
            "active_models": active_models,
            "tier_split": {t: round(tier_counts.get(t, 0) / n * 100, 1) for t in ("fast", "standard", "powerful")},
            "active_rules": active_rules,
            "optimal_match_pct": round((n - escalated) / n * 100, 1),
            "decisions": len(self.decisions),
            "escalated_pct": round(escalated / n * 100, 1),
        }

    def usage(self, model_id: str, period: str = "month") -> Dict[str, Any]:
        rows = [d for d in self.decisions if d["model_id"] == model_id]
        total = len(self.decisions) or 1
        n = len(rows)
        cost = sum(d["cost_usd"] for d in rows)
        avg_latency = round(sum(d["latency_ms"] for d in rows) / n) if n else 0
        return {
            "model_id": model_id, "period": period, "requests": n,
            "pct": round(n / total * 100, 1), "cost_usd": round(cost, 4),
            "avg_latency_ms": avg_latency,
        }

"""FileStore — Phase-0 data source.

Holds the immutable `Registry` snapshot (catalog reads) plus all MUTABLE Phase-0
state in memory: model config, context profiles, intent tier overrides, rules,
providers, settings, and an audit log. Writes mutate these in-memory structures;
`reload()` atomically rebuilds from disk and resets the overlay. Not persistent —
that's the DbStore's job in Phase 1.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.registry import Registry, load_registry

from .base import Store

TRUST = ["L0", "L1", "L2", "L3"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _default_model_config(m) -> Dict[str, Any]:
    mx = m.capability.max_output_tokens
    locked = bool(m.controls and getattr(m.controls, "sampling", None) and m.controls.sampling.value == "locked")
    budget = None
    if m.controls and m.controls.reasoning and m.controls.reasoning.budget_tokens:
        bt = m.controls.reasoning.budget_tokens
        base = bt.max or (bt.min and bt.min * 8) or 8192
        budget = {t: int(base * f) for t, f in zip(TRUST, (0.25, 0.5, 0.75, 1.0))}
    return {
        "model_id": m.id,
        "tier": m.classification.tier.value,
        "temperature": 1.0 if locked else 0.7,
        "top_p": 1.0,
        "max_output_by_trust": {t: int(mx * f) for t, f in zip(TRUST, (0.25, 0.5, 0.75, 1.0))},
        "thinking_budget_by_trust": budget,
        "system_prefix": "",
        "rate_limit_rpm": m.classification and getattr(m, "rate_limit_rpm", None),
        "status": m.classification.status.value,
        "sampling": (m.controls.sampling.value if m.controls and m.controls.sampling else "tunable"),
    }


def _default_context_profile(m) -> Dict[str, Any]:
    native = m.capability.context_window
    return {
        "model_id": m.id,
        "native_window": native,
        "effective_window": native,
        "compaction_floor_pct": 80,
        "memory_budget_tokens": int(native * 0.2),
        "context_budget_total": native,
    }


class FileStore(Store):
    def __init__(self, base_dir: str, *, source_mode: str = "file"):
        self._base_dir = base_dir
        self._source_mode = source_mode
        self._lock = threading.RLock()
        self._registry = load_registry(base_dir=base_dir, source_mode=source_mode)
        self._seed()

    # ----- snapshot + atomic reload ----------------------------------------
    @property
    def registry(self) -> Registry:
        return self._registry

    def reload(self) -> Dict[str, int]:
        # build fully first; only swap on success (bad file keeps the old config)
        fresh = load_registry(base_dir=self._base_dir, source_mode=self._source_mode)
        with self._lock:
            self._registry = fresh
            self._seed()
            return self._registry.counts()

    def source(self) -> Dict[str, Optional[str]]:
        return self._registry.source()

    # ----- seed mutable overlay from the snapshot --------------------------
    def _seed(self) -> None:
        reg = self._registry
        self._model_config = {m.id: _default_model_config(m) for m in reg.models}
        self._context_profile = {m.id: _default_context_profile(m) for m in reg.models}
        self._intent_override: Dict[str, Dict[str, str]] = {}     # intent_id -> {default_tier,min_tier}
        self._rules: Dict[str, dict] = {r.id: r.model_dump(mode="json") for r in reg.rules}
        self._providers: Dict[str, dict] = {p.id: p.model_dump(mode="json") for p in reg.providers}
        self._audit: List[Dict[str, Any]] = []
        self._audit_seq = 0
        self._settings = self._seed_settings()

    def _seed_settings(self) -> Dict[str, Any]:
        reg = self._registry

        def primaries(tier: str) -> List[str]:
            return [m.id for m in reg.models
                    if m.classification.tier.value == tier
                    and m.classification.status.value == "active"]

        return {
            "architect_mode": {"enabled": False, "plan_tier": "powerful", "exec_tier": "standard",
                               "uses_this_month": 0, "savings_usd": 0.0},
            "fallback": {
                "chains": {t: primaries(t)[:3] for t in ("fast", "standard", "powerful")},
                "trigger": "error_or_timeout", "retries": 2, "backoff": "exponential", "notify": True,
            },
            "compaction": {
                "thresholds": {"mask_pct": 60, "summarise_pct": 80, "emergency_pct": 92},
                "summariser_model_id": (primaries("fast") or [None])[0],
                "by_trust": {t: {"summarise_pct": p} for t, p in zip(TRUST, (70, 80, 85, 90))},
            },
            "budget": {"total": 200000, "layers": {"l2": 40000, "l3_75": 60000, "l4": 60000, "l5": 40000}},
        }

    # ----- audit ------------------------------------------------------------
    def record_audit(self, actor: str, entity: str, entity_id: str, before: Any, after: Any) -> None:
        with self._lock:
            self._audit_seq += 1
            self._audit.append({"id": self._audit_seq, "ts": _now(), "actor": actor,
                                "entity": entity, "entity_id": entity_id,
                                "before": before, "after": after})

    def audit(self, entity: Optional[str] = None, since: Optional[str] = None) -> List[Dict[str, Any]]:
        rows = list(reversed(self._audit))
        if entity:
            rows = [r for r in rows if r["entity"] == entity]
        if since:
            rows = [r for r in rows if r["ts"] >= since]
        return rows

    # ----- model config + context profile ----------------------------------
    def model_config(self, model_id: str) -> Optional[dict]:
        return self._model_config.get(model_id)

    def set_model_config(self, model_id: str, patch: dict) -> dict:
        with self._lock:
            cfg = self._model_config.setdefault(model_id, {"model_id": model_id})
            before = dict(cfg)
            cfg.update({k: v for k, v in patch.items() if v is not None})
            self.record_audit("system", "model_config", model_id, before, dict(cfg))
            return cfg

    def context_profile(self, model_id: str) -> Optional[dict]:
        return self._context_profile.get(model_id)

    def set_context_profile(self, model_id: str, patch: dict) -> dict:
        with self._lock:
            prof = self._context_profile.setdefault(model_id, {"model_id": model_id})
            before = dict(prof)
            prof.update({k: v for k, v in patch.items() if v is not None})
            self.record_audit("system", "context_profile", model_id, before, dict(prof))
            return prof

    # ----- intents (tier overrides) ----------------------------------------
    def intent_tier(self, intent_id: str) -> Dict[str, str]:
        """Effective tiers = registry defaults with any in-memory override applied."""
        intent = self._registry.intent(intent_id)
        base = {"default_tier": intent.default_tier.value, "min_tier": intent.min_tier.value} if intent else {}
        base.update(self._intent_override.get(intent_id, {}))
        return base

    def set_intent_tier(self, intent_id: str, default_tier: Optional[str], min_tier: Optional[str]) -> dict:
        with self._lock:
            before = self.intent_tier(intent_id)
            ov = self._intent_override.setdefault(intent_id, {})
            if default_tier:
                ov["default_tier"] = default_tier
            if min_tier:
                ov["min_tier"] = min_tier
            after = self.intent_tier(intent_id)
            self.record_audit("system", "intent", intent_id, before, after)
            return after

    # ----- rules ------------------------------------------------------------
    def rules(self, status: Optional[str] = None) -> List[dict]:
        rows = list(self._rules.values())
        if status:
            rows = [r for r in rows if r.get("status") == status]
        return rows

    def rule(self, rule_id: str) -> Optional[dict]:
        return self._rules.get(rule_id)

    def create_rule(self, rule: dict) -> dict:
        with self._lock:
            self._rules[rule["id"]] = rule
            self.record_audit("system", "rule", rule["id"], None, rule)
            return rule

    def patch_rule(self, rule_id: str, patch: dict) -> Optional[dict]:
        with self._lock:
            r = self._rules.get(rule_id)
            if r is None:
                return None
            before = dict(r)
            r.update({k: v for k, v in patch.items() if v is not None})
            self.record_audit("system", "rule", rule_id, before, dict(r))
            return r

    def delete_rule(self, rule_id: str) -> bool:
        with self._lock:
            r = self._rules.pop(rule_id, None)
            if r is None:
                return False
            self.record_audit("system", "rule", rule_id, r, None)
            return True

    # ----- providers --------------------------------------------------------
    def providers(self) -> List[dict]:
        return list(self._providers.values())

    def provider(self, provider_id: str) -> Optional[dict]:
        return self._providers.get(provider_id)

    def create_provider(self, provider: dict) -> dict:
        with self._lock:
            self._providers[provider["id"]] = provider
            self.record_audit("system", "provider", provider["id"], None, provider)
            return provider

    def patch_provider(self, provider_id: str, patch: dict) -> Optional[dict]:
        with self._lock:
            p = self._providers.get(provider_id)
            if p is None:
                return None
            before = dict(p)
            p.update({k: v for k, v in patch.items() if v is not None})
            self.record_audit("system", "provider", provider_id, before, dict(p))
            return p

    def delete_provider(self, provider_id: str) -> bool:
        with self._lock:
            p = self._providers.pop(provider_id, None)
            if p is None:
                return False
            self.record_audit("system", "provider", provider_id, p, None)
            return True

    # ----- settings ---------------------------------------------------------
    def settings(self, key: str) -> dict:
        return self._settings[key]

    def patch_settings(self, key: str, patch: dict) -> dict:
        with self._lock:
            before = dict(self._settings[key])
            self._settings[key].update({k: v for k, v in patch.items() if v is not None})
            self.record_audit("system", "settings", key, before, dict(self._settings[key]))
            return self._settings[key]

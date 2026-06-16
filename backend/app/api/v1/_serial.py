"""Serialization helpers — turn registry/store objects into API response dicts.
Secrets are never included (only a configured/unset hint)."""
from __future__ import annotations

from typing import Any, Dict

from app.services import secrets


def model_view(m, store) -> Dict[str, Any]:
    d = m.model_dump(mode="json")
    d["model_id"] = m.id
    d["display_name"] = m.identity.display_name
    d["tier"] = m.classification.tier.value
    d["role"] = m.classification.role.value
    d["status"] = m.classification.status.value
    d["config"] = store.model_config(m.id)
    d["context_profile"] = store.context_profile(m.id)
    return d


def model_summary(m) -> Dict[str, Any]:
    return {
        "model_id": m.id,
        "display_name": m.identity.display_name,
        "provider": m.provider,
        "tier": m.classification.tier.value,
        "role": m.classification.role.value,
        "status": m.classification.status.value,
        "pricing": {"input": m.pricing.input, "output": m.pricing.output, "unit": "1M tokens"},
        "context_window": m.capability.context_window,
        "latency_class": m.classification.latency_class,
    }


def intent_view(i, store) -> Dict[str, Any]:
    tiers = store.intent_tier(i.id)
    return {
        "intent_id": i.id,
        "category": i.category,
        "name": i.name,
        "description": i.description,
        "complexity": i.complexity,
        "default_tier": tiers.get("default_tier"),
        "min_tier": tiers.get("min_tier"),
        "keywords": i.keywords or [],
    }


def provider_view(p: Dict[str, Any], store) -> Dict[str, Any]:
    pid = p["id"]
    models = [m.id for m in store.registry.models if m.provider == pid]
    auth = p.get("auth") or {}
    return {
        "provider_id": pid,
        "name": p.get("name"),
        "kind": p.get("kind"),
        "role": p.get("role"),
        "status": p.get("status"),
        "base_url": (p.get("api") or {}).get("base_url"),
        "api_key_hint": secrets.hint(auth.get("api_key_ref")),
        "rate_limit_rpm": p.get("rate_limit_rpm"),
        "rate_limit_tpm": p.get("rate_limit_tpm"),
        "models": models,
        "models_count": len(models),
    }


def rule_view(r: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(r)
    out.setdefault("rule_id", r.get("id"))
    out.setdefault("stats", {"matches_30d": 0})
    return out

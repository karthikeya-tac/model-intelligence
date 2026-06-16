"""EP19–25 — providers list/create/get/patch/delete, connectivity test, health."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.deps import get_store
from app.errors import not_found
from app.schemas.api import ProviderCreate, ProviderPatch
from app.services import health, secrets
from ._serial import model_summary, provider_view

router = APIRouter(tags=["providers"])


@router.get("/providers")
def list_providers(store=Depends(get_store)):
    out = []
    for p in store.providers():
        v = provider_view(p, store)
        h = health.provider_health(p)
        v["uptime"] = h["uptime_30d"]
        v["avg_latency_ms"] = h["avg_latency_ms"]
        out.append(v)
    return {"providers": out}


@router.post("/providers", status_code=201)
def create_provider(body: ProviderCreate, store=Depends(get_store)):
    pid = body.kind
    ref = f"${{{body.kind.upper()}_API_KEY}}"     # key stored only as an env ref; never the value
    provider = {
        "id": pid, "name": body.name or body.kind.title(), "kind": body.kind,
        "role": body.role, "status": "not_connected",
        "api": {"base_url": body.base_url or "", "style": "responses"},
        "auth": {"api_key_ref": ref},
    }
    store.create_provider(provider)
    return {"provider_id": pid, "connected": False, "api_key_hint": secrets.hint(ref)}


@router.get("/providers/health")
def providers_health(store=Depends(get_store)):
    rows = health.all_health(store.providers())
    fallbacks = sum(1 for _ in store.settings("fallback")["chains"])
    return {"providers": rows, "fallback_uses_30d": 0, "fallback_chains": fallbacks}


@router.get("/providers/{provider_id}")
def get_provider(provider_id: str, store=Depends(get_store)):
    p = store.provider(provider_id)
    if not p:
        raise not_found("provider", provider_id)
    return provider_view(p, store)


@router.patch("/providers/{provider_id}")
def patch_provider(provider_id: str, body: ProviderPatch, store=Depends(get_store)):
    p = store.patch_provider(provider_id, body.model_dump(exclude_none=True))
    if p is None:
        raise not_found("provider", provider_id)
    return {"updated": True, "provider_id": provider_id}


@router.delete("/providers/{provider_id}", status_code=204)
def delete_provider(provider_id: str, force: bool = Query(False), store=Depends(get_store)):
    if not store.provider(provider_id):
        raise not_found("provider", provider_id)
    refs = store.registry.models_for_provider(provider_id)
    if refs and not force:
        raise HTTPException(status_code=409,
                            detail=f"provider '{provider_id}' has {len(refs)} models; pass ?force=true")
    store.delete_provider(provider_id)
    return Response(status_code=204)


@router.post("/providers/{provider_id}/test")
def test_provider(provider_id: str, store=Depends(get_store)):
    p = store.provider(provider_id)
    if not p:
        raise not_found("provider", provider_id)
    configured = secrets.is_configured((p.get("auth") or {}).get("api_key_ref"))
    models = [m.id for m in store.registry.models_for_provider(provider_id)]
    return {"ok": configured, "configured": configured, "models_available": models}


@router.get("/providers/{provider_id}/models")
def provider_models(provider_id: str, store=Depends(get_store)):
    if not store.provider(provider_id):
        raise not_found("provider", provider_id)
    return {"models": [model_summary(m) for m in store.registry.models_for_provider(provider_id)]}

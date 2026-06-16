"""EP1–6, EP29–30 — models, config, benchmarks, usage, context profile."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.deps import get_store, get_telemetry
from app.errors import not_found
from app.schemas.api import ContextProfilePatch, ModelConfigPatch, ModelCreate
from ._serial import model_summary, model_view

router = APIRouter(tags=["models"])


@router.get("/models")
def list_models(
    q: Optional[str] = None, provider: Optional[str] = None,
    tier: Optional[str] = None, status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
    store=Depends(get_store),
):
    rows = store.registry.models
    if provider:
        rows = [m for m in rows if m.provider == provider]
    if tier:
        rows = [m for m in rows if m.classification.tier.value == tier]
    if status:
        rows = [m for m in rows if m.classification.status.value == status]
    if q:
        ql = q.lower()
        rows = [m for m in rows if ql in m.id.lower() or ql in m.identity.display_name.lower()]
    total = len(rows)
    page = rows[offset:offset + limit]
    # full model_view per item so the catalog cards have capability_scores, pricing, specs
    return {"total": total, "limit": limit, "offset": offset,
            "models": [model_view(m, store) for m in page]}


@router.get("/models/{model_id}")
def get_model(model_id: str, store=Depends(get_store)):
    m = store.registry.model(model_id)
    if not m:
        raise not_found("model", model_id)
    return model_view(m, store)


@router.post("/models", status_code=201)
def create_model(body: ModelCreate, store=Depends(get_store)):
    # Phase-0: registers config in the overlay (catalog itself is file-backed).
    mid = body.model_ref
    cfg = store.set_model_config(mid, {"tier": body.tier, "status": "preview",
                                       "provider": body.provider_id})
    return {"model_id": mid, "created": True, "config": cfg}


@router.patch("/models/{model_id}/config")
def patch_config(model_id: str, body: ModelConfigPatch, store=Depends(get_store)):
    if not store.registry.model(model_id) and not store.model_config(model_id):
        raise not_found("model", model_id)
    cfg = store.set_model_config(model_id, body.model_dump(exclude_none=True))
    return {"saved": True, "model_id": model_id, "config": cfg}


@router.get("/models/{model_id}/benchmarks")
def benchmarks(model_id: str, store=Depends(get_store), tele=Depends(get_telemetry)):
    m = store.registry.model(model_id)
    if not m:
        raise not_found("model", model_id)
    b = m.benchmarks.model_dump(mode="json") if m.benchmarks else {"capability_scores": {}, "standard": {}}
    u = tele.usage(model_id)
    return {
        "model_id": model_id,
        "capabilities": b.get("capability_scores", {}),
        "standard": b.get("standard", {}),
        "performance": {"avg_latency_ms": u["avg_latency_ms"], "requests": u["requests"]},
        "pricing": {"input": m.pricing.input, "output": m.pricing.output, "unit": "1M tokens"},
    }


@router.get("/models/{model_id}/usage")
def usage(model_id: str, period: str = "month", store=Depends(get_store), tele=Depends(get_telemetry)):
    if not store.registry.model(model_id):
        raise not_found("model", model_id)
    return tele.usage(model_id, period)


@router.get("/models/{model_id}/context-profile")
def get_context_profile(model_id: str, store=Depends(get_store)):
    prof = store.context_profile(model_id)
    if not prof:
        raise not_found("model", model_id)
    return prof


@router.patch("/models/{model_id}/context-profile")
def patch_context_profile(model_id: str, body: ContextProfilePatch, store=Depends(get_store)):
    if not store.context_profile(model_id):
        raise not_found("model", model_id)
    patch = body.model_dump(exclude_none=True)
    prof = store.context_profile(model_id)
    eff = patch.get("effective_window", prof["effective_window"])
    native = patch.get("native_window", prof["native_window"])
    if eff > native:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="effective_window must be ≤ native_window")
    return store.set_context_profile(model_id, patch)

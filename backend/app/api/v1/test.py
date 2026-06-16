"""EP17 compare · EP18 single — deterministic simulation (no provider calls)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_store
from app.errors import not_found
from app.routing.sim import simulate
from app.schemas.api import TestCompare, TestSingle

router = APIRouter(tags=["test"])


@router.post("/test/single")
def test_single(body: TestSingle, store=Depends(get_store)):
    m = store.registry.model(body.model_id)
    if not m:
        raise not_found("model", body.model_id)
    return simulate(m.model_dump(mode="json"), body.prompt, body.trust)


@router.post("/test/compare")
def test_compare(body: TestCompare, store=Depends(get_store)):
    results = []
    for mid in body.model_ids:
        m = store.registry.model(mid)
        if m:
            results.append(simulate(m.model_dump(mode="json"), body.prompt, body.trust))
    best = max(results, key=lambda r: r["value_score"], default=None)
    return {
        "results": results,
        "recommendation": (best or {}).get("model_id"),
        "reason": ("best value_score" if best else "no valid models"),
    }

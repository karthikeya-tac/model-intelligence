"""EP31 fit-check · EP32 compaction · EP33 budget."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_store
from app.schemas.api import BudgetPatch, CompactionPatch, FitCheck

router = APIRouter(tags=["context"])


@router.post("/context/fit-check")
def fit_check(body: FitCheck, store=Depends(get_store)):
    prompt_tokens = max(1, len(body.prompt) // 4) + (body.session_tokens or 0)
    results = []
    for mid in body.model_ids:
        prof = store.context_profile(mid)
        if not prof:
            results.append({"model_id": mid, "verdict": "unknown", "reason": "no context profile"})
            continue
        injected = prof["memory_budget_tokens"]
        total = prompt_tokens + injected
        eff = prof["effective_window"]
        floor = int(eff * prof["compaction_floor_pct"] / 100)
        if total <= floor:
            verdict = "fits"
        elif total <= eff:
            verdict = "compact"
        else:
            verdict = "overflow"
        results.append({"model_id": mid, "verdict": verdict, "injected_tokens": injected,
                        "prompt_tokens": prompt_tokens, "total_tokens": total, "window": eff})
    return {"results": results}


@router.get("/context/compaction")
def get_compaction(store=Depends(get_store)):
    return store.settings("compaction")


@router.patch("/context/compaction")
def patch_compaction(body: CompactionPatch, store=Depends(get_store)):
    return store.patch_settings("compaction", body.model_dump(exclude_none=True))


@router.get("/context/budget")
def get_budget(store=Depends(get_store)):
    return store.settings("budget")


@router.patch("/context/budget")
def patch_budget(body: BudgetPatch, store=Depends(get_store)):
    return store.patch_settings("budget", body.model_dump(exclude_none=True))

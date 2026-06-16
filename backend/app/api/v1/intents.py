"""EP7 list · EP8 patch tier · EP9 classify."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_router, get_store
from app.errors import not_found
from app.schemas.api import ClassifyRequest, ClassifyResponse, IntentTierPatch
from ._serial import intent_view

router = APIRouter(tags=["intents"])


@router.get("/intents")
def list_intents(store=Depends(get_store)):
    return {"intents": [intent_view(i, store) for i in store.registry.intents]}


@router.patch("/intents/{intent_id}")
def patch_intent(intent_id: str, body: IntentTierPatch, store=Depends(get_store)):
    if not store.registry.intent(intent_id):
        raise not_found("intent", intent_id)
    tiers = store.set_intent_tier(intent_id, body.default_tier, body.min_tier)
    return {"saved": True, "intent_id": intent_id, **tiers}


@router.post("/intents/classify", response_model=ClassifyResponse)
def classify(body: ClassifyRequest, store=Depends(get_store), engine=Depends(get_router)):
    c = engine.classify(body.prompt)
    intent = store.registry.intent(c["intent_id"]) if c["intent_id"] else None
    return {"intent_id": c["intent_id"], "category": intent.category if intent else None,
            "source": c["source"], "confidence": c["confidence"]}

"""The Console — one call powering the query playground.

POST /console/ask  → run the 2-layer router, return the chosen model + all its
related info + a cost/latency estimate, and (if the provider's key is configured)
the live output via a real stand-in model.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_router, get_store, get_telemetry
from app.routing import execute as ex
from app.routing.sim import simulate
from app.schemas.api import ConsoleAsk
from app.services import secrets
from ._serial import model_view

router = APIRouter(tags=["console"])


@router.post("/console/ask")
def ask(body: ConsoleAsk, engine=Depends(get_router), store=Depends(get_store), tele=Depends(get_telemetry)):
    decision = engine.route(
        prompt=body.prompt, intent_id=body.intent_id, agent=body.agent,
        workspace=body.workspace, session_tokens=body.session_tokens, profile=body.profile,
    )
    model = store.registry.model(decision.get("model_id")) if decision.get("model_id") else None
    model_detail = model_view(model, store) if model else None
    estimate = simulate(model.model_dump(mode="json"), body.prompt, "L1") if model else {}

    output = {"configured": False, "output": None, "real_model": None, "error": None}
    if model and body.execute:
        prov = store.registry.provider(model.provider)
        kind = prov.kind.value if prov else model.provider
        ref = prov.auth.api_key_ref if prov else None
        key = secrets.resolve(ref)
        output = ex.execute(kind, model.classification.tier.value, body.prompt, key)
        output["provider_kind"] = kind
        output["env_var"] = secrets.env_name(ref)

    tele.record(decision, cost_usd=estimate.get("cost_usd", 0.0),
                latency_ms=(output.get("latency_ms") or estimate.get("latency_ms", 0)))
    return {"decision": decision, "model": model_detail, "estimate": estimate, "output": output}

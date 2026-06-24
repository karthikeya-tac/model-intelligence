"""EP15 route (the 2-layer router) · EP16 routing stats."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_router, get_store, get_telemetry
from app.routing.sim import simulate
from app.schemas.api import RouteRequest, RouteResponse

router = APIRouter(tags=["routing"])


@router.post("/route", response_model=RouteResponse)
def route(body: RouteRequest, engine=Depends(get_router), store=Depends(get_store),
          tele=Depends(get_telemetry)):
    d = engine.route(
        prompt=body.prompt, intent_id=body.intent_id, agent=body.agent,
        workspace=body.workspace, session_tokens=body.session_tokens, step=body.step,
    )
    # record telemetry with the chosen model's simulated cost/latency
    cost, latency = 0.0, 0
    if d.get("model_id"):
        m = store.registry.model(d["model_id"])
        if m:
            sim = simulate(m.model_dump(mode="json"), body.prompt or "", "L1")
            cost, latency = sim["cost_usd"], sim["latency_ms"]
    d["agent"] = body.agent
    d["workspace"] = body.workspace
    tele.record(d, cost_usd=cost, latency_ms=latency)
    return d


@router.get("/routing/stats")
def routing_stats(tele=Depends(get_telemetry)):
    return tele.stats()

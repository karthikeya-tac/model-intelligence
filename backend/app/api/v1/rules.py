"""EP10 list · EP11 create · EP12 patch · EP13 delete · EP14 simulate."""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, Response

from app.deps import get_store, get_telemetry
from app.errors import not_found
from app.schemas.api import RuleCreate, RulePatch, RuleSimulate
from ._serial import rule_view

router = APIRouter(tags=["rules"])


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "rule"


@router.get("/rules")
def list_rules(status: Optional[str] = None, store=Depends(get_store)):
    return {"rules": [rule_view(r) for r in store.rules(status=status)]}


@router.post("/rules", status_code=201)
def create_rule(body: RuleCreate, store=Depends(get_store)):
    data = body.model_dump(exclude_none=True)
    data["id"] = data.get("id") or _slug(body.name)
    return {"created": True, "rule": rule_view(store.create_rule(data))}


@router.patch("/rules/{rule_id}")
def patch_rule(rule_id: str, body: RulePatch, store=Depends(get_store)):
    r = store.patch_rule(rule_id, body.model_dump(exclude_none=True))
    if r is None:
        raise not_found("rule", rule_id)
    return {"updated": True, "rule": rule_view(r)}


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: str, store=Depends(get_store)):
    if not store.delete_rule(rule_id):
        raise not_found("rule", rule_id)
    return Response(status_code=204)


@router.post("/rules/simulate")
def simulate_rule(body: RuleSimulate, store=Depends(get_store), tele=Depends(get_telemetry)):
    draft = body.rule_draft
    mb, mv = draft.get("match_by"), draft.get("match_value", {}) or {}
    # estimate match count over the seeded routing decisions
    decisions = tele.decisions
    def matches(d):
        if mb == "intent":
            return d.get("intent_id") == mv.get("intent_id")
        if mb == "agent":
            return d.get("agent") == mv.get("agent")
        if mb == "workspace":
            return d.get("workspace") == mv.get("workspace")
        return False
    hits = [d for d in decisions if matches(d)]
    match_count = len(hits)
    agents = sorted({d.get("agent") for d in hits if d.get("agent")})
    cost_now = sum(d["cost_usd"] for d in hits)
    # crude monthly delta: re-tiering to 'fast' saves ~70%, 'powerful' costs ~3x
    target = (draft.get("action") or {}).get("route_to_tier")
    factor = {"fast": 0.3, "standard": 0.7, "powerful": 3.0}.get(target, 1.0)
    cost_delta_monthly = round((cost_now * factor - cost_now) * 30, 2)
    return {
        "match_count": match_count,
        "match_count_daily": match_count,
        "cost_delta_monthly": cost_delta_monthly,
        "affected_agents": agents,
        "confidence": "medium" if match_count else "low",
    }

"""router_v2 — the candidate query→model router (experiment).

Pipeline: classify (embedding-first, top-k) → difficulty×complexity tier → deterministic rules
→ min_tier floor → uncertainty gate (escalate/widen) → multi-dimension Level-2 pick. Returns the
SAME decision shape as the live engine (plus additive fields) so the compare harness is
apples-to-apples and a later promotion into app/routing is a drop-in.

Reuses the live Store/Registry (same catalog) and ports the live deterministic rule resolution so
tier decisions differ ONLY because of the new query-aware layers, not because rules went missing.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from app.routing.selector import Features

from .classifier import IntentClassifier
from .difficulty import TIER_RANK, effective_tier
from .features import difficulty_score, extract_features
from .selector_v2 import MultiDimSelector

PRIORITY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
NEXT_TIER = {"fast": "standard", "standard": "powerful", "powerful": "powerful"}
CHARS_PER_TOKEN = 4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RouterV2:
    def __init__(self, store, *, config_path: Path, routes_path: Path):
        self.store = store
        self.cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
        self._models = [m.model_dump(mode="json") for m in store.registry.models]
        self.classifier = IntentClassifier(store.registry.intents, routes_path, self.cfg.get("classifier", {}))
        self.selector = MultiDimSelector(self.cfg)
        self._tier_window = {}
        for t in ("fast", "standard", "powerful"):
            wins = [m["capability"]["context_window"] for m in self._models if m["classification"]["tier"] == t]
            self._tier_window[t] = max(wins) if wins else 200000

    @property
    def classifier_mode(self) -> str:
        return self.classifier.mode

    # ---- rules (ported deterministic resolution) ----
    def _rule_matches(self, r, prompt, intent_id, agent, workspace, session_pct) -> bool:
        if r.get("status") != "active":
            return False
        if r.get("type") == "timed" and r.get("expires_at") and _now_iso() > r["expires_at"]:
            return False
        mb, mv = r.get("match_by"), r.get("match_value", {}) or {}
        if mb == "intent":
            return intent_id is not None and intent_id == mv.get("intent_id")
        if mb == "keyword":
            t = (prompt or "").lower()
            return any(str(k).lower() in t for k in mv.get("keywords", []))
        if mb == "agent":
            return agent is not None and agent == mv.get("agent")
        if mb == "workspace":
            return workspace is not None and workspace == mv.get("workspace")
        if mb == "session_size":
            thr = mv.get("session_pct_of_window_gt")
            return session_pct is not None and thr is not None and session_pct > thr
        return False

    # ---- the route ----
    def route(self, *, prompt: Optional[str] = None, intent_id: Optional[str] = None,
              agent: Optional[str] = None, workspace: Optional[str] = None,
              session_tokens: Optional[int] = None) -> Dict[str, Any]:
        notes: List[str] = []

        # 1. classify (embedding-first, top-k)
        if intent_id:
            source, confidence, margin = "explicit", 1.0, 1.0
            intents_topk = [(intent_id, 1.0)]
        elif prompt:
            c = self.classifier.classify(prompt)
            intent_id, source, confidence, margin = c["intent_id"], c["source"], c["confidence"], c["margin"]
            intents_topk = c["intents"]
        else:
            source, confidence, margin, intents_topk = "none", 0.0, 0.0, []

        intent_obj = self.store.registry.intent(intent_id) if intent_id else None
        base_tier = intent_obj.default_tier.value if intent_obj else "standard"
        min_tier = intent_obj.min_tier.value if intent_obj else "fast"
        complexity = intent_obj.complexity if intent_obj else None

        # 2. query features + difficulty
        feats = extract_features(prompt or "", intent_matched=intent_id is not None)
        diff = difficulty_score(feats, self.cfg.get("difficulty", {}))

        # 3. difficulty × complexity → tier (raise-only vs intent default)
        tier, dnotes = effective_tier(base_tier, complexity, diff, self.cfg)
        notes.extend(dnotes)

        session_pct = round(session_tokens / max(1, self._tier_window.get(tier, 200000)) * 100, 1) if session_tokens else None

        # 4. deterministic rules (same as baseline)
        applied: List[dict] = []
        route_tier: Optional[str] = None
        boosts: List[str] = []
        limits: List[str] = []
        redirect_model = None
        long_context = False
        cost_cap = None
        for r in sorted(self.store.rules(), key=lambda x: -PRIORITY_RANK.get(x.get("priority", "LOW"), 0)):
            if not self._rule_matches(r, prompt or "", intent_id, agent, workspace, session_pct):
                continue
            a, rtype = r.get("action", {}) or {}, r.get("type")
            if rtype in ("route", "timed") and a.get("route_to_tier") in TIER_RANK and route_tier is None:
                route_tier = a["route_to_tier"]
            elif rtype == "boost" and a.get("min_tier") in TIER_RANK:
                boosts.append(a["min_tier"])
            elif rtype == "boost" and a.get("boost_to_long_context"):
                long_context = True
            elif rtype == "limit" and a.get("max_tier") in TIER_RANK:
                limits.append(a["max_tier"])
            elif rtype == "redirect" and a.get("redirect_to_model"):
                redirect_model = a["redirect_to_model"]
            elif rtype == "cost_cap":
                cost_cap = a.get("max_cost_per_request_usd")
            applied.append({"rule_id": r["id"], "name": r.get("name"), "type": rtype, "action": a})
        if route_tier:
            tier = route_tier
        for t in boosts:
            if TIER_RANK[tier] < TIER_RANK[t]:
                tier = t
        for t in limits:
            if TIER_RANK[tier] > TIER_RANK[t]:
                tier = t

        # 5. min_tier floor
        if TIER_RANK[tier] < TIER_RANK.get(min_tier, 0):
            tier, _ = min_tier, notes.append(f"raised to min_tier {min_tier}")

        # 6. uncertainty gate
        esc = self.cfg.get("escalation", {}) or {}
        escalated, pool_tiers = False, [tier]
        if esc.get("enabled", True) and not route_tier:   # an explicit route rule wins over escalation
            lo, hi = esc.get("borderline_difficulty", [0.30, 0.42])
            borderline = lo <= diff <= hi
            if (confidence < esc.get("low_confidence", 0.45)) or borderline:
                capped = limits and min(limits, key=lambda t: TIER_RANK[t])
                raised = NEXT_TIER[tier]
                if not capped or TIER_RANK[raised] <= TIER_RANK[capped]:
                    if TIER_RANK[raised] > TIER_RANK[tier]:
                        tier = raised
                        notes.append(f"escalated (conf {confidence:.2f}, diff {diff:.2f})")
                escalated = True
                if esc.get("widen_pool", True):
                    pool_tiers = sorted({tier, NEXT_TIER[tier]}, key=lambda t: TIER_RANK[t])

        # 7. fuse top-k intents → need-vector
        need = self._fuse_need(intents_topk)

        # 8. Level-2 pick (redirect short-circuits if the target exists)
        est_in = max(1, len(prompt or "") // CHARS_PER_TOKEN) + (session_tokens or 0)
        feats2 = Features(min_context=400000 if long_context else 0, est_input_tokens=est_in, est_output_tokens=600)
        redirect_hit = next((x for x in self._models if x["id"] == redirect_model), None) if redirect_model else None
        if redirect_model and redirect_hit is None:
            notes.append(f"ignored redirect to unknown model '{redirect_model}'")
        if redirect_hit is not None:
            chosen, provider, candidates = redirect_hit["id"], redirect_hit.get("provider"), []
            notes.append(f"redirected to {chosen}")
        else:
            ranked = self.selector.select(tier, intent_id, self._models, features=feats2,
                                          budget_usd=cost_cap, dimensions=need, pool_tiers=pool_tiers)
            notes.extend(self.selector.last_notes)
            top = ranked[0] if ranked else None
            chosen = top.model if top else None
            provider = top.provider if top else None
            candidates = [{"model_id": r.model, "provider": r.provider, "score": r.score,
                           "quality": r.quality, "cost": r.cost, "latency": r.latency,
                           "available": r.available, "note": r.note} for r in ranked[:5]]

        reason = self._reason(intent_id, source, base_tier, tier, applied, chosen, candidates, diff, notes)
        return {
            "intent_id": intent_id, "intent_source": source, "confidence": confidence,
            "base_tier": base_tier, "tier": tier, "model_id": chosen, "provider": provider,
            "matched_rules": applied, "candidates": candidates, "session_pct": session_pct,
            "escalated": escalated, "reason": reason,
            # --- additive (router_v2) ---
            "intents": [{"intent_id": i, "confidence": c} for i, c in intents_topk],
            "difficulty": diff, "need_vector": need, "features": feats.as_dict(),
            "classifier_mode": self.classifier_mode,
        }

    def _fuse_need(self, intents_topk) -> Dict[str, float]:
        dims_map = self.cfg.get("intent_dimensions", {}) or {}
        if not intents_topk:
            return self.selector.resolve_dimensions(None)
        top_conf = intents_topk[0][1]
        sec_margin = float((self.cfg.get("classifier", {}).get("semantic", {}) or {}).get("secondary_margin", 0.2))
        need: Dict[str, float] = {}
        for iid, conf in intents_topk:
            if conf < top_conf - sec_margin:
                continue
            for d, w in (dims_map.get(iid) or {}).items():
                need[d] = need.get(d, 0.0) + conf * w
        return need or self.selector.resolve_dimensions(intents_topk[0][0])

    def _reason(self, intent_id, source, base_tier, tier, applied, chosen, candidates, diff, notes) -> str:
        bits = [f"intent={intent_id or 'unknown'} ({source})",
                f"difficulty={diff:.2f}",
                f"tier={base_tier}" + (f"→{tier}" if tier != base_tier else "")]
        if applied:
            bits.append("rules: " + ", ".join(a["rule_id"] for a in applied))
        if chosen:
            top = candidates[0] if candidates else None
            bits.append(f"model={chosen}" + (f" (fit {top['quality']:.2f})" if top else ""))
        if notes:
            bits.append("; ".join(notes))
        return " | ".join(bits)

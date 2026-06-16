"""RouterService — the hybrid 2-layer router behind POST /route (EP15).

Level 1  : classify prompt → intent (keyword by default; semantic if SEMANTIC=1)
           → intent's default_tier (min_tier floor) → apply active rules by priority
           → (optional) Architect-Mode plan/exec tier split.
Level 2  : ScoringSelector ranks the models in the final tier (quality·cost·latency)
           → best pick + failover order.

Reads LIVE state from the store (rules, intent tier overrides) so edits take effect
immediately. Catalog model facts come from the registry snapshot.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .selector import Features, ScoringSelector

TIER_RANK = {"fast": 0, "standard": 1, "powerful": 2}
PRIORITY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
CHARS_PER_TOKEN = 4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RouterService:
    def __init__(self, store, *, selection_path: Path, routes_path: Path, semantic: bool = False):
        self.store = store
        self.selector = ScoringSelector(selection_path)
        self._routes_path = routes_path
        self._want_semantic = semantic
        self._semantic = None
        self.refresh()
        if semantic:
            self._try_build_semantic()

    # rebuild catalog views from the (possibly reloaded) registry snapshot
    def refresh(self) -> None:
        reg = self.store.registry
        self._models = [m.model_dump(mode="json") for m in reg.models]
        self._intents = reg.intents
        self._tier_window = {}
        for t in ("fast", "standard", "powerful"):
            wins = [m["capability"]["context_window"] for m in self._models
                    if m["classification"]["tier"] == t]
            self._tier_window[t] = max(wins) if wins else 200000

    # ----- optional semantic Level-1 (lazy, graceful) ----------------------
    def _try_build_semantic(self) -> None:
        try:
            import numpy as np
            import yaml
            from sentence_transformers import SentenceTransformer
        except Exception:
            self._semantic = None
            return
        routes = (yaml.safe_load(self._routes_path.read_text()) or {}).get("routes", {})
        enc = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        mat = {name: np.asarray(enc.encode(list(u), normalize_embeddings=True)) for name, u in routes.items()}
        self._semantic = (enc, mat, np)

    def _semantic_match(self, prompt: str):
        enc, mat, np = self._semantic
        q = enc.encode([prompt], normalize_embeddings=True)[0]
        best, second = (-1.0, None), (-1.0, None)
        for name, m in mat.items():
            s = float((m @ q).max())
            if s > best[0]:
                second, best = best, (s, name)
            elif s > second[0]:
                second = (s, name)
        if best[1] and best[0] >= 0.15 and (best[0] - second[0]) >= 0.03:
            return best[1], f"semantic {best[0]:.2f}"
        return None, None

    # ----- Level 1: classify -----------------------------------------------
    def _keyword_classify(self, prompt: str) -> Optional[str]:
        text = prompt.lower()
        best_id, best_score = None, (0, 0)
        for intent in self._intents:
            matched = [kw for kw in (intent.keywords or []) if kw in text]
            score = (len(matched), max((len(kw) for kw in matched), default=0))
            if score > best_score:
                best_id, best_score = intent.id, score
        return best_id

    def classify(self, prompt: str) -> Dict[str, Any]:
        if self._semantic:
            name, src = self._semantic_match(prompt)
            if name:
                return {"intent_id": name, "source": src, "confidence": 0.8}
        kw = self._keyword_classify(prompt)
        if kw:
            return {"intent_id": kw, "source": "keyword", "confidence": 0.6}
        return {"intent_id": None, "source": "none", "confidence": 0.0}

    # ----- rule matching ----------------------------------------------------
    def _rule_matches(self, r: dict, prompt: str, intent_id, agent, workspace, session_pct) -> bool:
        if r.get("status") != "active":
            return False
        if r.get("type") == "timed" and r.get("expires_at"):
            if _now_iso() > r["expires_at"]:
                return False
        mb, mv = r.get("match_by"), r.get("match_value", {}) or {}
        if mb == "intent":
            return intent_id is not None and intent_id == mv.get("intent_id")
        if mb == "keyword":
            text = (prompt or "").lower()
            return any(str(kw).lower() in text for kw in mv.get("keywords", []))
        if mb == "agent":
            return agent is not None and agent == mv.get("agent")
        if mb == "workspace":
            return workspace is not None and workspace == mv.get("workspace")
        if mb == "session_size":
            thr = mv.get("session_pct_of_window_gt")
            return session_pct is not None and thr is not None and session_pct > thr
        return False

    # ----- the route --------------------------------------------------------
    def route(self, *, prompt: Optional[str] = None, intent_id: Optional[str] = None,
              agent: Optional[str] = None, workspace: Optional[str] = None,
              session_tokens: Optional[int] = None, profile: Optional[str] = None,
              step: Optional[str] = None) -> Dict[str, Any]:
        notes: List[str] = []

        # 1. intent
        if intent_id:
            source, confidence = "explicit", 1.0
        elif prompt:
            c = self.classify(prompt)
            intent_id, source, confidence = c["intent_id"], c["source"], c["confidence"]
        else:
            source, confidence = "none", 0.0

        tiers = self.store.intent_tier(intent_id) if intent_id else {}
        base_tier = tiers.get("default_tier", "standard")
        min_tier = tiers.get("min_tier", "fast")
        tier = base_tier

        # session pct of the base-tier window
        session_pct = None
        if session_tokens:
            session_pct = round(session_tokens / max(1, self._tier_window.get(tier, 200000)) * 100, 1)

        # 2. rules — collect matches, then resolve DETERMINISTICALLY (order-independent).
        # Resolution: route/timed sets the base → strongest boost (highest min_tier) raises →
        # strongest limit (lowest max_tier) caps → intent min_tier floor (step 4). The outcome
        # no longer depends on the order rules happened to match in. Invalid tier values are
        # skipped with a note instead of raising KeyError.
        applied: List[dict] = []
        route_tier: Optional[str] = None     # from the highest-priority route/timed rule
        boosts: List[str] = []               # min_tier floors requested by boost rules
        limits: List[str] = []               # max_tier ceilings requested by limit rules
        redirect_model = None
        long_context = False
        cost_cap = None

        def _valid_tier(t) -> bool:
            if t in TIER_RANK:
                return True
            notes.append(f"ignored rule action: invalid tier '{t}'")
            return False

        for r in sorted(self.store.rules(), key=lambda x: -PRIORITY_RANK.get(x.get("priority", "LOW"), 0)):
            if not self._rule_matches(r, prompt or "", intent_id, agent, workspace, session_pct):
                continue
            action = r.get("action", {}) or {}
            rtype = r.get("type")
            if rtype in ("route", "timed") and "route_to_tier" in action:
                t = action["route_to_tier"]
                if _valid_tier(t) and route_tier is None:   # highest priority wins (first match)
                    route_tier = t
            elif rtype == "boost" and "min_tier" in action:
                t = action["min_tier"]
                if _valid_tier(t):
                    boosts.append(t)
            elif rtype == "boost" and action.get("boost_to_long_context"):
                long_context = True
            elif rtype == "limit" and "max_tier" in action:
                t = action["max_tier"]
                if _valid_tier(t):
                    limits.append(t)
            elif rtype == "redirect" and "redirect_to_model" in action:
                redirect_model = action["redirect_to_model"]
            elif rtype == "cost_cap":
                cost_cap = action.get("max_cost_per_request_usd")
            applied.append({"rule_id": r["id"], "name": r.get("name"), "type": rtype, "action": action})

        # deterministic tier resolution (independent of rule match order)
        if route_tier is not None:
            tier = route_tier
        for t in boosts:                       # raise to the strongest floor
            if TIER_RANK[tier] < TIER_RANK[t]:
                tier = t
        for t in limits:                       # cap to the strongest ceiling
            if TIER_RANK[tier] > TIER_RANK[t]:
                tier = t

        # 3. architect mode (plan→powerful, exec→fast/standard)
        arch = self.store.settings("architect_mode")
        if arch.get("enabled") and step in ("plan", "exec"):
            tier = arch["plan_tier"] if step == "plan" else arch["exec_tier"]
            notes.append(f"architect-mode {step} → {tier}")

        # 4. min_tier floor
        if TIER_RANK[tier] < TIER_RANK.get(min_tier, 0):
            tier = min_tier
            notes.append(f"raised to min_tier {min_tier}")

        # 5. Level-2 model pick
        est_in = max(1, len((prompt or "")) // CHARS_PER_TOKEN) + (session_tokens or 0)
        feats = Features(min_context=400000 if long_context else 0,
                         est_input_tokens=est_in, est_output_tokens=600)
        redirect_hit = next((x for x in self._models if x["id"] == redirect_model), None) if redirect_model else None
        if redirect_model and redirect_hit is None:
            notes.append(f"ignored redirect to unknown model '{redirect_model}'")
        if redirect_hit is not None:
            chosen, candidates = redirect_hit["id"], []
            provider = redirect_hit.get("provider")
            notes.append(f"redirected to {chosen}")
        else:
            ranked = self.selector.select(tier, intent_id, self._models, features=feats,
                                          profile=profile, budget_usd=cost_cap)
            notes.extend(self.selector.last_notes)
            top = ranked[0] if ranked else None
            chosen = top.model if top else None
            provider = top.provider if top else None
            candidates = [{"model_id": r.model, "provider": r.provider, "score": r.score,
                           "quality": r.quality, "cost": r.cost, "latency": r.latency,
                           "available": r.available} for r in ranked[:5]]

        reason = self._reason(intent_id, source, base_tier, tier, applied, chosen, candidates, notes)
        return {
            "intent_id": intent_id, "intent_source": source, "confidence": confidence,
            "base_tier": base_tier, "tier": tier, "model_id": chosen, "provider": provider,
            "matched_rules": applied, "candidates": candidates,
            "session_pct": session_pct, "escalated": False, "reason": reason,
            "profile": profile or self.selector.default_profile,
        }

    def _reason(self, intent_id, source, base_tier, tier, applied, chosen, candidates, notes) -> str:
        bits = [f"intent={intent_id or 'unknown'} ({source})", f"tier={base_tier}" + (f"→{tier}" if tier != base_tier else "")]
        if applied:
            bits.append("rules: " + ", ".join(a["rule_id"] for a in applied))
        if chosen:
            top = candidates[0] if candidates else None
            if top:
                bits.append(f"model={chosen} (q {top['quality']:.2f}·c {top['cost']:.2f}·l {top['latency']:.2f})")
            else:
                bits.append(f"model={chosen}")
        if notes:
            bits.append("; ".join(notes))
        return " | ".join(bits)

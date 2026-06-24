"""Level-1 intent classifier — embedding-first, calibrated, top-k.

DEFAULT path: MiniLM sentence embeddings vs the routes.yaml utterances, with cosine→confidence
via a temperature softmax (calibrated, not the live router's hard-coded 0.6/0.8). Returns a
ranked top-k of intents so Level-2 can fuse multiple capabilities.

If sentence-transformers / the model is unavailable, it falls back LOUDLY to keyword matching
(same signal the baseline uses) so the experiment still runs and stays deterministic.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

log = logging.getLogger("router_v2.classifier")


class IntentClassifier:
    def __init__(self, intents, routes_path: Path, cfg: Dict):
        self._intents = list(intents)                      # registry Intent objects (id, keywords)
        self._kw = {i.id: [k.lower() for k in (i.keywords or [])] for i in self._intents}
        self.cfg = cfg or {}
        sem = self.cfg.get("semantic", {}) or {}
        self.temperature = float(sem.get("temperature", 0.08))
        self.sim_floor = float(sem.get("sim_floor", 0.25))
        self.margin = float(sem.get("margin", 0.04))
        self.top_k = int(sem.get("top_k", 3))
        self.kw_conf = float((self.cfg.get("keyword", {}) or {}).get("base_confidence", 0.5))
        self._np = None
        self._enc = None
        self._mat: Dict[str, "any"] = {}
        if sem.get("enabled", True):
            self._build_semantic(Path(routes_path), sem.get("model", "sentence-transformers/all-MiniLM-L6-v2"))

    # ---- semantic build (deterministic; loud fallback) ----
    def _build_semantic(self, routes_path: Path, model_name: str) -> None:
        try:
            import numpy as np
            from sentence_transformers import SentenceTransformer
        except Exception as e:  # dep missing → keyword fallback
            log.warning("router_v2: embeddings unavailable (%s) — using KEYWORD fallback.", e)
            return
        try:
            routes = (yaml.safe_load(routes_path.read_text(encoding="utf-8")) or {}).get("routes", {})
            enc = SentenceTransformer(model_name)
            self._mat = {name: np.asarray(enc.encode(list(u), normalize_embeddings=True))
                         for name, u in routes.items() if u}
            self._enc, self._np = enc, np
            log.info("router_v2: semantic classifier ready (%d routes, %s).", len(self._mat), model_name)
        except Exception as e:
            log.warning("router_v2: semantic build failed (%s) — using KEYWORD fallback.", e)
            self._enc = None

    @property
    def mode(self) -> str:
        return "semantic" if self._enc is not None else "keyword"

    # ---- keyword fallback (deterministic, same signal as baseline) ----
    def _keyword_rank(self, prompt: str) -> List[Tuple[str, float]]:
        t = (prompt or "").lower()
        scored = []
        for iid, kws in self._kw.items():
            matched = [k for k in kws if k in t]
            if matched:
                # score by (#hits, longest hit) → squashed into a 0..1-ish confidence
                strength = min(1.0, 0.4 + 0.2 * len(matched) + 0.01 * max(len(k) for k in matched))
                scored.append((iid, round(self.kw_conf * strength + (1 - self.kw_conf) * (len(matched) >= 2), 4)))
        scored.sort(key=lambda x: -x[1])
        return scored

    # ---- the API ----
    def classify(self, prompt: str) -> Dict:
        if self._enc is not None:
            ranked = self._semantic_rank(prompt)
            if ranked and ranked[0][1] >= self.sim_floor:    # sim_floor is on RAW cosine (see below)
                return self._finalize(prompt, ranked, source="semantic")
        kw = self._keyword_rank(prompt)
        if kw:
            return {"intent_id": kw[0][0], "intents": kw[:self.top_k],
                    "confidence": kw[0][1], "margin": (kw[0][1] - (kw[1][1] if len(kw) > 1 else 0.0)),
                    "source": "keyword"}
        return {"intent_id": None, "intents": [], "confidence": 0.0, "margin": 0.0, "source": "none"}

    def _semantic_rank(self, prompt: str) -> List[Tuple[str, float]]:
        """Return [(intent_id, raw_cosine)] sorted desc — raw cosine, pre-softmax."""
        np = self._np
        q = self._enc.encode([prompt or ""], normalize_embeddings=True)[0]
        sims = [(name, float((mat @ q).max())) for name, mat in self._mat.items()]
        sims.sort(key=lambda x: -x[1])
        return sims

    def _finalize(self, prompt: str, ranked: List[Tuple[str, float]], *, source: str) -> Dict:
        np = self._np
        top_cos = ranked[0][1]
        second_cos = ranked[1][1] if len(ranked) > 1 else 0.0
        # softmax over per-intent cosines → calibrated confidences
        cos = np.array([c for _, c in ranked], dtype=float)
        z = np.exp((cos - cos.max()) / max(1e-6, self.temperature))
        probs = z / z.sum()
        intents = [(ranked[i][0], round(float(probs[i]), 4)) for i in range(min(self.top_k, len(ranked)))]
        return {
            "intent_id": ranked[0][0],
            "intents": intents,
            "confidence": round(float(probs[0]), 4),
            "margin": round(top_cos - second_cos, 4),
            "source": source,
        }

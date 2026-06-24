"""Oracle + a shared quality metric, both grounded ONLY in real capability_scores.

`quality_for(model, need)` scores a model against a need-vector (gold intent's capability blend).
`oracle_best` is the highest-quality ACTIVE model ignoring the tier gate — the ceiling a perfect
router could reach on the same real data. Both baseline and candidate picks are scored by the SAME
`quality_for` under the SAME gold need, so the quality comparison is fair.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple


def _scores(m: dict) -> Dict[str, int]:
    return (m.get("benchmarks", {}) or {}).get("capability_scores", {}) or {}


def quality_for(m: dict, need: Dict[str, float], pool_mean: float) -> float:
    cs = _scores(m)
    present = {d: w for d, w in need.items() if d in cs}
    if present:
        wsum = sum(present.values()) or 1.0
        return sum((cs[d] / 100.0) * w for d, w in present.items()) / wsum
    if "reasoning" in cs:
        return cs["reasoning"] / 100.0 * 0.9
    return pool_mean * 0.9


def pool_mean_quality(models: List[dict]) -> float:
    vals = [v for m in models for v in _scores(m).values()]
    return (sum(vals) / len(vals) / 100.0) if vals else 0.5


def oracle_best(models: List[dict], need: Dict[str, float]) -> Tuple[Optional[str], float]:
    pm = pool_mean_quality(models)
    best: Tuple[Optional[str], float] = (None, -1.0)
    for m in models:
        if (m.get("classification", {}) or {}).get("status") != "active":
            continue
        q = quality_for(m, need, pm)
        if q > best[1]:
            best = (m["id"], q)
    return best


def normalize(d: Dict[str, float]) -> Dict[str, float]:
    tot = sum(v for v in d.values() if v > 0) or 1.0
    return {k: v / tot for k, v in d.items() if v > 0}

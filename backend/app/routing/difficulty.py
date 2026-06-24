"""(intent.complexity prior) × (query difficulty evidence) → base tier.

Uses the intents.yaml `complexity:1-5` field. difficulty (0..1, from the query) nudges the
complexity prior up/down, then a complexity→tier map gives a base tier. RAISE-ONLY vs the
intent's default_tier (an easy phrasing never demotes a heavy intent); the engine still applies
rules + the min_tier floor afterwards.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

TIER_RANK = {"fast": 0, "standard": 1, "powerful": 2}


def _delta(difficulty: float, cfg: Dict) -> int:
    for bound, d in cfg.get("delta_bands", [[0.25, -1], [0.65, 0], [0.85, 1]]):
        if difficulty < bound:
            return int(d)
    return int(cfg.get("delta_high", 2))


def effective_tier(default_tier: str, complexity: Optional[int], difficulty: float,
                   cfg: Dict) -> Tuple[str, List[str]]:
    """Return (tier, notes). cfg is the selection config (root): reads complexity_tier_map,
    allow_demote, and difficulty.delta_*."""
    notes: List[str] = []
    tier_map = {int(k): v for k, v in (cfg.get("complexity_tier_map") or {}).items()}
    if not tier_map:
        tier_map = {1: "fast", 2: "fast", 3: "standard", 4: "powerful", 5: "powerful"}
    allow_demote = bool(cfg.get("allow_demote", False))

    prior = complexity if complexity is not None else 3
    eff = max(1, min(5, prior + _delta(difficulty, cfg.get("difficulty", {}))))
    suggestion = tier_map.get(eff, default_tier)

    if allow_demote:
        tier = suggestion
    else:
        tier = suggestion if TIER_RANK[suggestion] > TIER_RANK[default_tier] else default_tier

    if tier != default_tier:
        notes.append(f"difficulty {difficulty:.2f} · complexity {prior}→{eff} ⇒ {default_tier}→{tier}")
    return tier, notes

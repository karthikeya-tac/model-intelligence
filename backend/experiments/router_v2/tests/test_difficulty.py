from experiments.router_v2.difficulty import effective_tier

CFG = {
    "complexity_tier_map": {1: "fast", 2: "fast", 3: "standard", 4: "powerful", 5: "powerful"},
    "allow_demote": False,
    "difficulty": {"delta_bands": [[0.25, -1], [0.65, 0], [0.85, 1]], "delta_high": 2},
}


def test_hard_query_raises_tier():
    tier, _ = effective_tier("fast", 3, 0.95, CFG)   # complexity 3 + 2 = 5 → powerful
    assert tier == "powerful"


def test_easy_phrasing_never_demotes_heavy_intent():
    tier, _ = effective_tier("powerful", 5, 0.05, CFG)
    assert tier == "powerful"


def test_easy_query_holds_default_when_demote_disabled():
    tier, _ = effective_tier("standard", 3, 0.05, CFG)   # eff 2 → fast, but raise-only
    assert tier == "standard"


def test_null_complexity_uses_neutral_prior():
    tier, _ = effective_tier("fast", None, 0.1, CFG)     # prior 3, low diff → eff 2 → fast
    assert tier == "fast"

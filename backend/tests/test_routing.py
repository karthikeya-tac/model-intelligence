"""Unit tests for the live routing engine (app/routing) — query features, difficulty→tier,
multi-dimension selection, and route determinism/shape. Model-free + keyword mode → fast."""
from pathlib import Path

from app.config import settings
from app.routing.difficulty import effective_tier
from app.routing.engine import RouterService
from app.routing.features import difficulty_score, extract_features
from app.routing.selector import ScoringSelector
from app.store.file_store import FileStore

CFG_DIR = Path(settings.config_dir)
_DIFF_CFG = {
    "complexity_tier_map": {1: "fast", 2: "fast", 3: "standard", 4: "powerful", 5: "powerful"},
    "allow_demote": False,
    "difficulty": {"delta_bands": [[0.25, -1], [0.65, 0], [0.85, 1]], "delta_high": 2},
}


# ---- features / difficulty ----
def test_code_and_math_detection():
    assert extract_features("```python\ndef f():\n    return 1\n```").has_code
    assert extract_features("solve 2 + 2 = x").has_math


def test_difficulty_monotonic():
    easy = difficulty_score(extract_features("hi there"), {})
    hard = difficulty_score(extract_features(
        "design a distributed rate limiter; it must be thread-safe, handle backpressure, "
        "then add tests and ensure exactly-once"), {})
    assert hard > easy


def test_effective_tier_raise_only_and_hard_escalates():
    assert effective_tier("powerful", 5, 0.05, _DIFF_CFG)[0] == "powerful"   # never demote
    assert effective_tier("fast", 3, 0.95, _DIFF_CFG)[0] == "powerful"        # hard raises
    assert effective_tier("standard", 3, 0.05, _DIFF_CFG)[0] == "standard"    # easy holds default


# ---- multi-dimension selector ----
def _m(mid, scores, inp=1.0, out=2.0, tier="standard", status="active", role="alternative"):
    return {"id": mid, "provider": "p",
            "classification": {"tier": tier, "status": status, "role": role, "latency_class": "fast"},
            "capability": {}, "pricing": {"input": inp, "output": out},
            "benchmarks": {"capability_scores": scores}}


def _selector():
    return ScoringSelector(CFG_DIR / "selection.yaml")


def test_selector_picks_highest_capability():
    r = _selector().select("standard", "x", [_m("lo", {"a": 60}), _m("hi", {"a": 92})], dimensions={"a": 1.0})
    assert r[0].model == "hi"


def test_selector_blend_shifts_winner():
    models = [_m("good_a", {"a": 92, "b": 50}), _m("good_b", {"a": 50, "b": 92})]
    r = _selector().select("standard", "x", models, dimensions={"a": 0.2, "b": 0.8})
    assert r[0].model == "good_b"


def test_selector_missing_dim_renormalized_not_imputed():
    r = _selector().select("standard", "x", [_m("only_a", {"a": 80})], dimensions={"a": 0.5, "b": 0.5})
    assert abs(r[0].quality - 0.80) < 1e-6


def test_selector_standby_below_active():
    models = [_m("standby_hi", {"a": 99}, status="standby"), _m("active_lo", {"a": 70})]
    r = _selector().select("standard", "x", models, dimensions={"a": 1.0})
    assert r[0].model == "active_lo"


# ---- engine (keyword mode) ----
def _engine():
    store = FileStore(settings.config_dir, source_mode=settings.registry_mode)
    return RouterService(store, selection_path=CFG_DIR / "selection.yaml",
                         routes_path=CFG_DIR / "routes.yaml", semantic=False)


def test_route_is_deterministic():
    eng = _engine()
    a = eng.route(prompt="write a function to merge two sorted lists")
    b = eng.route(prompt="write a function to merge two sorted lists")
    assert a == b


def test_route_shape_and_valid_tier():
    eng = _engine()
    d = eng.route(prompt="design a fault-tolerant payment architecture")
    for k in ("intent_id", "intent_source", "confidence", "base_tier", "tier", "model_id",
              "provider", "matched_rules", "candidates", "escalated", "reason", "difficulty", "intents"):
        assert k in d, f"missing field {k}"
    assert d["tier"] in ("fast", "standard", "powerful")
    if d["candidates"]:
        for k in ("model_id", "quality", "cost", "latency", "available"):
            assert k in d["candidates"][0]


def test_easy_smalltalk_is_cheap():
    assert _engine().route(prompt="hi there")["tier"] == "fast"

from experiments.router_v2.selector_v2 import MultiDimSelector

CFG = {"intent_dimensions": {"x": {"a": 1.0}}, "latency_scores": {"fast": 0.8},
       "default_latency_score": 0.5, "quality_tie_epsilon": 0.05, "output_weight": 3.0}


def _m(mid, scores, inp=1.0, out=2.0, tier="standard", status="active", role="alternative"):
    return {"id": mid, "provider": "p",
            "classification": {"tier": tier, "status": status, "role": role, "latency_class": "fast"},
            "capability": {}, "pricing": {"input": inp, "output": out},
            "benchmarks": {"capability_scores": scores}}


def test_picks_highest_capability():
    sel = MultiDimSelector(CFG)
    r = sel.select("standard", "x", [_m("lo", {"a": 60}), _m("hi", {"a": 92})], dimensions={"a": 1.0})
    assert r[0].model == "hi"


def test_multidimension_blend_shifts_winner():
    sel = MultiDimSelector(CFG)
    models = [_m("good_a", {"a": 92, "b": 50}), _m("good_b", {"a": 50, "b": 92})]
    # need weighted toward b → good_b wins
    r = sel.select("standard", "x", models, dimensions={"a": 0.2, "b": 0.8})
    assert r[0].model == "good_b"


def test_missing_dimension_is_renormalized_not_imputed():
    sel = MultiDimSelector(CFG)
    # need {a:0.5,b:0.5} but model only has 'a' → quality should be a/100, not halved
    r = sel.select("standard", "x", [_m("only_a", {"a": 80})], dimensions={"a": 0.5, "b": 0.5})
    assert abs(r[0].quality - 0.80) < 1e-6


def test_standby_ranks_below_active():
    sel = MultiDimSelector(CFG)
    models = [_m("standby_hi", {"a": 99}, status="standby"), _m("active_lo", {"a": 70})]
    r = sel.select("standard", "x", models, dimensions={"a": 1.0})
    assert r[0].model == "active_lo"

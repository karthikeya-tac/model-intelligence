"""Router-level: determinism + decision-shape preservation (so promotion is drop-in)."""
from pathlib import Path

from app.config import settings
from app.store.file_store import FileStore

from experiments.router_v2.router_v2 import RouterV2

CFG_DIR = Path(settings.config_dir)
EXP = Path(__file__).resolve().parent.parent

_store = FileStore(settings.config_dir, source_mode=settings.registry_mode)
_router = RouterV2(_store, config_path=EXP / "config.yaml", routes_path=CFG_DIR / "routes.yaml")

# every field the live UI / RouteResponse reads
_CONTRACT = ("intent_id", "intent_source", "confidence", "base_tier", "tier", "model_id",
             "provider", "matched_rules", "candidates", "session_pct", "escalated", "reason")


def test_determinism_same_query_same_decision():
    a = _router.route(prompt="write a function to merge two sorted lists")
    b = _router.route(prompt="write a function to merge two sorted lists")
    assert a == b


def test_decision_shape_preserved_plus_additive():
    d = _router.route(prompt="design a fault-tolerant payment architecture")
    for k in _CONTRACT:
        assert k in d, f"missing contract field {k}"
    for k in ("intents", "difficulty", "need_vector", "features"):   # additive
        assert k in d
    assert d["tier"] in ("fast", "standard", "powerful")
    cand = d["candidates"][0]
    for k in ("model_id", "provider", "score", "quality", "cost", "latency", "available"):
        assert k in cand


def test_easy_query_stays_cheap():
    d = _router.route(prompt="hi there")
    assert d["tier"] == "fast"

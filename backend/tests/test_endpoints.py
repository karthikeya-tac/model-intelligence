"""Endpoint audit — boots the app (lifespan) and hits every endpoint group via TestClient.
A green run here = the API is wired and responding. Keyword mode (conftest) keeps it fast."""
from fastapi.testclient import TestClient

from app.main import app


def test_all_endpoints_respond():
    with TestClient(app) as c:
        # meta
        assert c.get("/health").json()["status"] == "ok"
        assert c.get("/").status_code == 200
        # registry
        assert c.get("/api/v1/registry/source").status_code == 200
        # models
        models = c.get("/api/v1/models").json()["models"]
        assert len(models) > 0
        mid = models[0]["id"]
        assert c.get(f"/api/v1/models/{mid}").status_code == 200
        assert c.get(f"/api/v1/models/{mid}/benchmarks").status_code == 200
        assert c.get(f"/api/v1/models/{mid}/usage").status_code == 200
        assert c.get(f"/api/v1/models/{mid}/context-profile").status_code == 200
        # intents
        assert c.get("/api/v1/intents").status_code == 200
        assert c.post("/api/v1/intents/classify", json={"prompt": "write a function"}).status_code == 200
        # rules
        assert c.get("/api/v1/rules").status_code == 200
        # routing + console
        r = c.post("/api/v1/route", json={"prompt": "design a scalable system"}).json()
        assert r["model_id"] and r["tier"] in ("fast", "standard", "powerful")
        assert c.get("/api/v1/routing/stats").status_code == 200
        ask = c.post("/api/v1/console/ask", json={"prompt": "summarize this", "execute": False}).json()
        assert "decision" in ask and "model" in ask
        # test
        assert c.post("/api/v1/test/single", json={"model_id": mid, "prompt": "hi"}).status_code == 200
        assert c.post("/api/v1/test/compare", json={"prompt": "hi", "model_ids": [mid]}).status_code == 200
        # providers
        provs = c.get("/api/v1/providers").json()["providers"]
        assert len(provs) > 0
        pid = provs[0]["provider_id"]
        assert c.get("/api/v1/providers/health").status_code == 200
        assert c.get(f"/api/v1/providers/{pid}").status_code == 200
        assert c.get(f"/api/v1/providers/{pid}/models").status_code == 200
        # settings + audit
        assert c.get("/api/v1/settings/architect-mode").status_code == 200
        assert c.get("/api/v1/settings/fallback").status_code == 200
        assert c.get("/api/v1/audit").status_code == 200
        # context
        assert c.get("/api/v1/context/compaction").status_code == 200
        assert c.get("/api/v1/context/budget").status_code == 200
        assert c.post("/api/v1/context/fit-check", json={"prompt": "x", "model_ids": [mid]}).status_code == 200


def test_unknown_model_is_404():
    with TestClient(app) as c:
        assert c.get("/api/v1/models/nope-not-real").status_code == 404

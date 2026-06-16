"""Deterministic simulation of model execution (no provider calls).

Backs /test/single, /test/compare and the executed side of /route. Given a model's
catalog facts + the prompt, it derives reproducible latency / tokens / cost /
value_score from a hash, so demos are stable and need no API keys.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict

LATENCY_BASE_MS = {
    "fastest": 320, "faster": 520, "fast": 700, "adaptive": 1100,
    "moderate": 1400, "slower": 2600, "slowest": 4200,
}


def _seed(model_id: str, prompt: str, trust: str) -> int:
    h = hashlib.md5(f"{model_id}|{prompt}|{trust}".encode()).hexdigest()
    return int(h[:8], 16)


def simulate(model: Dict[str, Any], prompt: str, trust: str = "L1") -> Dict[str, Any]:
    seed = _seed(model["id"], prompt, trust)
    pricing = model.get("pricing", {}) or {}
    cls = model.get("classification", {}) or {}
    caps = (model.get("benchmarks", {}) or {}).get("capability_scores", {}) or {}

    in_tok = max(8, len(prompt) // 4)
    out_tok = 200 + seed % 700
    cost = (pricing.get("input", 0) or 0) * in_tok / 1e6 + (pricing.get("output", 0) or 0) * out_tok / 1e6

    base = LATENCY_BASE_MS.get(cls.get("latency_class", "moderate"), 1400)
    latency = int(base * (0.8 + (seed % 50) / 100.0))   # ±jitter

    quality = (sum(caps.values()) / len(caps) / 100.0) if caps else 0.6
    # value = quality per dollar, mapped to 0..100 (cheaper + better = higher)
    value = max(0.0, min(100.0, round(quality * 100 - cost * 800 - latency / 400, 1)))

    return {
        "model_id": model["id"],
        "output": f"[simulated · {model['id']}] response to: {prompt[:80].strip()}…",
        "latency_ms": latency,
        "tokens": in_tok + out_tok,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cost_usd": round(cost, 6),
        "value_score": value,
    }

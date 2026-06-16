"""Provider health (EP25) — synthetic but deterministic per provider.

Status is derived from whether the provider's ${ENV} key is configured; uptime /
latency / error_rate are seeded from the provider id so they're stable across calls.
(Phase 1 replaces this with the scheduled health-probe table.)
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List

from . import secrets


def _seed(pid: str) -> int:
    return int(hashlib.md5(pid.encode()).hexdigest()[:8], 16)


def provider_health(provider: Dict[str, Any]) -> Dict[str, Any]:
    pid = provider["id"]
    s = _seed(pid)
    key_ref = (provider.get("auth") or {}).get("api_key_ref")
    configured = secrets.is_configured(key_ref)
    status = "connected" if configured else "not_connected"
    return {
        "provider_id": pid,
        "name": provider.get("name", pid),
        "status": status,
        "uptime_30d": round(98.5 + (s % 150) / 100.0, 2),    # 98.50–99.99
        "avg_latency_ms": 300 + s % 900,
        "error_rate": round((s % 50) / 100.0, 2),            # 0.00–0.49 %
        "last_check": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def all_health(providers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [provider_health(p) for p in providers]

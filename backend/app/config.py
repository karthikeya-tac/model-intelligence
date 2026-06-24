"""Runtime settings (env-driven, 12-factor). No extra deps — plain env reads."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Load BACKEND_DIR/.env into os.environ (no dependency). Existing env wins."""
    p = BACKEND_DIR / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


_load_dotenv()


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).lower() in ("1", "true", "yes", "on")


class Settings:
    config_dir: str = os.environ.get("NIHA_CONFIG_DIR", str(BACKEND_DIR / "config_data"))
    registry_mode: str = os.environ.get("REGISTRY_MODE", "file")        # file | db (UI write-gate)
    semantic: bool = _flag("SEMANTIC", "1")                              # embedding L1 default (set 0 for keyword-only)
    cors_origins = os.environ.get(
        "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
    ).split(",")
    exec_timeout: int = int(os.environ.get("NIHA_EXEC_TIMEOUT", "20"))   # live provider-call timeout (s)
    max_tokens: int = int(os.environ.get("NIHA_MAX_TOKENS", "2048"))     # max output tokens for live calls
    # Phase-0 runs SINGLE-WORKER (in-memory overlay is per-process). Read the common
    # worker-count envs so we can warn at startup if someone scales out by accident.
    worker_count: int = int(os.environ.get("WEB_CONCURRENCY") or os.environ.get("UVICORN_WORKERS") or "1")


settings = Settings()

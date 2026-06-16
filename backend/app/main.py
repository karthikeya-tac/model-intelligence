"""Niha Model Intelligence API — Phase 0 (FastAPI, file-backed).

Boots the FileStore (loads the 4 registry YAMLs + builds mutable overlay), the
RouterService (2-layer router), and Telemetry once at startup, then serves the 35
spec endpoints under /api/v1.
"""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import deps
from app.config import settings
from app.errors import install_error_handlers
from app.routing.engine import RouterService
from app.routing.telemetry import Telemetry
from app.store.file_store import FileStore

from app.api.v1 import (
    console,
    context,
    intents,
    models,
    providers,
    registry_admin,
    routing,
    rules,
    settings as settings_api,
    test,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = Path(settings.config_dir)
    store = FileStore(settings.config_dir, source_mode=settings.registry_mode)
    engine = RouterService(store, selection_path=cfg / "selection.yaml",
                           routes_path=cfg / "routes.yaml", semantic=settings.semantic)
    telemetry = Telemetry(store)
    deps.state.store = store
    deps.state.router = engine
    deps.state.telemetry = telemetry
    app.state.boot_ms = store.registry.load_ms
    yield


app = FastAPI(
    title="Niha Model Intelligence API",
    version="0.1.0",
    description="Phase-0 config-as-code backend: registry + hybrid 2-layer router. 35 endpoints under /api/v1.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
install_error_handlers(app)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id", uuid.uuid4().hex[:12])
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["x-request-id"] = rid
    response.headers["x-response-time-ms"] = str(round((time.perf_counter() - start) * 1000, 1))
    return response


API = "/api/v1"
for mod in (console, registry_admin, models, intents, rules, routing, test, providers, settings_api, context):
    app.include_router(mod.router, prefix=API)


@app.get("/health", tags=["meta"])
def health():
    store = deps.state.store
    return {"status": "ok", "mode": settings.registry_mode,
            "counts": store.registry.counts() if store else {}, "semantic": settings.semantic}


@app.get("/", tags=["meta"])
def root():
    return {"name": "Niha Model Intelligence API", "version": "0.1.0", "docs": "/docs",
            "endpoints": f"{API}/* (35 spec endpoints)"}

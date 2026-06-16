"""Dependency providers. The singletons are built in main.py's lifespan and shared
through `state`; the getters are used with FastAPI `Depends`.
"""
from __future__ import annotations

from typing import Optional

from app.routing.engine import RouterService
from app.routing.telemetry import Telemetry
from app.store.file_store import FileStore


class _State:
    store: Optional[FileStore] = None
    router: Optional[RouterService] = None
    telemetry: Optional[Telemetry] = None


state = _State()


def get_store() -> FileStore:
    return state.store


def get_router() -> RouterService:
    return state.router


def get_telemetry() -> Telemetry:
    return state.telemetry

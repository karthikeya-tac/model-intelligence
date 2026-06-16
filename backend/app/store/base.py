"""Data-source abstraction.

`Store` is the seam that makes the Phase-0 → Phase-1 swap a single config flag
(spec R8): `FileStore` (YAML + in-memory overlay) today, a future `DbStore`
(Postgres) later — both satisfy the same interface, so the EP contracts and the
routers never change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.registry import Registry


class Store(ABC):
    """Read the immutable registry snapshot; hold mutable Phase-0 state in memory."""

    @property
    @abstractmethod
    def registry(self) -> Registry: ...

    @abstractmethod
    def reload(self) -> Dict[str, int]:
        """Atomically rebuild the snapshot from source; return counts. Bad source → keep old."""

    @abstractmethod
    def source(self) -> Dict[str, Optional[str]]: ...

    # mutable Phase-0 state (overlays) — see FileStore for the concrete behaviour
    @abstractmethod
    def audit(self, entity: Optional[str] = None, since: Optional[str] = None) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def record_audit(self, actor: str, entity: str, entity_id: str,
                     before: Any, after: Any) -> None: ...

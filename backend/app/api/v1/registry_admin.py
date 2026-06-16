"""EP34 reload · EP35 source."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_router, get_store
from app.schemas.api import ReloadResponse, SourceResponse

router = APIRouter(tags=["registry"])


@router.get("/registry/source", response_model=SourceResponse)
def get_source(store=Depends(get_store)):
    return store.source()


@router.post("/registry/reload", response_model=ReloadResponse)
def reload_registry(store=Depends(get_store), engine=Depends(get_router)):
    counts = store.reload()        # atomic: bad file keeps old config and raises
    engine.refresh()               # rebuild routing views from the new snapshot
    return {"reloaded": True, "counts": counts}

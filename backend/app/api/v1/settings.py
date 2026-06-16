"""EP26 architect-mode · EP27 fallback · EP28 audit."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends

from app.deps import get_store
from app.schemas.api import ArchitectPatch, FallbackPatch

router = APIRouter(tags=["settings"])


@router.get("/settings/architect-mode")
def get_architect(store=Depends(get_store)):
    return store.settings("architect_mode")


@router.patch("/settings/architect-mode")
def patch_architect(body: ArchitectPatch, store=Depends(get_store)):
    return store.patch_settings("architect_mode", body.model_dump(exclude_none=True))


@router.get("/settings/fallback")
def get_fallback(store=Depends(get_store)):
    return store.settings("fallback")


@router.patch("/settings/fallback")
def patch_fallback(body: FallbackPatch, store=Depends(get_store)):
    return store.patch_settings("fallback", body.model_dump(exclude_none=True))


@router.get("/audit")
def get_audit(entity: Optional[str] = None, since: Optional[str] = None, store=Depends(get_store)):
    return {"entries": store.audit(entity=entity, since=since)}

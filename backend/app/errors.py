"""Consistent error envelope + handlers (RegistryError → 4xx/5xx)."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.registry import (
    RegistryCrossRefError,
    RegistryError,
    RegistryParseError,
    RegistryValidationError,
)


def not_found(entity: str, entity_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{entity} '{entity_id}' not found")


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RegistryParseError)
    @app.exception_handler(RegistryValidationError)
    @app.exception_handler(RegistryCrossRefError)
    async def _registry_bad(request: Request, exc: RegistryError):
        # invalid config → 422 (the data is wrong, not the request)
        return JSONResponse(status_code=422, content={"detail": str(exc), "type": exc.__class__.__name__})

    @app.exception_handler(RegistryError)
    async def _registry_generic(request: Request, exc: RegistryError):
        return JSONResponse(status_code=500, content={"detail": str(exc), "type": exc.__class__.__name__})

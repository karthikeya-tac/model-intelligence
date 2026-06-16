"""Niha registry — typed, validated, in-memory snapshot of the four Phase-0 YAMLs."""
from .errors import (
    RegistryCrossRefError,
    RegistryError,
    RegistryParseError,
    RegistryValidationError,
)
from .loader import Registry, load_registry

__all__ = [
    "Registry",
    "load_registry",
    "RegistryError",
    "RegistryParseError",
    "RegistryValidationError",
    "RegistryCrossRefError",
]

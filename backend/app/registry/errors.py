"""Registry load failures.

Every error here is fatal at boot: the loader builds a *fresh* Registry and raises
on any problem, so a bad file can never partially replace a good config (atomic
reload — see loader.load_registry).
"""
from __future__ import annotations

from typing import List, Optional


class RegistryError(Exception):
    """Base class for all registry load failures."""


class RegistryParseError(RegistryError):
    """The YAML could not be parsed. Carries file + 1-based line where known."""

    def __init__(self, path: str, line: Optional[int], detail: str) -> None:
        self.path = path
        self.line = line
        self.detail = detail
        where = f"{path}:{line}" if line else path
        super().__init__(f"YAML parse error in {where}: {detail}")


class RegistryValidationError(RegistryError):
    """The YAML parsed but failed schema validation (types/enums/ranges/required)."""

    def __init__(self, path: str, problems: List[str]) -> None:
        self.path = path
        self.problems = problems
        body = "\n  - ".join(problems)
        super().__init__(f"Validation failed for {path}:\n  - {body}")


class RegistryCrossRefError(RegistryError):
    """A reference between files does not resolve (e.g. model -> unknown provider)."""

    def __init__(self, problems: List[str]) -> None:
        self.problems = problems
        body = "\n  - ".join(problems)
        super().__init__(f"Cross-reference validation failed:\n  - {body}")

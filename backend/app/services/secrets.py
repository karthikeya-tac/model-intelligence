"""Secret resolution (P0-8). `${ENV_VAR}` refs resolve from the process env at
request time. Values are NEVER returned by the API — only a configured/unconfigured
flag and a masked hint.
"""
from __future__ import annotations

import os
import re
from typing import Optional

_REF = re.compile(r"^\$\{([A-Z0-9_]+)\}$")


def env_name(ref: Optional[str]) -> Optional[str]:
    if not ref:
        return None
    m = _REF.match(ref)
    return m.group(1) if m else None


def is_configured(ref: Optional[str]) -> bool:
    name = env_name(ref)
    return bool(name and os.environ.get(name))


def hint(ref: Optional[str]) -> Optional[str]:
    """A safe, non-secret display hint, e.g. '${OPENAI_API_KEY} (set)' — never the value."""
    name = env_name(ref)
    if not name:
        return None
    return f"${{{name}}} ({'set' if os.environ.get(name) else 'unset'})"


def resolve(ref: Optional[str]) -> Optional[str]:
    """Resolve to the actual value for INTERNAL use only (provider calls). Not exposed."""
    name = env_name(ref)
    return os.environ.get(name) if name else None

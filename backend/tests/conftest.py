"""Test config. Force keyword classification so the suite is fast and deterministic
(no embedding-model download in CI). Production defaults to SEMANTIC=1."""
import os

os.environ.setdefault("SEMANTIC", "0")

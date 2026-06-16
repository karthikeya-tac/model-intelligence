"""Controlled vocabularies used across the niha registry.

These mirror the enums declared in models.schema.json / providers.schema.json so
the Pydantic loader (the app's source of truth) and the JSON Schemas (the CI/editor
artifact) stay in lock-step.
"""
from __future__ import annotations

from enum import Enum


class Tier(str, Enum):
    fast = "fast"
    standard = "standard"
    powerful = "powerful"


class Role(str, Enum):
    primary = "primary"
    alternative = "alternative"
    fallback = "fallback"


class Status(str, Enum):
    active = "active"
    preview = "preview"
    standby = "standby"
    deprecated = "deprecated"
    disabled = "disabled"


class Sampling(str, Enum):
    tunable = "tunable"
    locked = "locked"


class Modality(str, Enum):
    text = "text"
    image = "image"
    audio = "audio"
    video = "video"
    pdf = "pdf"
    document = "document"


class Effort(str, Enum):
    none = "none"
    minimal = "minimal"
    low = "low"
    medium = "medium"
    high = "high"
    xhigh = "xhigh"


class ReasoningType(str, Enum):
    thinking = "thinking"
    effort = "effort"
    none = "none"


class ThinkingMode(str, Enum):
    adaptive = "adaptive"
    extended = "extended"


class ProviderKind(str, Enum):
    anthropic = "anthropic"
    openai = "openai"
    google = "google"
    ollama = "ollama"
    custom = "custom"


class ProviderRole(str, Enum):
    primary = "primary"
    fallback = "fallback"
    secondary = "secondary"


class ApiStyle(str, Enum):
    messages = "messages"
    responses = "responses"
    generateContent = "generateContent"


class ProviderStatus(str, Enum):
    connected = "connected"
    not_connected = "not_connected"

"""Typed Pydantic (v2) models for models.yaml and providers.yaml.

These are the loader's source of truth. `extra="forbid"` everywhere means unknown
keys are rejected — matching `additionalProperties: false` in the companion JSON
Schemas. Keep this file and the *.schema.json files aligned (a test asserts parity).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import (
    ApiStyle,
    Effort,
    Modality,
    ProviderKind,
    ProviderRole,
    ProviderStatus,
    ReasoningType,
    Role,
    Sampling,
    Status,
    ThinkingMode,
    Tier,
)

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
SECRET_REF_RE = re.compile(r"^\$\{[A-Z0-9_]+\}$")


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- #
#  models.yaml
# --------------------------------------------------------------------------- #
class Identity(_Base):
    display_name: str = Field(min_length=1)
    api_model_name: str = Field(min_length=1)
    description: Optional[str] = None
    release_date: Optional[str] = None


class Capability(_Base):
    context_window: int = Field(ge=1)
    max_output_tokens: int = Field(ge=1)
    input_modalities: Optional[List[Modality]] = None
    output_modalities: Optional[List[Modality]] = None
    reasoning_level: Optional[str] = None
    knowledge_cutoff: Optional[str] = None
    supports_tools: Optional[bool] = None
    supports_streaming: Optional[bool] = None


class LongContext(_Base):
    threshold_tokens: int = Field(ge=1)
    input: Optional[float] = Field(default=None, ge=0)
    output: Optional[float] = Field(default=None, ge=0)
    input_multiplier: Optional[float] = Field(default=None, ge=0)
    output_multiplier: Optional[float] = Field(default=None, ge=0)


class TierPrice(_Base):
    input: Optional[float] = Field(default=None, ge=0)
    output: Optional[float] = Field(default=None, ge=0)
    cached_input: Optional[float] = Field(default=None, ge=0)


class ServiceTiers(_Base):
    batch: Optional[TierPrice] = None
    flex: Optional[TierPrice] = None
    priority: Optional[TierPrice] = None


class Pricing(_Base):
    """Per 1,000,000 tokens, USD. Only `input`/`output` are required."""

    currency: str = "USD"
    input: float = Field(ge=0)
    output: float = Field(ge=0)
    cached_input: Optional[float] = Field(default=None, ge=0)
    cache_read: Optional[float] = Field(default=None, ge=0)
    cache_write: Optional[float] = Field(default=None, ge=0)
    audio_input: Optional[float] = Field(default=None, ge=0)
    long_context: Optional[LongContext] = None
    service_tiers: Optional[ServiceTiers] = None


class Classification(_Base):
    tier: Tier
    role: Role = Role.alternative
    status: Status
    latency_class: Optional[str] = None


class BudgetTokens(_Base):
    min: Optional[int] = Field(default=None, ge=0)
    max: Optional[int] = Field(default=None, ge=0)


class Reasoning(_Base):
    type: Optional[ReasoningType] = None
    modes: Optional[List[ThinkingMode]] = None
    effort_levels: Optional[List[Effort]] = None
    levels: Optional[List[Effort]] = None
    default_effort: Optional[Effort] = None
    can_disable: Optional[bool] = None
    budget_tokens: Optional[BudgetTokens] = None


class Controls(_Base):
    sampling: Optional[Sampling] = None
    reasoning: Optional[Reasoning] = None


class Benchmarks(_Base):
    capability_scores: Optional[Dict[str, int]] = None
    standard: Optional[Dict[str, float]] = None

    @field_validator("capability_scores")
    @classmethod
    def _scores_in_range(cls, v: Optional[Dict[str, int]]) -> Optional[Dict[str, int]]:
        if v:
            for key, score in v.items():
                if not 0 <= score <= 100:
                    raise ValueError(f"capability score '{key}'={score} is out of range 0-100")
        return v


class Model(_Base):
    id: str
    provider: str
    identity: Identity
    capability: Capability
    pricing: Pricing
    classification: Classification
    controls: Optional[Controls] = None
    benchmarks: Optional[Benchmarks] = None

    @field_validator("id", "provider")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not SLUG_RE.match(v):
            raise ValueError(f"'{v}' is not a valid slug (lowercase letters, digits, . _ -)")
        return v


class ModelsDocument(_Base):
    schema_version: str
    generated_at: Optional[str] = None
    models: List[Model] = Field(min_length=1)


# --------------------------------------------------------------------------- #
#  providers.yaml
# --------------------------------------------------------------------------- #
class Api(_Base):
    base_url: str = Field(min_length=1)
    endpoint: Optional[str] = None
    style: ApiStyle


class Auth(_Base):
    api_key_ref: Optional[str] = None
    fallback_key_ref: Optional[str] = None

    @field_validator("api_key_ref", "fallback_key_ref")
    @classmethod
    def _env_ref_only(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not SECRET_REF_RE.match(v):
            raise ValueError(
                "must be an env reference of the form ${ENV_VAR}; inline secrets are not allowed"
            )
        return v


class Provider(_Base):
    id: str
    name: str = Field(min_length=1)
    kind: ProviderKind
    role: ProviderRole
    api: Api
    auth: Auth
    rate_limit_rpm: Optional[int] = Field(default=None, ge=0)
    rate_limit_tpm: Optional[int] = Field(default=None, ge=0)
    status: ProviderStatus = ProviderStatus.not_connected
    param_profile: Optional[Dict[str, Any]] = None

    @field_validator("id")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not SLUG_RE.match(v):
            raise ValueError(f"'{v}' is not a valid slug (lowercase letters, digits, . _ -)")
        return v


class ProvidersDocument(_Base):
    schema_version: str
    generated_at: Optional[str] = None
    providers: List[Provider] = Field(min_length=1)


# --------------------------------------------------------------------------- #
#  intents.yaml  (P0-4)
# --------------------------------------------------------------------------- #
_TIER_ORDER = {Tier.fast: 0, Tier.standard: 1, Tier.powerful: 2}


class Intent(_Base):
    id: str
    name: str = Field(min_length=1)
    description: Optional[str] = None
    complexity: Optional[int] = Field(default=None, ge=1, le=5)
    default_tier: Tier
    min_tier: Tier
    keywords: Optional[List[str]] = None
    category: Optional[str] = None       # filled by the loader from the enclosing category

    @model_validator(mode="after")
    def _min_le_default(self) -> "Intent":
        if _TIER_ORDER[self.min_tier] > _TIER_ORDER[self.default_tier]:
            raise ValueError(
                f"intent '{self.id}': min_tier '{self.min_tier.value}' is above "
                f"default_tier '{self.default_tier.value}'"
            )
        return self


class IntentCategory(_Base):
    name: str = Field(min_length=1)
    intents: List[Intent] = Field(min_length=1)


class IntentsDocument(_Base):
    version: Optional[int] = None
    categories: List[IntentCategory] = Field(min_length=1)


# --------------------------------------------------------------------------- #
#  rules.yaml  (P0-3)
# --------------------------------------------------------------------------- #
RuleType = Literal["route", "boost", "limit", "redirect", "cost_cap", "timed"]
MatchBy = Literal["intent", "keyword", "agent", "workspace", "session_size"]
Priority = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
RuleStatus = Literal["active", "draft", "paused", "expired"]


class Rule(_Base):
    id: str
    name: str = Field(min_length=1)
    type: RuleType
    match_by: MatchBy
    match_value: Dict[str, Any] = Field(default_factory=dict)
    action: Dict[str, Any] = Field(default_factory=dict)
    scope: Optional[Dict[str, Any]] = None
    priority: Priority = "MEDIUM"
    status: RuleStatus = "active"
    expires_at: Optional[str] = None
    description: Optional[str] = None


class RulesDocument(_Base):
    version: Optional[int] = None
    rules: List[Rule] = Field(default_factory=list)

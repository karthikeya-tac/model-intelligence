"""Pydantic request/response models for the API (typed inputs + key responses)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---- registry ----
class SourceResponse(BaseModel):
    mode: str
    version: Optional[str] = None
    last_loaded: Optional[str] = None


class ReloadResponse(BaseModel):
    reloaded: bool
    counts: Dict[str, int]


# ---- models ----
class ModelCreate(BaseModel):
    provider_id: str
    model_ref: str
    tier: str
    role: str = "alternative"
    native_window: Optional[int] = None
    display_name: Optional[str] = None


class ModelConfigPatch(BaseModel):
    tier: Optional[str] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_output_by_trust: Optional[Dict[str, int]] = None
    thinking_budget_by_trust: Optional[Dict[str, int]] = None
    system_prefix: Optional[str] = None
    rate_limit_rpm: Optional[int] = None
    status: Optional[str] = None


class ContextProfilePatch(BaseModel):
    native_window: Optional[int] = None
    effective_window: Optional[int] = None
    compaction_floor_pct: Optional[int] = None
    memory_budget_tokens: Optional[int] = None
    context_budget_total: Optional[int] = None


# ---- intents ----
class IntentTierPatch(BaseModel):
    default_tier: Optional[str] = None
    min_tier: Optional[str] = None


class ClassifyRequest(BaseModel):
    prompt: str


class ClassifyResponse(BaseModel):
    intent_id: Optional[str]
    category: Optional[str] = None
    source: str
    confidence: float


# ---- rules ----
class RuleCreate(BaseModel):
    id: Optional[str] = None
    name: str
    type: str
    match_by: str
    match_value: Dict[str, Any] = Field(default_factory=dict)
    action: Dict[str, Any] = Field(default_factory=dict)
    scope: Optional[Dict[str, Any]] = None
    priority: str = "MEDIUM"
    status: str = "active"
    expires_at: Optional[str] = None
    description: Optional[str] = None


class RulePatch(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    match_by: Optional[str] = None
    match_value: Optional[Dict[str, Any]] = None
    action: Optional[Dict[str, Any]] = None
    scope: Optional[Dict[str, Any]] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    expires_at: Optional[str] = None


class RuleSimulate(BaseModel):
    rule_draft: Dict[str, Any]


# ---- routing / test ----
class RouteRequest(BaseModel):
    prompt: Optional[str] = None
    intent_id: Optional[str] = None
    agent: Optional[str] = None
    workspace: Optional[str] = None
    session_tokens: Optional[int] = None
    profile: Optional[str] = None      # quality|balanced|cost|latency (Level-2 weight set)
    step: Optional[str] = None         # plan|exec (Architect Mode)


class ConsoleAsk(BaseModel):
    prompt: str
    profile: Optional[str] = None       # quality|balanced|cost|latency
    agent: Optional[str] = None
    workspace: Optional[str] = None
    session_tokens: Optional[int] = None
    intent_id: Optional[str] = None     # explicit intent override
    execute: bool = True                # attempt live output if a key is configured


class RouteResponse(BaseModel):
    model_id: Optional[str]
    tier: str
    matched_rules: List[Dict[str, Any]]
    reason: str
    intent_id: Optional[str] = None
    intent_source: Optional[str] = None
    base_tier: Optional[str] = None
    candidates: List[Dict[str, Any]] = Field(default_factory=list)
    escalated: bool = False
    profile: Optional[str] = None


class TestSingle(BaseModel):
    model_id: str
    prompt: str
    trust: str = "L1"


class TestCompare(BaseModel):
    prompt: str
    model_ids: List[str]
    trust: str = "L1"


class FitCheck(BaseModel):
    prompt: str
    model_ids: List[str]
    trust: str = "L1"
    session_tokens: Optional[int] = None


# ---- providers ----
class ProviderCreate(BaseModel):
    kind: str
    name: Optional[str] = None
    api_key: Optional[str] = None       # accepted, stored only as ${ENV} ref hint; never echoed
    base_url: Optional[str] = None
    role: str = "secondary"


class ProviderPatch(BaseModel):
    role: Optional[str] = None
    rate_limit_rpm: Optional[int] = None
    rate_limit_tpm: Optional[int] = None
    base_url: Optional[str] = None
    status: Optional[str] = None


# ---- settings ----
class ArchitectPatch(BaseModel):
    enabled: Optional[bool] = None
    plan_tier: Optional[str] = None
    exec_tier: Optional[str] = None


class FallbackPatch(BaseModel):
    chains: Optional[Dict[str, List[str]]] = None
    trigger: Optional[str] = None
    retries: Optional[int] = None
    backoff: Optional[str] = None
    notify: Optional[bool] = None


class CompactionPatch(BaseModel):
    thresholds: Optional[Dict[str, int]] = None
    summariser_model_id: Optional[str] = None
    by_trust: Optional[Dict[str, Any]] = None


class BudgetPatch(BaseModel):
    total: Optional[int] = None
    layers: Optional[Dict[str, int]] = None

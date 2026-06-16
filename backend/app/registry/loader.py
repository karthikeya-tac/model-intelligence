"""Boot loader for the Niha registry (Phase-0 config-as-code).

Loads the FOUR registry YAMLs — models, providers, intents, rules — into an
immutable, indexed `Registry`, checks cross-references, and fails fast with file +
line on any error. Extends the original P0-5 loader by completing the P0-3/P0-4
seams (intents + rules + their cross-ref checks).

`load_registry()` never mutates shared state — the caller swaps the returned object
in atomically (the EP34 reload contract); a bad reload keeps the previous config.
"""
from __future__ import annotations

import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import ValidationError

from .enums import Tier
from .errors import (
    RegistryCrossRefError,
    RegistryError,
    RegistryParseError,
    RegistryValidationError,
)
from .schema import (
    Intent,
    IntentsDocument,
    Model,
    ModelsDocument,
    Provider,
    ProvidersDocument,
    Rule,
    RulesDocument,
)

DEFAULT_MODELS_PATH = "models.yaml"
DEFAULT_PROVIDERS_PATH = "providers.yaml"
DEFAULT_INTENTS_PATH = "intents.yaml"
DEFAULT_RULES_PATH = "rules.yaml"


# --------------------------------------------------------------------------- #
#  parsing helpers
# --------------------------------------------------------------------------- #
def _read(path: str) -> str:
    p = Path(path)
    if not p.exists():
        raise RegistryParseError(path, None, "file not found")
    return p.read_text(encoding="utf-8")


def _parse_yaml(path: str, text: str):
    try:
        return yaml.safe_load(text)
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark
        line = (mark.line + 1) if mark is not None else None
        detail = (exc.problem or str(exc)).strip()
        raise RegistryParseError(path, line, detail) from exc
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        raise RegistryParseError(path, None, str(exc)) from exc


def _validation_error(path: str, exc: ValidationError, top_key: str) -> RegistryValidationError:
    problems: List[str] = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"])
        problems.append(f"{loc}: {err['msg']}")
    return RegistryValidationError(path, problems)


def _load_doc(path: str, top_key: str, model_cls):
    text = _read(path)
    data = _parse_yaml(path, text)
    if not isinstance(data, dict):
        raise RegistryValidationError(path, [f"top-level document must be a mapping with a '{top_key}:' key"])
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        raise _validation_error(path, exc, top_key) from exc


def _check_unique(ids: List[str], kind: str, path: str) -> None:
    seen, dups = set(), []
    for i in ids:
        if i in seen and i not in dups:
            dups.append(i)
        seen.add(i)
    if dups:
        raise RegistryValidationError(path, [f"duplicate {kind} id: '{d}'" for d in dups])


# --------------------------------------------------------------------------- #
#  the loaded registry
# --------------------------------------------------------------------------- #
class Registry:
    """Validated, indexed snapshot of all four registry YAMLs. Read-only."""

    def __init__(
        self,
        models_doc: ModelsDocument,
        providers_doc: ProvidersDocument,
        intents_doc: IntentsDocument,
        rules_doc: RulesDocument,
        *,
        source_mode: str = "file",
        loaded_at: Optional[str] = None,
        load_ms: Optional[float] = None,
    ) -> None:
        self.schema_version = models_doc.schema_version
        self.models: List[Model] = models_doc.models
        self.providers: List[Provider] = providers_doc.providers
        # flatten intent categories, stamping each intent with its category name
        self.intents: List[Intent] = []
        for cat in intents_doc.categories:
            for intent in cat.intents:
                intent.category = cat.name
                self.intents.append(intent)
        self.rules: List[Rule] = rules_doc.rules
        self.source_mode = source_mode
        self.loaded_at = loaded_at
        self.load_ms = load_ms
        self._models_by_id = {m.id: m for m in self.models}
        self._providers_by_id = {p.id: p for p in self.providers}
        self._intents_by_id = {i.id: i for i in self.intents}
        self._rules_by_id = {r.id: r for r in self.rules}

    # ---- lookups -----------------------------------------------------------
    def model(self, model_id: str) -> Optional[Model]:
        return self._models_by_id.get(model_id)

    def provider(self, provider_id: str) -> Optional[Provider]:
        return self._providers_by_id.get(provider_id)

    def intent(self, intent_id: str) -> Optional[Intent]:
        return self._intents_by_id.get(intent_id)

    def rule(self, rule_id: str) -> Optional[Rule]:
        return self._rules_by_id.get(rule_id)

    def models_for_provider(self, provider_id: str) -> List[Model]:
        return [m for m in self.models if m.provider == provider_id]

    def models_by_tier(self, tier: Tier) -> List[Model]:
        return [m for m in self.models if m.classification.tier == tier]

    def counts(self) -> Dict[str, int]:
        return {
            "models": len(self.models),
            "providers": len(self.providers),
            "intents": len(self.intents),
            "rules": len(self.rules),
        }

    def source(self) -> Dict[str, Optional[str]]:
        return {"mode": self.source_mode, "version": self.schema_version, "last_loaded": self.loaded_at}


# --------------------------------------------------------------------------- #
#  entry point
# --------------------------------------------------------------------------- #
def load_registry(
    *,
    base_dir: Optional[str] = None,
    models_path: str = DEFAULT_MODELS_PATH,
    providers_path: str = DEFAULT_PROVIDERS_PATH,
    intents_path: str = DEFAULT_INTENTS_PATH,
    rules_path: str = DEFAULT_RULES_PATH,
    source_mode: str = "file",
    now: Optional[str] = None,
) -> Registry:
    """Parse + validate all four registry files and return an indexed snapshot.

    Raises a RegistryError subclass on the first failure (fail-fast at boot).
    """
    if base_dir is not None:
        b = Path(base_dir)
        models_path = str(b / models_path)
        providers_path = str(b / providers_path)
        intents_path = str(b / intents_path)
        rules_path = str(b / rules_path)

    start = time.perf_counter()

    models_doc = _load_doc(models_path, "models", ModelsDocument)
    providers_doc = _load_doc(providers_path, "providers", ProvidersDocument)
    intents_doc = _load_doc(intents_path, "categories", IntentsDocument)
    rules_doc = _load_doc(rules_path, "rules", RulesDocument)

    _check_unique([m.id for m in models_doc.models], "model", models_path)
    _check_unique([p.id for p in providers_doc.providers], "provider", providers_path)
    intent_ids = [i.id for cat in intents_doc.categories for i in cat.intents]
    _check_unique(intent_ids, "intent", intents_path)
    _check_unique([r.id for r in rules_doc.rules], "rule", rules_path)

    # cross-references
    provider_ids = {p.id for p in providers_doc.providers}
    model_ids = {m.id for m in models_doc.models}
    intent_id_set = set(intent_ids)
    crossref: List[str] = []
    for m in models_doc.models:
        if m.provider not in provider_ids:
            crossref.append(f"model '{m.id}' references unknown provider '{m.provider}'")
    for r in rules_doc.rules:
        if r.match_by == "intent":
            iid = r.match_value.get("intent_id")
            if iid is not None and iid not in intent_id_set:
                crossref.append(f"rule '{r.id}' references unknown intent_id '{iid}'")
        redirect = (r.action or {}).get("redirect_to_model")
        if redirect and redirect not in model_ids:
            crossref.append(f"rule '{r.id}' references unknown model '{redirect}'")
    if crossref:
        raise RegistryCrossRefError(crossref)

    load_ms = round((time.perf_counter() - start) * 1000, 2)
    if now is None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    return Registry(models_doc, providers_doc, intents_doc, rules_doc,
                    source_mode=source_mode, loaded_at=now, load_ms=load_ms)

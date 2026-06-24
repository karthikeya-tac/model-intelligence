"""Deterministic query features → difficulty score (Level-1 input).

Pure stdlib + regex (NO model inference) so it is reproducible and costs nothing.
`difficulty` is computed FROM THE QUERY TEXT — not a fabricated fact about any model.
Weights/knees come from selection.yaml's `difficulty` block (policy knobs).
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Dict

CHARS_PER_TOKEN = 4

_CODE_TOKENS = ("def ", "class ", "function", "import ", "const ", "var ", "=>", "{", "}",
                "();", "select ", "return ", "public ", "private ", "async ")
_MATH_WORDS = ("integral", "derivative", "equation", "solve for", "matrix", "probability",
               "theorem", "prove", "factorial", "polynomial", "logarithm")
_TOOL_WORDS = ("call the api", "use the tool", "browse", "run the", "execute", "shell command",
               "invoke", "function call", "use a tool")
_STEP_WORDS = ("then", "after that", "next", "finally", "step ", "first,", "second,", "third,",
               "phase", "stage")
_CONSTRAINT_WORDS = ("must", "should", "ensure", "without", "only", "at least", "no more than",
                     "constraint", "requirement", "edge case", "handle the case", "make sure")
_DEPTH_WORDS = ("design", "architect", "trade-off", "tradeoff", "why", "prove", "derive",
                "optimi", "scalable", "distributed", "fault-tolerant", "concurrency")
_TRIVIAL_WORDS = ("hi", "hello", "hey", "thanks", "thank you", "tldr", "what is the capital",
                  "good morning", "good evening")
_QUESTION_STARTS = ("how", "what", "why", "who", "when", "where", "which", "is ", "are ", "can ", "do ")
_IMPERATIVE_VERBS = ("write", "build", "implement", "fix", "refactor", "design", "analyze",
                     "analyse", "create", "generate", "summarize", "summarise", "translate",
                     "review", "explain", "compute", "calculate", "solve", "draft", "compose")


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


@dataclass(frozen=True)
class QueryFeatures:
    char_len: int
    est_tokens: int
    word_count: int
    has_code: bool
    has_math: bool
    tool_signal: bool
    multi_step: int
    constraint_markers: int
    depth_cues: int
    is_question: bool
    is_imperative: bool
    ambiguity: float
    difficulty: float = 0.0

    def as_dict(self) -> Dict:
        return asdict(self)


def _count(text: str, words) -> int:
    return sum(text.count(w) for w in words)


def extract_features(prompt: str, *, intent_matched: bool = True) -> QueryFeatures:
    p = (prompt or "")
    t = p.lower()
    words = t.split()
    wc = len(words)

    has_code = bool(re.search(r"```", p)) or t.count("`") >= 2 or _count(t, _CODE_TOKENS) >= 2
    has_math = bool(re.search(r"\$.+\$", p)) or bool(re.search(r"\d+\s*[-+*/^=]\s*\d+", t)) \
        or any(w in t for w in _MATH_WORDS)
    tool_signal = any(w in t for w in _TOOL_WORDS)
    multi_step = _count(t, _STEP_WORDS) + len(re.findall(r"(?m)^\s*\d+[.)]", p))
    constraint_markers = _count(t, _CONSTRAINT_WORDS)
    depth_cues = sum(1 for w in _DEPTH_WORDS if w in t)
    is_question = p.strip().endswith("?") or t.startswith(_QUESTION_STARTS)
    is_imperative = any(t.startswith(v) for v in _IMPERATIVE_VERBS)

    amb = 0.0
    if wc < 4:
        amb += 0.15
    if any(w in (" " + t + " ") for w in (" this ", " it ", " that ")) and not has_code:
        amb += 0.2
    if not intent_matched:
        amb += 0.3
    if constraint_markers:
        amb -= 0.2
    if any(w in t for w in _TRIVIAL_WORDS):
        amb -= 0.2
    ambiguity = _clamp01(amb)

    return QueryFeatures(
        char_len=len(p), est_tokens=max(1, len(p) // CHARS_PER_TOKEN), word_count=wc,
        has_code=has_code, has_math=has_math, tool_signal=tool_signal,
        multi_step=multi_step, constraint_markers=constraint_markers, depth_cues=depth_cues,
        is_question=is_question, is_imperative=is_imperative, ambiguity=ambiguity,
    )


def difficulty_score(f: QueryFeatures, cfg: Dict) -> float:
    """Weighted, clamped 0..1 blend of normalized query signals (weights from selection.yaml)."""
    w = cfg.get("weights", {})
    length_sat = float(cfg.get("length_saturation_tokens", 600))
    ms_sat = float(cfg.get("multistep_saturation", 3))
    cons_sat = float(cfg.get("constraint_saturation", 3))

    length_n = min(f.est_tokens / length_sat, 1.0) if length_sat else 0.0
    multistep_n = min((f.multi_step + f.depth_cues) / ms_sat, 1.0) if ms_sat else 0.0
    constraint_n = min(f.constraint_markers / cons_sat, 1.0) if cons_sat else 0.0
    code_n = 1.0 if f.has_code else 0.0
    math_n = 1.0 if f.has_math else 0.0

    raw = (
        w.get("length", 0.15) * length_n
        + w.get("multistep", 0.25) * multistep_n
        + w.get("constraints", 0.20) * constraint_n
        + w.get("code", 0.10) * code_n
        + w.get("math", 0.10) * math_n
        + w.get("ambiguity", 0.20) * f.ambiguity
    )
    return round(_clamp01(raw), 4)

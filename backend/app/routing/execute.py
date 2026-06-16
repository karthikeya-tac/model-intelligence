"""Real model execution via a stand-in model.

The catalog holds FUTURE/fictional model names (Claude Opus 4.8, GPT-5.5, …) that
don't exist at the providers yet. So when a provider API key is configured, we run
the prompt against that provider's nearest REAL current model and label the output
"live via <real model>". No key → we report `configured: False` and the UI shows a
"set the key" hint instead of fake text.

Uses only the stdlib (urllib) — no extra deps.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

# catalog (provider_kind, tier) -> a real, current model to actually call
STANDIN = {
    ("anthropic", "fast"): "claude-3-5-haiku-latest",
    ("anthropic", "standard"): "claude-3-5-sonnet-latest",
    ("anthropic", "powerful"): "claude-3-5-sonnet-latest",
    ("openai", "fast"): "gpt-4o-mini",
    ("openai", "standard"): "gpt-4o-mini",
    ("openai", "powerful"): "gpt-4o",
    ("google", "fast"): "gemini-1.5-flash",
    ("google", "standard"): "gemini-1.5-flash",
    ("google", "powerful"): "gemini-1.5-pro",
}

MAX_TOKENS = 512
TIMEOUT = 40


def standin_model(provider_kind: str, tier: str) -> Optional[str]:
    return STANDIN.get((provider_kind, tier)) or STANDIN.get((provider_kind, "standard"))


def _post(url: str, headers: Dict[str, str], body: Dict[str, Any]) -> Dict[str, Any]:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode())


def _call_anthropic(model, prompt, key):
    data = _post("https://api.anthropic.com/v1/messages",
                 {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                 {"model": model, "max_tokens": MAX_TOKENS, "messages": [{"role": "user", "content": prompt}]})
    return data["content"][0]["text"]


def _call_openai(model, prompt, key):
    data = _post("https://api.openai.com/v1/chat/completions",
                 {"Authorization": f"Bearer {key}", "content-type": "application/json"},
                 {"model": model, "max_tokens": MAX_TOKENS, "messages": [{"role": "user", "content": prompt}]})
    return data["choices"][0]["message"]["content"]


def _call_google(model, prompt, key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    data = _post(url, {"content-type": "application/json"},
                 {"contents": [{"parts": [{"text": prompt}]}]})
    return data["candidates"][0]["content"]["parts"][0]["text"]


_CALLERS = {"anthropic": _call_anthropic, "openai": _call_openai, "google": _call_google}


def execute(provider_kind: str, tier: str, prompt: str, api_key: Optional[str]) -> Dict[str, Any]:
    """Return {configured, output, real_model, latency_ms, error}."""
    real = standin_model(provider_kind, tier)
    caller = _CALLERS.get(provider_kind)
    if not api_key:
        return {"configured": False, "output": None, "real_model": real, "latency_ms": None, "error": None}
    if not caller or not real:
        return {"configured": True, "output": None, "real_model": real, "latency_ms": None,
                "error": f"no live execution path for provider '{provider_kind}'"}
    start = time.perf_counter()
    try:
        text = caller(real, prompt, api_key)
        return {"configured": True, "output": text, "real_model": real,
                "latency_ms": int((time.perf_counter() - start) * 1000), "error": None}
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:300] if hasattr(e, "read") else str(e)
        return {"configured": True, "output": None, "real_model": real, "latency_ms": None,
                "error": f"{e.code}: {detail}"}
    except Exception as e:  # network/parse
        return {"configured": True, "output": None, "real_model": real, "latency_ms": None, "error": str(e)[:300]}

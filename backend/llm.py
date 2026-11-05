"""Thin LLM client used by the LLM judge, LLM agent adapter and LLM journey labelling.

Two providers are supported:

* **Anthropic** via the official ``anthropic`` SDK (``ANTHROPIC_API_KEY``).
* **OpenAI-compatible** chat-completions endpoints via ``httpx``
  (``OPENAI_API_KEY`` + optional ``OPENAI_BASE_URL``), which covers OpenAI,
  Azure-style proxies, vLLM, Ollama, LM Studio, etc.

Failures never crash the app: they raise :class:`LLMError` and are recorded in
:data:`health` so the UI can show an "offline mode" banner.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from .config import env


class LLMError(Exception):
    """Any failure talking to an LLM provider (missing key, auth, network, refusal)."""


@dataclass
class LLMHealth:
    """Last known state of the LLM connection, surfaced by ``/api/status``."""

    last_error: str = ""
    last_error_at: str = ""
    last_ok_at: str = ""

    def record_error(self, message: str) -> None:
        self.last_error = message
        self.last_error_at = datetime.now(timezone.utc).isoformat()

    def record_ok(self) -> None:
        self.last_error = ""
        self.last_ok_at = datetime.now(timezone.utc).isoformat()


health = LLMHealth()
_lock = threading.Lock()


def provider() -> str | None:
    """The provider to use: honours ``LLM_PROVIDER`` (auto|anthropic|openai)."""
    preference = env("LLM_PROVIDER").lower()
    has_anthropic = bool(env("ANTHROPIC_API_KEY"))
    has_openai = bool(env("OPENAI_API_KEY"))
    if preference == "anthropic":
        return "anthropic" if has_anthropic else None
    if preference == "openai":
        return "openai" if has_openai else None
    if has_anthropic:
        return "anthropic"
    if has_openai:
        return "openai"
    return None


def model_name(which: str | None = None) -> str:
    """Model id for the active (or given) provider."""
    which = which or provider()
    if which == "anthropic":
        return env("ANTHROPIC_MODEL")
    if which == "openai":
        return env("OPENAI_MODEL")
    return ""


def available() -> bool:
    """True if a key is configured (it may still turn out to be invalid)."""
    return provider() is not None


def complete(
    system: str,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 2000,
    json_mode: bool = False,
    which: str | None = None,
    timeout: float = 90.0,
) -> str:
    """Send a chat request and return the assistant's text.

    ``messages`` uses ``{"role": "user"|"assistant", "content": str}``.
    Raises :class:`LLMError` on any failure.
    """
    which = which or provider()
    if which is None:
        raise LLMError("No LLM API key configured. Add ANTHROPIC_API_KEY or OPENAI_API_KEY in Settings.")
    try:
        if which == "anthropic":
            text = _anthropic(system, messages, max_tokens, timeout)
        else:
            text = _openai(system, messages, max_tokens, json_mode, timeout)
    except LLMError as exc:
        with _lock:
            health.record_error(str(exc))
        raise
    with _lock:
        health.record_ok()
    return text


def _anthropic(system: str, messages: list[dict[str, str]], max_tokens: int, timeout: float) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=env("ANTHROPIC_API_KEY"), timeout=timeout, max_retries=2)
    try:
        # Current Claude models do not accept sampling parameters (temperature/top_p);
        # determinism comes from the strict rubric prompt and schema validation instead.
        response = client.messages.create(
            model=env("ANTHROPIC_MODEL"),
            max_tokens=max_tokens,
            system=system,
            messages=messages,  # type: ignore[arg-type]
        )
    except anthropic.AuthenticationError as exc:
        raise LLMError("Anthropic rejected the API key (401). Check ANTHROPIC_API_KEY in Settings.") from exc
    except anthropic.PermissionDeniedError as exc:
        raise LLMError(f"Anthropic denied access to model {env('ANTHROPIC_MODEL')} (403).") from exc
    except anthropic.NotFoundError as exc:
        raise LLMError(f"Anthropic model not found: {env('ANTHROPIC_MODEL')}. Check ANTHROPIC_MODEL.") from exc
    except anthropic.RateLimitError as exc:
        raise LLMError("Anthropic rate limit reached (429). Try again shortly.") from exc
    except anthropic.APIStatusError as exc:
        raise LLMError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise LLMError("Could not reach the Anthropic API (network error).") from exc
    if response.stop_reason == "refusal":
        raise LLMError("The model declined this request (refusal).")
    text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
    if not text.strip():
        raise LLMError("Anthropic returned an empty response.")
    return text


def _openai(
    system: str, messages: list[dict[str, str]], max_tokens: int, json_mode: bool, timeout: float
) -> str:
    url = env("OPENAI_BASE_URL").rstrip("/") + "/chat/completions"
    body: dict[str, Any] = {
        "model": env("OPENAI_MODEL"),
        "messages": [{"role": "system", "content": system}, *messages],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {env('OPENAI_API_KEY')}"}
    try:
        resp = httpx.post(url, json=body, headers=headers, timeout=timeout)
    except httpx.HTTPError as exc:
        raise LLMError(f"Could not reach {url}: {exc.__class__.__name__}") from exc
    if resp.status_code == 401:
        raise LLMError("The OpenAI-compatible endpoint rejected the API key (401). Check OPENAI_API_KEY.")
    if resp.status_code >= 400:
        raise LLMError(f"OpenAI-compatible API error {resp.status_code}: {resp.text[:200]}")
    try:
        return str(resp.json()["choices"][0]["message"]["content"] or "")
    except (KeyError, IndexError, ValueError) as exc:
        raise LLMError("Unexpected response shape from the OpenAI-compatible endpoint.") from exc


def extract_json(text: str) -> str:
    """Return the outermost JSON object in ``text`` (tolerates code fences / preamble)."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("No JSON object found in model output")
    return text[start : end + 1]

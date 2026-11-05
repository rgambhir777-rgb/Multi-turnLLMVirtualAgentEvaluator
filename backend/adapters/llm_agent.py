"""LLM stand-in virtual agent: wraps Claude or an OpenAI-compatible model with a system prompt."""
from __future__ import annotations

import time
from typing import Any

from .. import llm
from .base import AdapterError, AgentReply, VirtualAgentAdapter

DEFAULT_SYSTEM_PROMPT = (
    "You are Nova, the virtual agent for Northwind Telecom. Help customers with billing, plan changes, "
    "outages, password resets, cancellations, refunds and support hours. Use only the facts below; if you "
    "do not know something, say so and offer to connect the customer to a human agent. Never ask for the "
    "customer's full password. Remember details the customer already gave you (account number, ZIP code, "
    "plan) and do not ask for them again.\n\nFacts:\n{kb}"
)

CHANNEL_HINTS: dict[str, str] = {
    "chat": "Channel: web chat. Reply in 1-4 short sentences of plain text.",
    "sms": "Channel: SMS. Reply in plain text under 160 characters if possible, never over 320. No markdown or lists.",
    "email": "Channel: email. Start with a greeting, answer completely in short paragraphs, end with a sign-off.",
    "voice": "Channel: voice (text-to-speech). Speak naturally in 1-3 sentences. No URLs, markdown, tables or lists.",
}


class LLMAgentAdapter(VirtualAgentAdapter):
    """Uses an LLM as the virtual agent under test.

    Config keys:
        system_prompt: prompt template; ``{kb}`` is replaced with the knowledge base
        provider: ``auto`` | ``anthropic`` | ``openai``
        include_kb: whether to inject the KB into the prompt (default true)
    """

    def __init__(self, config: dict[str, Any] | None = None, kb_text: str = ""):
        super().__init__(config)
        self.kb_text = kb_text
        self.history: list[dict[str, str]] = []

    def _provider(self) -> str | None:
        preference = str(self.config.get("provider") or "auto")
        if preference == "auto":
            return llm.provider()
        from ..config import env

        key = "ANTHROPIC_API_KEY" if preference == "anthropic" else "OPENAI_API_KEY"
        return preference if env(key) else None

    def start_session(self, metadata: dict[str, Any] | None = None) -> str:
        if self._provider() is None:
            raise AdapterError(
                "LLM agent: no API key for the selected provider. Add ANTHROPIC_API_KEY or OPENAI_API_KEY in Settings."
            )
        self.history = []
        return "llm-session"

    def send_message(self, text: str, channel: str) -> AgentReply:
        template = str(self.config.get("system_prompt") or DEFAULT_SYSTEM_PROMPT)
        kb = self.kb_text if self.config.get("include_kb", True) else ""
        system = template.replace("{kb}", kb) + "\n\n" + CHANNEL_HINTS.get(channel, "")
        self.history.append({"role": "user", "content": text})
        started = time.perf_counter()
        try:
            reply = llm.complete(system, self.history, max_tokens=1200, which=self._provider())
        except llm.LLMError as exc:
            self.history.pop()
            raise AdapterError(f"LLM agent: {exc}") from exc
        self.history.append({"role": "assistant", "content": reply})
        return AgentReply(text=reply.strip(), latency_ms=int((time.perf_counter() - started) * 1000))

    def end_session(self) -> None:
        self.history = []

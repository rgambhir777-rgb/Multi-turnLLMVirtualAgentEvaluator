"""The pluggable virtual-agent adapter interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

CHANNELS: tuple[str, ...] = ("chat", "voice", "email", "sms")


class AdapterError(Exception):
    """Raised when an adapter cannot reach or talk to its virtual agent.

    The message is shown to the user verbatim, so it should say how to fix the problem.
    """


@dataclass
class AgentReply:
    """A single reply from the virtual agent."""

    text: str
    latency_ms: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectionCheck:
    """Result of the 'Test connection' button."""

    ok: bool
    message: str
    sample_reply: str = ""


class VirtualAgentAdapter(ABC):
    """Common interface every virtual-agent connection implements.

    The runner calls ``start_session`` once per test conversation, then
    ``send_message`` for every customer turn, then ``end_session``.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config: dict[str, Any] = dict(config or {})

    @abstractmethod
    def start_session(self, metadata: dict[str, Any] | None = None) -> str:
        """Open a conversation and return a session identifier.

        ``metadata`` may carry the script id, channel, persona and a seed key so
        adapters can tag or reproduce sessions.
        """

    @abstractmethod
    def send_message(self, text: str, channel: str) -> AgentReply:
        """Send one customer message on ``channel`` and return the agent's reply."""

    @abstractmethod
    def end_session(self) -> None:
        """Close the conversation and release any remote resources."""

    def test_connection(self) -> ConnectionCheck:
        """Run a one-message smoke test. Adapters may override for richer checks."""
        try:
            self.start_session({"seed_key": "connection-test"})
            reply = self.send_message("Hi, what are your support hours?", "chat")
            self.end_session()
        except AdapterError as exc:
            return ConnectionCheck(False, str(exc))
        except Exception as exc:  # noqa: BLE001 - surface any adapter bug as a friendly message
            return ConnectionCheck(False, f"Unexpected error: {exc}")
        return ConnectionCheck(True, f"Connected. Reply received in {reply.latency_ms} ms.", reply.text)

"""Adapter registry: build the right adapter for an agent connection."""
from __future__ import annotations

from typing import Any

from .base import CHANNELS, AdapterError, AgentReply, ConnectionCheck, VirtualAgentAdapter
from .http_adapter import GenericHTTPAdapter
from .llm_agent import LLMAgentAdapter
from .mock import PRESETS, MockAgentAdapter
from .nice_cxone import NiceCXoneAdapter

ADAPTER_TYPES: dict[str, str] = {
    "mock": "Mock Northwind agent (offline)",
    "http": "Generic HTTP bot endpoint",
    "llm": "LLM stand-in agent",
    "cxone": "NICE CXone Digital / Bot",
}


def build_adapter(adapter_type: str, config: dict[str, Any], kb_text: str = "") -> VirtualAgentAdapter:
    """Instantiate an adapter. ``kb_text`` is only used by the LLM stand-in agent."""
    if adapter_type == "mock":
        return MockAgentAdapter(config)
    if adapter_type == "http":
        return GenericHTTPAdapter(config)
    if adapter_type == "llm":
        return LLMAgentAdapter(config, kb_text=kb_text)
    if adapter_type == "cxone":
        return NiceCXoneAdapter(config)
    raise AdapterError(f"Unknown adapter type '{adapter_type}'. Choose one of: {', '.join(ADAPTER_TYPES)}.")


__all__ = [
    "ADAPTER_TYPES", "CHANNELS", "PRESETS", "AdapterError", "AgentReply", "ConnectionCheck",
    "GenericHTTPAdapter", "LLMAgentAdapter", "MockAgentAdapter", "NiceCXoneAdapter",
    "VirtualAgentAdapter", "build_adapter",
]

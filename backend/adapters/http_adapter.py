"""Generic HTTP adapter: point AgentProof at any bot that speaks JSON over HTTP."""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from typing import Any

import httpx

from .base import AdapterError, AgentReply, VirtualAgentAdapter


def expand_env(value: str) -> str:
    """Replace ``${NAME}`` with the environment variable NAME (empty if unset; port defaults to 8000)."""
    defaults = {"AGENTPROOF_PORT": "8000"}
    return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1)) or defaults.get(m.group(1), ""), value)


def get_path(data: Any, path: str) -> Any:
    """Read a dotted path such as ``data.messages.0.text`` from nested JSON."""
    current = data
    for key in [p for p in path.split(".") if p]:
        if isinstance(current, list):
            try:
                current = current[int(key)]
            except (ValueError, IndexError) as exc:
                raise KeyError(path) from exc
        elif isinstance(current, dict):
            if key not in current:
                raise KeyError(path)
            current = current[key]
        else:
            raise KeyError(path)
    return current


def set_path(data: dict[str, Any], path: str, value: Any) -> None:
    """Write ``value`` at a dotted path, creating intermediate objects."""
    keys = [p for p in path.split(".") if p]
    current = data
    for key in keys[:-1]:
        current = current.setdefault(key, {})
    current[keys[-1]] = value


class GenericHTTPAdapter(VirtualAgentAdapter):
    """POSTs each customer turn to a configurable endpoint.

    Config keys:
        url: endpoint receiving each message (required)
        method: HTTP method, default ``POST``
        headers: dict of headers (values may reference env vars as ``${NAME}``)
        request_template: JSON body template; ``{{message}}``, ``{{channel}}`` and
            ``{{session_id}}`` placeholders are substituted
        message_path / channel_path / session_path: alternatively, dotted paths
            where those values are written into the body
        response_path: dotted path of the reply text in the response JSON (required)
        session_response_path: optional dotted path of a server-issued session id
        timeout_s: request timeout, default 30
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.session_id = ""

    def start_session(self, metadata: dict[str, Any] | None = None) -> str:
        if not self.config.get("url"):
            raise AdapterError("HTTP adapter: 'url' is not configured. Edit the agent and set the endpoint URL.")
        if not self.config.get("response_path"):
            raise AdapterError("HTTP adapter: 'response_path' is not configured (e.g. 'reply' or 'data.text').")
        self.session_id = str(uuid.uuid4())
        return self.session_id

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        for key, value in dict(self.config.get("headers") or {}).items():
            headers[str(key)] = expand_env(str(value))
        return headers

    @property
    def url(self) -> str:
        return expand_env(str(self.config.get("url", "")))

    def _body(self, text: str, channel: str) -> dict[str, Any]:
        template = self.config.get("request_template")
        if template:
            raw = template if isinstance(template, str) else json.dumps(template)
            raw = (
                raw.replace("{{message}}", json.dumps(text)[1:-1])
                .replace("{{channel}}", channel)
                .replace("{{session_id}}", self.session_id)
            )
            try:
                return dict(json.loads(raw))
            except ValueError as exc:
                raise AdapterError(f"HTTP adapter: request_template is not valid JSON ({exc}).") from exc
        body: dict[str, Any] = {}
        set_path(body, str(self.config.get("message_path") or "message"), text)
        set_path(body, str(self.config.get("channel_path") or "channel"), channel)
        set_path(body, str(self.config.get("session_path") or "session_id"), self.session_id)
        return body

    def send_message(self, text: str, channel: str) -> AgentReply:
        started = time.perf_counter()
        try:
            resp = httpx.request(
                str(self.config.get("method") or "POST").upper(),
                self.url,
                json=self._body(text, channel),
                headers=self._headers(),
                timeout=float(self.config.get("timeout_s") or 30),
            )
        except httpx.HTTPError as exc:
            raise AdapterError(f"HTTP adapter: could not reach {self.url} ({exc.__class__.__name__}).") from exc
        latency = int((time.perf_counter() - started) * 1000)
        if resp.status_code >= 400:
            raise AdapterError(f"HTTP adapter: endpoint returned {resp.status_code}: {resp.text[:200]}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise AdapterError("HTTP adapter: response was not JSON.") from exc
        try:
            reply = get_path(data, str(self.config["response_path"]))
        except KeyError as exc:
            raise AdapterError(
                f"HTTP adapter: response_path '{self.config['response_path']}' not found in response: {str(data)[:200]}"
            ) from exc
        session_path = self.config.get("session_response_path")
        if session_path:
            try:
                self.session_id = str(get_path(data, str(session_path)))
            except KeyError:
                pass
        return AgentReply(text=str(reply), latency_ms=latency, raw={"response": data})

    def end_session(self) -> None:
        self.session_id = ""

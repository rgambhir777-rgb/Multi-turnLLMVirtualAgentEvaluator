"""NICE CXone adapter for Digital (DFO) / bot conversations.

Flow:
1. **Authenticate** – OAuth token from the CXone auth endpoint using your
   application's client id/secret plus a user access key (id/secret).
2. **Start session** – open a conversation (thread) on a Digital channel /
   point of contact that routes to the virtual agent under test.
3. **Send message** – post the customer message as an inbound message, then
   poll the thread for the bot's outbound reply.
4. **End session** – close the conversation so it does not stay in queues.

Every tenant configures Digital channels differently (custom messaging channel,
chat point of contact, Bot Builder / Autopilot integration), so the exact
endpoint paths are marked ``TODO(tenant)`` below. Credentials are read from the
agent config or the environment (``.env`` / Settings page) – never hard-coded.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

import httpx

from ..config import env
from .base import AdapterError, AgentReply, ConnectionCheck, VirtualAgentAdapter

REQUIRED_SETTINGS: dict[str, str] = {
    "auth_url": "CXONE_AUTH_URL",
    "api_base_url": "CXONE_API_BASE_URL",
    "client_id": "CXONE_CLIENT_ID",
    "client_secret": "CXONE_CLIENT_SECRET",
    "access_key_id": "CXONE_ACCESS_KEY_ID",
    "access_key_secret": "CXONE_ACCESS_KEY_SECRET",
    "business_unit": "CXONE_BUSINESS_UNIT",
    "channel_id": "CXONE_CHANNEL_ID",
}
OPTIONAL_SETTINGS: dict[str, str] = {"point_of_contact": "CXONE_POINT_OF_CONTACT"}


class NiceCXoneAdapter(VirtualAgentAdapter):
    """Talks to a CXone Digital channel that is routed to a virtual agent / bot."""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self._token = ""
        self._token_expiry = 0.0
        self.thread_id = ""
        self._last_message_id = ""

    # ------------------------------------------------------------------ settings
    def setting(self, name: str) -> str:
        env_key = REQUIRED_SETTINGS.get(name) or OPTIONAL_SETTINGS.get(name, "")
        return str(self.config.get(name) or (env(env_key) if env_key else ""))

    def missing_settings(self) -> list[str]:
        return [env_key for name, env_key in REQUIRED_SETTINGS.items() if not self.setting(name)]

    def _require(self) -> None:
        missing = self.missing_settings()
        if missing:
            raise AdapterError(
                "NICE CXone is not configured. Missing: " + ", ".join(missing)
                + ". Add them on the Settings page (stored in your local .env) or in this agent's config."
            )

    # ------------------------------------------------------------------ auth
    def _authenticate(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        self._require()
        try:
            resp = httpx.post(
                self.setting("auth_url"),
                data={
                    "grant_type": "password",
                    "username": self.setting("access_key_id"),
                    "password": self.setting("access_key_secret"),
                    "client_id": self.setting("client_id"),
                    "client_secret": self.setting("client_secret"),
                },
                timeout=20,
            )
        except httpx.HTTPError as exc:
            raise AdapterError(f"CXone auth: could not reach {self.setting('auth_url')} ({exc.__class__.__name__}).") from exc
        if resp.status_code in (400, 401, 403):
            raise AdapterError("CXone auth failed: check the client id/secret and access key id/secret.")
        if resp.status_code >= 400:
            raise AdapterError(f"CXone auth error {resp.status_code}: {resp.text[:200]}")
        payload = resp.json()
        self._token = str(payload.get("access_token", ""))
        self._token_expiry = time.time() + float(payload.get("expires_in", 3600))
        if not self._token:
            raise AdapterError("CXone auth: no access_token in response.")
        return self._token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._authenticate()}",
            "Content-Type": "application/json",
            # TODO(tenant): some tenants require the business unit header for DFO APIs.
            "x-business-unit": self.setting("business_unit"),
        }

    def _url(self, path: str) -> str:
        return self.setting("api_base_url").rstrip("/") + path

    # ------------------------------------------------------------------ session
    def start_session(self, metadata: dict[str, Any] | None = None) -> str:
        self._require()
        self.thread_id = f"agentproof-{uuid.uuid4()}"
        self._last_message_id = ""
        # TODO(tenant): confirm the DFO channel-integration path for your custom messaging
        # channel. Most tenants create the thread implicitly with the first inbound message,
        # so no request is sent here. If yours requires explicit creation, POST it here.
        return self.thread_id

    def send_message(self, text: str, channel: str) -> AgentReply:
        started = time.perf_counter()
        channel_id = self.setting("channel_id")
        body = {
            "thread": {"idOnExternalPlatform": self.thread_id},
            "messageContent": {"type": "TEXT", "payload": {"text": text}},
            "idOnExternalPlatform": str(uuid.uuid4()),
            "direction": "inbound",
            "authorEndUserIdentity": {
                "idOnExternalPlatform": f"agentproof-tester-{channel}",
                "firstName": "AgentProof",
                "lastName": "Tester",
            },
            # TODO(tenant): map AgentProof channel names to your point of contact if routing differs per channel.
            "pointOfContact": self.setting("point_of_contact") or None,
        }
        try:
            # TODO(tenant): verify this inbound-message endpoint for your DFO channel integration.
            resp = httpx.post(self._url(f"/dfo/3.0/channels/{channel_id}/messages"), json=body,
                              headers=self._headers(), timeout=30)
        except httpx.HTTPError as exc:
            raise AdapterError(f"CXone: could not send message ({exc.__class__.__name__}).") from exc
        if resp.status_code >= 400:
            raise AdapterError(f"CXone: inbound message rejected ({resp.status_code}): {resp.text[:200]}")
        reply = self._poll_reply(timeout_s=float(self.config.get("reply_timeout_s") or 30))
        return AgentReply(text=reply, latency_ms=int((time.perf_counter() - started) * 1000))

    def _poll_reply(self, timeout_s: float) -> str:
        """Poll the thread until the bot posts an outbound message."""
        deadline = time.time() + timeout_s
        channel_id = self.setting("channel_id")
        while time.time() < deadline:
            try:
                # TODO(tenant): verify the thread-messages listing endpoint and its paging parameters.
                resp = httpx.get(
                    self._url(f"/dfo/3.0/channels/{channel_id}/threads/{self.thread_id}/messages"),
                    headers=self._headers(),
                    timeout=20,
                )
            except httpx.HTTPError as exc:
                raise AdapterError(f"CXone: could not read replies ({exc.__class__.__name__}).") from exc
            if resp.status_code >= 400:
                raise AdapterError(f"CXone: reading replies failed ({resp.status_code}): {resp.text[:200]}")
            messages = resp.json().get("messages", [])
            outbound = [m for m in messages if m.get("direction") == "outbound" and m.get("id") != self._last_message_id]
            if outbound:
                latest = outbound[-1]
                self._last_message_id = str(latest.get("id", ""))
                return str(latest.get("messageContent", {}).get("payload", {}).get("text", ""))
            time.sleep(1.0)
        raise AdapterError(f"CXone: no bot reply within {timeout_s:.0f}s. Check the channel routes to the virtual agent.")

    def end_session(self) -> None:
        if not self.thread_id or self.missing_settings():
            return
        try:
            # TODO(tenant): close/resolve the contact so test conversations do not linger in queues.
            httpx.post(
                self._url(f"/dfo/3.0/channels/{self.setting('channel_id')}/threads/{self.thread_id}/close"),
                headers=self._headers(),
                timeout=10,
            )
        except (httpx.HTTPError, AdapterError):
            pass
        self.thread_id = ""

    def test_connection(self) -> ConnectionCheck:
        missing = self.missing_settings()
        if missing:
            return ConnectionCheck(
                False,
                "NICE CXone is not configured yet. Missing: " + ", ".join(missing)
                + ". Add them on the Settings page.",
            )
        try:
            self._authenticate()
        except AdapterError as exc:
            return ConnectionCheck(False, str(exc))
        return super().test_connection()

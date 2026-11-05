"""Adapter tests: mock agent behaviour and graceful failures of the remote adapters."""
from __future__ import annotations

import pytest

from backend.adapters import AdapterError, GenericHTTPAdapter, LLMAgentAdapter, MockAgentAdapter, NiceCXoneAdapter, build_adapter
from backend.adapters.http_adapter import expand_env, get_path, set_path


def converse(adapter: MockAgentAdapter, messages: list[str], channel: str = "chat", seed: str = "t") -> list[str]:
    adapter.start_session({"seed_key": seed})
    replies = [adapter.send_message(m, channel).text for m in messages]
    adapter.end_session()
    return replies


def test_mock_session_lifecycle_returns_replies():
    adapter = MockAgentAdapter({"preset": "v3"})
    session = adapter.start_session({"seed_key": "x"})
    reply = adapter.send_message("What are your phone support hours?", "chat")
    adapter.end_session()
    assert session.startswith("mock-")
    assert "8 AM" in reply.text and "10 PM" in reply.text
    assert reply.latency_ms >= 1


def test_mock_v3_remembers_account_from_turn_one():
    replies = converse(MockAgentAdapter({"preset": "v3"}), [
        "Hi, account NW-123456 here. When is my bill due?",
        "Do you offer a discount if I pay automatically?",
        "What time can I call phone support?",
        "Great, please enroll my account in autopay.",
    ])
    assert "21st" in replies[0]
    assert "NW-123456" in replies[3]
    assert "provide your account number" not in replies[3]


def test_mock_v3_handles_plan_correction():
    replies = converse(MockAgentAdapter({"preset": "v3"}), [
        "My account number is NW-555111.",
        "I want to upgrade to Fiber 500.",
        "Actually sorry, I meant the Fiber Gig plan, not Fiber 500.",
        "Yes, go ahead with that.",
    ])
    assert "$79.99" in replies[2]
    assert "Fiber Gig" in replies[3] and "Fiber 500" not in replies[3]


def test_mock_v3_formats_for_channels():
    sms = converse(MockAgentAdapter({"preset": "v3"}), ["I want to cancel my service, account NW-222333."], "sms")[0]
    email = converse(MockAgentAdapter({"preset": "v3"}), ["How do I reset my password?"], "email")[0]
    voice = converse(MockAgentAdapter({"preset": "v3"}), ["How do I reset my password?"], "voice")[0]
    assert len(sms) <= 320 and "**" not in sms
    assert email.startswith(("Hi", "Hello")) and "Kind regards" in email
    assert "northwind.example" not in voice


def test_mock_v1_injects_flaws_across_many_turns():
    adapter = MockAgentAdapter({"preset": "v1"})
    replies = []
    for i in range(12):
        replies += converse(adapter, [
            "My account number is NW-777888.",
            "How much is the Fiber 500 plan?",
            "Please enroll my account in autopay.",
        ], seed=f"flaw-{i}")
    text = "\n".join(replies)
    assert "provide your account number" in text  # context loss
    assert "$49.99" in text  # wrong fact
    assert "**" in text and "https://" in text  # channel-blind formatting


def test_mock_flaw_rates_are_configurable_and_deterministic():
    flawless = MockAgentAdapter({"preset": "v1", "context_loss_rate": 0, "wrong_fact_rate": 0,
                                 "hallucination_rate": 0, "channel_awareness": 1})
    reply = converse(flawless, ["How much is the Fiber 500 plan?"])[0]
    assert "$59.99" in reply and "**" not in reply
    a = converse(MockAgentAdapter({"preset": "v1"}), ["How much is Fiber 500?"], seed="same")
    b = converse(MockAgentAdapter({"preset": "v1"}), ["How much is Fiber 500?"], seed="same")
    assert a == b


def test_mock_understands_speech_to_text_noise():
    reply = converse(MockAgentAdapter({"preset": "v3"}), ["um hi uh my account is n w 482913 and i'd like to upgrade too fiber 500"], "voice")[0]
    assert "NW-482913" in reply and "$59.99" in reply


def test_http_path_helpers_and_env_expansion(monkeypatch):
    data = {"data": {"messages": [{"text": "hello"}]}}
    assert get_path(data, "data.messages.0.text") == "hello"
    with pytest.raises(KeyError):
        get_path(data, "data.missing")
    body: dict = {}
    set_path(body, "input.text", "hi")
    assert body == {"input": {"text": "hi"}}
    monkeypatch.setenv("BOT_TOKEN", "abc")
    assert expand_env("Bearer ${BOT_TOKEN}") == "Bearer abc"


def test_http_adapter_requires_url_and_reports_unreachable_endpoint():
    with pytest.raises(AdapterError, match="url"):
        GenericHTTPAdapter({}).start_session()
    adapter = GenericHTTPAdapter({"url": "http://127.0.0.1:9/never", "response_path": "reply", "timeout_s": 1})
    check = adapter.test_connection()
    assert not check.ok and "could not reach" in check.message


def test_cxone_adapter_fails_gracefully_without_credentials():
    adapter = NiceCXoneAdapter({})
    check = adapter.test_connection()
    assert not check.ok
    assert "CXONE_CLIENT_ID" in check.message and "Settings" in check.message
    with pytest.raises(AdapterError):
        adapter.start_session()


def test_llm_agent_without_key_raises_friendly_error():
    with pytest.raises(AdapterError, match="API key"):
        LLMAgentAdapter({"provider": "auto"}).start_session()


def test_build_adapter_rejects_unknown_type():
    assert isinstance(build_adapter("mock", {"preset": "v2"}), MockAgentAdapter)
    with pytest.raises(AdapterError):
        build_adapter("carrier-pigeon", {})

"""Judge tests: the heuristic judge detects each flaw type; the LLM judge validates, retries and falls back."""
from __future__ import annotations

import json

import pytest

from backend import llm
from backend.channels import evaluate_channel_fit, simulate_stt
from backend.judges import TurnInput, heuristic, judge_turn, llm_judge


def turn(kb, reply: str, customer: str = "", history=None, channel: str = "chat", **expectations) -> TurnInput:
    exp = {"must_include": [], "must_not_include": [], "must_remember": [], "notes": ""}
    exp.update(expectations)
    return TurnInput(index=len(history or []), channel=channel, customer_text=customer, agent_text=reply,
                     history=history or [], expectations=exp, kb=kb)


HISTORY = [("Hi, my account number is NW-123456.", "Thanks, I've verified account NW-123456.")]


def test_good_answer_scores_full_marks(kb):
    result = heuristic.judge_turn(turn(kb, "The Fiber 500 plan provides 500 Mbps and costs $59.99 per month.",
                                       "How much is Fiber 500?", must_include=["$59.99"]))
    assert result.accuracy_score == 5 and result.hallucination_score == 5
    assert all(c.label == "Supported" for c in result.claims)
    assert not result.critical


def test_context_loss_reasking_for_given_account_is_detected(kb):
    result = heuristic.judge_turn(turn(kb, "Before I continue, could you please provide your account number?",
                                       "Please enroll my account in autopay.", HISTORY, must_remember=["NW-123456"]))
    assert result.context_score <= 1
    assert "re-asked" in result.context_justification
    assert result.context_applicable


def test_context_loss_using_wrong_account_is_detected(kb):
    result = heuristic.judge_turn(turn(kb, "Done. I've enrolled account NW-999999 in autopay.", "Enroll me please.", HISTORY))
    assert result.context_score <= 2
    assert "NW-999999" in result.context_justification


def test_wrong_fact_is_contradicted_and_critical(kb):
    result = heuristic.judge_turn(turn(kb, "The Fiber 500 plan costs $49.99 per month.", "How much is Fiber 500?",
                                       must_include=["$59.99"]))
    labels = [c.label for c in result.claims]
    assert "Contradicted" in labels
    assert result.accuracy_score <= 1 and result.critical
    assert "$59.99" in result.claims[0].evidence


def test_wrong_free_downgrade_policy_is_contradicted(kb):
    result = heuristic.judge_turn(turn(kb, "Downgrading to a slower plan is free of charge.", "Is there a fee to downgrade?"))
    assert result.claims and result.claims[0].label == "Contradicted"


def test_hallucinated_policy_is_unsupported(kb):
    result = heuristic.judge_turn(turn(kb, "Phone support is available from 8 AM to 10 PM Eastern Time, 7 days a week. "
                                           "Northwind also offers a lifetime price lock guarantee on every plan.",
                                       "What are your hours?"))
    bad = [c for c in result.claims if c.label != "Supported"]
    assert len(bad) == 1 and bad[0].label == "Unsupported" and "price lock" in bad[0].text
    assert result.hallucinated and result.hallucination_score == 3


def test_hallucinated_number_is_flagged(kb):
    result = heuristic.judge_turn(turn(kb, "As a loyalty bonus, I've also added a $25 credit to your next bill.", "Thanks"))
    assert result.hallucinated and result.hallucination_score <= 3


def test_customer_stated_numbers_are_supported(kb):
    result = heuristic.judge_turn(turn(kb, "I can see the refund of $45.20 is approved.", "My refund is for $45.20.",
                                       must_remember=[]))
    assert not result.hallucinated


def test_forbidden_content_and_password_requests_are_critical(kb):
    forbidden = heuristic.judge_turn(turn(kb, "I've submitted the cancellation request.", "Switch me to Basic 100 instead.",
                                          must_not_include=["cancellation request"]))
    assert forbidden.critical and "must not say" in forbidden.critical_reason
    password = heuristic.judge_turn(turn(kb, "Sure, share your current password and I'll check it.", "Should I tell you my password?"))
    assert password.critical and password.accuracy_score == 0
    safe = heuristic.judge_turn(turn(kb, "Please don't share your password. Northwind agents never ask customers for their full password.",
                                     "Should I tell you my password?"))
    assert not safe.critical


def test_empty_reply_is_critical(kb):
    result = heuristic.judge_turn(turn(kb, "", "Hello?"))
    assert result.critical and result.accuracy_score == 0


def test_channel_fit_rules():
    long_sms = "word " * 120
    assert evaluate_channel_fit(long_sms, "sms").score < 3
    assert evaluate_channel_fit("Short and plain.", "sms").score == 5
    voice = evaluate_channel_fit("**Visit https://northwind.example/help**", "voice")
    assert voice.score <= 2 and any("URL" in f for f in voice.flags)
    email = evaluate_channel_fit("No greeting and no sign off.", "email")
    assert "no greeting" in email.flags and "no sign-off" in email.flags
    good_email = evaluate_channel_fit("Hi Sam,\n\nThank you for contacting us. " + "Details here. " * 10 + "\n\nKind regards,\nNova", "email")
    assert good_email.score == 5


def test_stt_simulation_is_noisy_but_keeps_key_entities():
    out = simulate_stt("My account is NW-482913 and my refund was $45.20.", "seed")
    assert "n w 482913" in out and "45.20 dollars" in out
    assert out == out.lower() and "." not in out.replace("45.20", "")


VALID = {"context_score": 4, "context_justification": "ok", "accuracy_score": 5, "accuracy_justification": "ok",
         "claims": [{"text": "Costs $59.99", "label": "Supported", "evidence": "KB Fiber 500"},
                    {"text": "Free router", "label": "Unsupported", "evidence": "not in KB"}],
         "critical": False, "critical_reason": ""}


def test_llm_judge_retries_invalid_json_then_validates(kb, monkeypatch):
    outputs = iter(["not json at all", json.dumps({"context_score": 9}), "```json\n" + json.dumps(VALID) + "\n```"])
    calls = []

    def fake_complete(system, messages, **kwargs):
        calls.append(messages)
        return next(outputs)

    monkeypatch.setattr(llm, "complete", fake_complete)
    monkeypatch.setattr(llm, "model_name", lambda which=None: "test-model")
    result = llm_judge.judge_turn(turn(kb, "The Fiber 500 plan costs $59.99 per month.", "Price?", must_include=["$59.99"]))
    assert len(calls) == 3
    assert result.judge == "llm:test-model"
    assert result.hallucination_score == 3  # derived from claims: one unsupported
    assert result.expectations_met == 1


def test_llm_judge_gives_up_after_max_attempts(kb, monkeypatch):
    monkeypatch.setattr(llm, "complete", lambda *a, **k: "still not json")
    with pytest.raises(llm.LLMError):
        llm_judge.judge_turn(turn(kb, "Hello", "Hi"))


def test_judge_falls_back_to_heuristic_and_trips_breaker(kb, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "invalid-key")
    calls = []

    def failing(*args, **kwargs):
        calls.append(1)
        raise llm.LLMError("Anthropic rejected the API key (401).")

    monkeypatch.setattr(llm, "complete", failing)
    breaker: dict = {}
    first = judge_turn(turn(kb, "The Fiber 500 plan costs $59.99 per month.", "Price?"), "auto", breaker)
    second = judge_turn(turn(kb, "The Fiber 500 plan costs $59.99 per month.", "Price?"), "auto", breaker)
    assert first.judge == second.judge == "heuristic (LLM fallback)"
    assert breaker["tripped"] and len(calls) == 1

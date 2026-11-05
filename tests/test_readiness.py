"""Readiness verdict logic tests."""
from __future__ import annotations

from backend.readiness import ConversationStats, TurnStats, compute_metrics, summarize, verdict

BASE = {"turns": 100, "conversations": 20, "avg_accuracy": 4.6, "avg_context": 4.5, "avg_hallucination": 4.9,
        "hallucination_rate": 0.01, "hallucinated_turns": 1, "avg_channel_fit": 4.4, "task_completion_rate": 0.95,
        "critical_failures": 0}


def test_all_thresholds_met_is_go():
    result = verdict(BASE)
    assert result["verdict"] == "GO" and not result["reasons"]
    assert len(result["passed"]) == 6


def test_narrow_miss_is_conditional():
    result = verdict({**BASE, "avg_accuracy": 3.8})
    assert result["verdict"] == "CONDITIONAL"
    assert result["reasons"][0]["severity"] == "soft"


def test_hallucination_rate_bands():
    assert verdict({**BASE, "hallucination_rate": 0.03, "hallucinated_turns": 3})["verdict"] == "CONDITIONAL"
    assert verdict({**BASE, "hallucination_rate": 0.05, "hallucinated_turns": 5})["verdict"] == "NO-GO"


def test_wide_miss_or_critical_failure_is_no_go():
    assert verdict({**BASE, "avg_context": 3.0})["verdict"] == "NO-GO"
    result = verdict({**BASE, "critical_failures": 1})
    assert result["verdict"] == "NO-GO" and "critical" in result["reasons"][0]["text"]


def test_hard_reasons_are_listed_first():
    result = verdict({**BASE, "avg_accuracy": 3.8, "critical_failures": 2})
    assert [r["severity"] for r in result["reasons"]] == ["hard", "soft"]


def test_custom_thresholds_are_respected():
    assert verdict({**BASE, "avg_accuracy": 4.2}, {"min_accuracy": 4.5, "score_margin": 0.1})["verdict"] == "NO-GO"
    assert verdict({**BASE, "critical_failures": 2}, {"max_critical_failures": 2})["verdict"] == "GO"


def test_no_turns_is_no_go():
    assert verdict({"turns": 0})["verdict"] == "NO-GO"


def test_metrics_and_per_channel_verdicts():
    good = TurnStats(5, 5, 5, 5, False, False, True)
    bad = TurnStats(2, 1, 2, 2, True, True, True)
    conversations = [
        ConversationStats("chat", True, [good, good]),
        ConversationStats("voice", False, [bad, good]),
    ]
    metrics = compute_metrics(conversations)
    assert metrics["turns"] == 4 and metrics["hallucinated_turns"] == 1
    assert metrics["task_completion_rate"] == 0.5 and metrics["critical_failures"] == 1
    summary = summarize(conversations)
    assert summary["by_channel"]["chat"]["verdict"] == "GO"
    assert summary["by_channel"]["voice"]["verdict"] == "NO-GO"
    assert summary["verdict"] == "NO-GO"


def test_context_average_ignores_turns_without_context():
    turns = [TurnStats(5, 5, 5, 5, False, False, False), TurnStats(2, 5, 5, 5, False, False, True)]
    assert compute_metrics([ConversationStats("chat", True, turns)])["avg_context"] == 2.0

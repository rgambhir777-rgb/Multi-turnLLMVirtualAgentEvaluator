"""Readiness metrics and the GO / CONDITIONAL / NO-GO verdict.

Each threshold is checked against the run's metrics. Missing a threshold by a
small margin (inside the "conditional band") is a *soft* failure; missing it by
more, or any critical failure, is a *hard* failure.

* GO          – every threshold met and no critical failures
* CONDITIONAL – only soft failures (fixable gaps; release with conditions)
* NO-GO       – at least one hard failure
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DEFAULT_THRESHOLDS: dict[str, float] = {
    "min_accuracy": 4.0,
    "min_context": 4.0,
    "max_hallucination_rate": 0.02,
    "min_channel_fit": 3.5,
    "min_task_completion": 0.80,
    "max_critical_failures": 0,
    "score_margin": 0.5,
    "rate_multiplier": 2.0,
    "completion_margin": 0.10,
}

THRESHOLD_LABELS: dict[str, str] = {
    "min_accuracy": "Minimum average accuracy (0–5)",
    "min_context": "Minimum average context awareness (0–5)",
    "max_hallucination_rate": "Maximum share of turns with a hallucinated claim",
    "min_channel_fit": "Minimum average channel fit (0–5)",
    "min_task_completion": "Minimum task completion rate",
    "max_critical_failures": "Maximum critical failures",
    "score_margin": "Conditional band below score thresholds",
    "rate_multiplier": "Conditional band for hallucination rate (× threshold)",
    "completion_margin": "Conditional band below task completion",
}


@dataclass
class TurnStats:
    """Minimal per-turn data needed for metrics."""

    context: float
    accuracy: float
    hallucination: float
    channel_fit: float
    hallucinated: bool
    critical: bool
    context_applicable: bool = True


@dataclass
class ConversationStats:
    channel: str
    task_completed: bool
    turns: list[TurnStats] = field(default_factory=list)


def compute_metrics(conversations: list[ConversationStats]) -> dict[str, Any]:
    """Aggregate turn/conversation stats into readiness metrics."""
    turns = [t for c in conversations for t in c.turns]
    n = len(turns)
    if n == 0:
        return {"turns": 0, "conversations": len(conversations), "avg_accuracy": 0.0, "avg_context": 0.0,
                "avg_hallucination": 0.0, "hallucination_rate": 0.0, "avg_channel_fit": 0.0,
                "task_completion_rate": 0.0, "critical_failures": 0, "hallucinated_turns": 0}

    def avg(values: list[float]) -> float:
        return round(sum(values) / len(values), 3) if values else 0.0

    hallucinated = sum(1 for t in turns if t.hallucinated)
    context_turns = [t.context for t in turns if t.context_applicable] or [t.context for t in turns]
    return {
        "turns": n,
        "conversations": len(conversations),
        "avg_accuracy": avg([t.accuracy for t in turns]),
        "avg_context": avg(context_turns),
        "context_turns": len(context_turns),
        "avg_hallucination": avg([t.hallucination for t in turns]),
        "hallucination_rate": round(hallucinated / n, 4),
        "hallucinated_turns": hallucinated,
        "avg_channel_fit": avg([t.channel_fit for t in turns]),
        "task_completion_rate": round(sum(1 for c in conversations if c.task_completed) / len(conversations), 4)
        if conversations else 0.0,
        "critical_failures": sum(1 for t in turns if t.critical),
    }


def verdict(metrics: dict[str, Any], thresholds: dict[str, float] | None = None) -> dict[str, Any]:
    """Return ``{"verdict": GO|CONDITIONAL|NO-GO, "reasons": [...], "passed": [...]}``."""
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    if not metrics.get("turns"):
        return {"verdict": "NO-GO", "reasons": [{"severity": "hard", "text": "No scored turns – nothing to assess."}], "passed": []}
    reasons: list[dict[str, str]] = []
    passed: list[str] = []

    def check_min(key: str, metric: str, label: str, margin: float, fmt: str = "{:.2f}") -> None:
        value, limit = float(metrics[metric]), float(th[key])
        if value >= limit:
            passed.append(f"{label} {fmt.format(value)} ≥ {fmt.format(limit)}")
            return
        severity = "soft" if value >= limit - margin else "hard"
        reasons.append({"severity": severity, "text": f"{label} {fmt.format(value)} is below the {fmt.format(limit)} threshold"})

    check_min("min_accuracy", "avg_accuracy", "Average accuracy", th["score_margin"])
    check_min("min_context", "avg_context", "Context awareness", th["score_margin"])
    check_min("min_channel_fit", "avg_channel_fit", "Channel fit", th["score_margin"])
    check_min("min_task_completion", "task_completion_rate", "Task completion", th["completion_margin"], "{:.0%}")

    rate, limit = float(metrics["hallucination_rate"]), float(th["max_hallucination_rate"])
    if rate <= limit:
        passed.append(f"Hallucination rate {rate:.1%} ≤ {limit:.1%}")
    else:
        severity = "soft" if rate <= limit * th["rate_multiplier"] else "hard"
        reasons.append({"severity": severity, "text": f"Hallucination rate {rate:.1%} exceeds the {limit:.1%} limit ({metrics['hallucinated_turns']} turns)"})

    critical, max_critical = int(metrics["critical_failures"]), int(th["max_critical_failures"])
    if critical <= max_critical:
        passed.append(f"Critical failures {critical} ≤ {max_critical}")
    else:
        reasons.append({"severity": "hard", "text": f"{critical} critical failure(s) (wrong facts, forbidden content or security issues)"})

    reasons.sort(key=lambda r: r["severity"] != "hard")  # hard blockers first
    if any(r["severity"] == "hard" for r in reasons):
        result = "NO-GO"
    elif reasons:
        result = "CONDITIONAL"
    else:
        result = "GO"
    return {"verdict": result, "reasons": reasons, "passed": passed}


def summarize(conversations: list[ConversationStats], thresholds: dict[str, float] | None = None) -> dict[str, Any]:
    """Overall + per-channel metrics and verdicts."""
    overall = compute_metrics(conversations)
    by_channel: dict[str, Any] = {}
    for channel in sorted({c.channel for c in conversations}):
        subset = [c for c in conversations if c.channel == channel]
        metrics = compute_metrics(subset)
        by_channel[channel] = {"metrics": metrics, **verdict(metrics, thresholds)}
    return {"metrics": overall, **verdict(overall, thresholds), "by_channel": by_channel}

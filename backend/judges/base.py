"""Shared judge types and the claim-based hallucination score."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..kb import KnowledgeIndex

ClaimLabel = Literal["Supported", "Contradicted", "Unsupported"]


class ClaimResult(BaseModel):
    """One factual claim from an agent reply and its verification label."""

    text: str
    label: ClaimLabel
    evidence: str = ""


class TurnJudgement(BaseModel):
    """All scores for one agent turn. Scores are 0–5 (5 = best)."""

    context_score: float = Field(ge=0, le=5)
    context_justification: str
    #: True when the turn depends on earlier context (memory expected, details given before,
    #: or a context problem was found). Readiness averages context only over these turns.
    context_applicable: bool = False
    accuracy_score: float = Field(ge=0, le=5)
    accuracy_justification: str
    claims: list[ClaimResult] = Field(default_factory=list)
    hallucination_score: float = Field(ge=0, le=5)
    hallucination_justification: str
    channel_fit_score: float = Field(ge=0, le=5)
    channel_justification: str
    channel_flags: list[str] = Field(default_factory=list)
    critical: bool = False
    critical_reason: str = ""
    expectations_met: int = 0
    expectations_total: int = 0
    judge: str = "heuristic"

    @property
    def hallucinated(self) -> bool:
        return any(c.label != "Supported" for c in self.claims)


@dataclass
class TurnInput:
    """Everything a judge needs to score one agent turn."""

    index: int
    channel: str
    customer_text: str
    agent_text: str
    history: list[tuple[str, str]]  # previous (customer, agent) pairs, oldest first
    expectations: dict[str, Any]
    kb: KnowledgeIndex
    persona: dict[str, Any] = field(default_factory=dict)
    goal: str = ""

    @property
    def customer_history(self) -> list[str]:
        return [c for c, _ in self.history]


def hallucination_score(claims: list[ClaimResult]) -> float:
    """5 = every claim supported. Each contradicted claim costs 3, each unsupported claim 2."""
    contradicted = sum(1 for c in claims if c.label == "Contradicted")
    unsupported = sum(1 for c in claims if c.label == "Unsupported")
    return float(max(0.0, 5.0 - 3.0 * contradicted - 2.0 * unsupported))


def hallucination_justification(claims: list[ClaimResult]) -> str:
    """Human-readable summary of the claim table."""
    if not claims:
        return "No checkable factual claims in this reply."
    counts = {label: sum(1 for c in claims if c.label == label) for label in ("Supported", "Contradicted", "Unsupported")}
    summary = f"{len(claims)} claim(s): {counts['Supported']} supported, {counts['Contradicted']} contradicted, {counts['Unsupported']} unsupported."
    bad = [c for c in claims if c.label != "Supported"]
    if bad:
        summary += " " + " ".join(f'{c.label}: "{c.text}" ({c.evidence})' for c in bad[:3])
    return summary

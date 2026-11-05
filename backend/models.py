"""ORM models: KB, transcripts, journeys, scripts, agents, runs, conversations, turns, claims."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    """Timezone-aware current UTC time."""
    return datetime.now(timezone.utc)


class KBFact(Base):
    """A ground-truth fact or policy the judge checks agent replies against."""

    __tablename__ = "kb_facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(80), default="General")
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Transcript(Base):
    """A historical customer conversation used for journey discovery."""

    __tablename__ = "transcripts"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(80), default="")
    channel: Mapped[str] = mapped_column(String(20), default="chat")
    turns: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    journey_id: Mapped[int | None] = mapped_column(
        ForeignKey("journeys.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Journey(Base):
    """A customer journey (intent cluster), discovered or created manually."""

    __tablename__ = "journeys"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    intent: Mapped[str] = mapped_column(String(60), default="general")
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    frequency: Mapped[int] = mapped_column(Integer, default=0)
    avg_turns: Mapped[float] = mapped_column(Float, default=0.0)
    example_utterances: Mapped[list[str]] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    labeler: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    scripts: Mapped[list[TestScript]] = relationship(back_populates="journey")


class TestScript(Base):
    """A multi-turn test conversation with per-turn expectations.

    ``turns`` is a list of dicts with keys ``customer``, ``must_include``,
    ``must_not_include``, ``must_remember`` and ``notes``.
    """

    __tablename__ = "test_scripts"
    __test__ = False  # not a pytest test class

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    journey_id: Mapped[int | None] = mapped_column(
        ForeignKey("journeys.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(20), default="chat")
    variant: Mapped[str] = mapped_column(String(40), default="standard")
    persona: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    goal: Mapped[str] = mapped_column(Text, default="")
    email_subject: Mapped[str] = mapped_column(String(200), default="")
    turns: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    journey: Mapped[Journey | None] = relationship(back_populates="scripts")


class Agent(Base):
    """A virtual agent connection (adapter type + configuration)."""

    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    adapter_type: Mapped[str] = mapped_column(String(20), default="mock")
    description: Mapped[str] = mapped_column(Text, default="")
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Run(Base):
    """A test run: selected scripts x one agent x channels."""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    agent_name: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(20), default="queued")
    script_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    channels: Mapped[list[str]] = mapped_column(JSON, default=list)
    judge_mode: Mapped[str] = mapped_column(String(20), default="auto")
    total_conversations: Mapped[int] = mapped_column(Integer, default=0)
    completed_conversations: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="Conversation.id"
    )


class Conversation(Base):
    """One executed test script on one channel within a run."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    script_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_scripts.id", ondelete="SET NULL"), nullable=True
    )
    script_name: Mapped[str] = mapped_column(String(200), default="")
    journey_name: Mapped[str] = mapped_column(String(160), default="")
    variant: Mapped[str] = mapped_column(String(40), default="standard")
    channel: Mapped[str] = mapped_column(String(20), default="chat")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    email_subject: Mapped[str] = mapped_column(String(200), default="")
    persona: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    goal: Mapped[str] = mapped_column(Text, default="")
    task_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    task_score: Mapped[float] = mapped_column(Float, default=0.0)
    task_justification: Mapped[str] = mapped_column(Text, default="")
    avg_context: Mapped[float] = mapped_column(Float, default=0.0)
    avg_accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    avg_hallucination: Mapped[float] = mapped_column(Float, default=0.0)
    avg_channel_fit: Mapped[float] = mapped_column(Float, default=0.0)
    critical_failures: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")

    run: Mapped[Run] = relationship(back_populates="conversations")
    turns: Mapped[list[Turn]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Turn.index"
    )


class Turn(Base):
    """One customer message and the agent's reply, with all scores."""

    __tablename__ = "turns"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    index: Mapped[int] = mapped_column(Integer)
    customer_text: Mapped[str] = mapped_column(Text)
    customer_rendered: Mapped[str] = mapped_column(Text)
    agent_text: Mapped[str] = mapped_column(Text, default="")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    expectations: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    context_score: Mapped[float] = mapped_column(Float, default=0.0)
    context_applicable: Mapped[bool] = mapped_column(Boolean, default=False)
    accuracy_score: Mapped[float] = mapped_column(Float, default=0.0)
    hallucination_score: Mapped[float] = mapped_column(Float, default=0.0)
    channel_fit_score: Mapped[float] = mapped_column(Float, default=0.0)
    context_justification: Mapped[str] = mapped_column(Text, default="")
    accuracy_justification: Mapped[str] = mapped_column(Text, default="")
    hallucination_justification: Mapped[str] = mapped_column(Text, default="")
    channel_justification: Mapped[str] = mapped_column(Text, default="")
    channel_flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    hallucinated: Mapped[bool] = mapped_column(Boolean, default=False)
    critical: Mapped[bool] = mapped_column(Boolean, default=False)
    critical_reason: Mapped[str] = mapped_column(Text, default="")
    judge: Mapped[str] = mapped_column(String(80), default="heuristic")

    conversation: Mapped[Conversation] = relationship(back_populates="turns")
    claims: Mapped[list[Claim]] = relationship(
        back_populates="turn", cascade="all, delete-orphan", order_by="Claim.id"
    )


class Claim(Base):
    """A factual claim extracted from an agent reply and its verification label."""

    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    turn_id: Mapped[int] = mapped_column(ForeignKey("turns.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(String(20))  # Supported | Contradicted | Unsupported
    evidence: Mapped[str] = mapped_column(Text, default="")

    turn: Mapped[Turn] = relationship(back_populates="claims")


class AppSetting(Base):
    """Non-secret application settings (thresholds, judge mode) as JSON values."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)

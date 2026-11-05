"""Test-run execution: drive conversations through an adapter, judge every turn, store results."""
from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .adapters import AdapterError, VirtualAgentAdapter, build_adapter
from .channels import render_customer_turn
from .database import session_scope
from .judges import TurnInput, TurnJudgement, effective_mode, judge_turn
from .kb import KnowledgeIndex
from .models import Agent, Claim, Conversation, KBFact, Run, TestScript, Turn
from .readiness import ConversationStats, TurnStats, summarize
from .settings_store import get_setting


@dataclass
class TurnOutcome:
    customer_text: str
    customer_rendered: str
    agent_text: str
    latency_ms: int
    expectations: dict[str, Any]
    judgement: TurnJudgement


@dataclass
class ConversationOutcome:
    turns: list[TurnOutcome] = field(default_factory=list)
    task_completed: bool = False
    task_score: float = 0.0
    task_justification: str = ""
    error: str = ""


def load_kb(db: Session) -> KnowledgeIndex:
    """Build the KB index from the database."""
    rows = db.scalars(select(KBFact).order_by(KBFact.id)).all()
    return KnowledgeIndex.from_rows([{"id": r.id, "category": r.category, "title": r.title, "content": r.content} for r in rows])


def kb_as_text(kb: KnowledgeIndex) -> str:
    return "\n".join(f"- {f.title}: {f.content}" for f in kb.facts)


def execute_conversation(
    adapter: VirtualAgentAdapter,
    script: dict[str, Any],
    channel: str,
    kb: KnowledgeIndex,
    *,
    judge_mode: str = "auto",
    seed_key: str = "",
    breaker: dict[str, object] | None = None,
) -> ConversationOutcome:
    """Run one scripted conversation on one channel and judge each agent turn.

    ``script`` needs ``turns`` and may include ``persona``, ``goal`` and ``email_subject``.
    """
    outcome = ConversationOutcome()
    persona = script.get("persona") or {}
    history: list[tuple[str, str]] = []
    try:
        adapter.start_session({"seed_key": seed_key, "channel": channel, "persona": persona, "script": script.get("name")})
    except AdapterError as exc:
        outcome.error = str(exc)
        return outcome
    try:
        for index, turn in enumerate(script.get("turns", [])):
            rendered = render_customer_turn(
                turn["customer"], channel, turn_index=index, subject=script.get("email_subject", ""),
                persona_name=persona.get("name", ""), seed_key=seed_key,
            )
            try:
                reply = adapter.send_message(rendered, channel)
                reply_text, latency = reply.text, reply.latency_ms
            except AdapterError as exc:
                outcome.error = str(exc)
                reply_text, latency = "", 0
            expectations = {k: turn.get(k, []) for k in ("must_include", "must_not_include", "must_remember")}
            expectations["notes"] = turn.get("notes", "")
            judgement = judge_turn(
                TurnInput(index=index, channel=channel, customer_text=rendered, agent_text=reply_text,
                          history=list(history), expectations=expectations, kb=kb, persona=persona,
                          goal=script.get("goal", "")),
                judge_mode,
                breaker,
            )
            outcome.turns.append(TurnOutcome(turn["customer"], rendered, reply_text, latency, expectations, judgement))
            history.append((rendered, reply_text))
            if outcome.error:
                break
    finally:
        try:
            adapter.end_session()
        except AdapterError:
            pass

    met = sum(t.judgement.expectations_met for t in outcome.turns)
    total = sum(t.judgement.expectations_total for t in outcome.turns)
    ratio = met / total if total else (1.0 if outcome.turns else 0.0)
    critical = sum(1 for t in outcome.turns if t.judgement.critical)
    outcome.task_score = round(5 * ratio, 2)
    outcome.task_completed = ratio >= 0.8 and critical == 0 and not outcome.error
    reasons = [f"{met}/{total} expected facts and remembered details delivered"]
    if critical:
        reasons.append(f"{critical} critical failure(s)")
    if outcome.error:
        reasons.append(f"conversation aborted: {outcome.error}")
    outcome.task_justification = ("Goal achieved: " if outcome.task_completed else "Goal not achieved: ") + "; ".join(reasons) + "."
    return outcome


def _store_conversation(conv: Conversation, outcome: ConversationOutcome) -> None:
    conv.task_completed = outcome.task_completed
    conv.task_score = outcome.task_score
    conv.task_justification = outcome.task_justification
    conv.error = outcome.error
    conv.status = "failed" if outcome.error and not outcome.turns else "completed"
    judgements = [t.judgement for t in outcome.turns]
    if judgements:
        ctx = [j.context_score for j in judgements if j.context_applicable] or [j.context_score for j in judgements]
        conv.avg_context = round(sum(ctx) / len(ctx), 3)
        conv.avg_accuracy = round(sum(j.accuracy_score for j in judgements) / len(judgements), 3)
        conv.avg_hallucination = round(sum(j.hallucination_score for j in judgements) / len(judgements), 3)
        conv.avg_channel_fit = round(sum(j.channel_fit_score for j in judgements) / len(judgements), 3)
    conv.critical_failures = sum(1 for j in judgements if j.critical)
    for index, t in enumerate(outcome.turns):
        j = t.judgement
        turn = Turn(
            index=index, customer_text=t.customer_text, customer_rendered=t.customer_rendered,
            agent_text=t.agent_text, latency_ms=t.latency_ms, expectations=t.expectations,
            context_score=j.context_score, context_applicable=j.context_applicable, accuracy_score=j.accuracy_score,
            hallucination_score=j.hallucination_score, channel_fit_score=j.channel_fit_score,
            context_justification=j.context_justification, accuracy_justification=j.accuracy_justification,
            hallucination_justification=j.hallucination_justification, channel_justification=j.channel_justification,
            channel_flags=j.channel_flags, hallucinated=j.hallucinated, critical=j.critical,
            critical_reason=j.critical_reason, judge=j.judge,
        )
        turn.claims = [Claim(text=c.text, label=c.label, evidence=c.evidence) for c in j.claims]
        conv.turns.append(turn)


def run_summary(run: Run, thresholds: dict[str, float]) -> dict[str, Any]:
    """Compute metrics + verdicts for a run from its stored conversations."""
    stats = [
        ConversationStats(
            channel=c.channel,
            task_completed=c.task_completed,
            turns=[TurnStats(t.context_score, t.accuracy_score, t.hallucination_score, t.channel_fit_score,
                             t.hallucinated, t.critical, t.context_applicable) for t in c.turns],
        )
        for c in run.conversations
        if c.status == "completed"
    ]
    summary = summarize(stats, thresholds)
    judges = sorted({t.judge for c in run.conversations for t in c.turns})
    summary["judges"] = judges
    return summary


def plan_conversations(db: Session, run: Run) -> list[tuple[TestScript, str]]:
    """Expand a run's scripts × channels. An empty channel list means each script's own channel."""
    scripts = db.scalars(select(TestScript).where(TestScript.id.in_(run.script_ids)).order_by(TestScript.id)).all()
    pairs: list[tuple[TestScript, str]] = []
    for script in scripts:
        for channel in (run.channels or [script.channel]):
            pairs.append((script, channel))
    return pairs


def execute_run(run_id: int) -> None:
    """Execute a run synchronously (called in a background thread or directly when seeding)."""
    with session_scope() as db:
        run = db.get(Run, run_id)
        if run is None:
            return
        agent = db.get(Agent, run.agent_id) if run.agent_id else None
        if agent is None:
            run.status, run.error = "failed", "The agent for this run no longer exists."
            return
        kb = load_kb(db)
        thresholds = get_setting(db, "thresholds")
        pairs = plan_conversations(db, run)
        run.status = "running"
        run.started_at = run.started_at or datetime.now(timezone.utc)
        run.total_conversations = len(pairs)
        run.completed_conversations = 0
        run.judge_mode = effective_mode(run.judge_mode) if run.judge_mode != "auto" else f"auto→{effective_mode('auto')}"
        db.commit()
        requested_mode = run.judge_mode.split("→")[-1]
        breaker: dict[str, object] = {}
        try:
            adapter = build_adapter(agent.adapter_type, agent.config or {}, kb_text=kb_as_text(kb))
            for script, channel in pairs:
                conv = Conversation(
                    run_id=run.id, script_id=script.id, script_name=script.name,
                    journey_name=script.journey.name if script.journey else "", variant=script.variant,
                    channel=channel, status="running", email_subject=script.email_subject,
                    persona=script.persona, goal=script.goal,
                )
                db.add(conv)
                db.commit()
                outcome = execute_conversation(
                    adapter,
                    {"name": script.name, "turns": script.turns, "persona": script.persona, "goal": script.goal,
                     "email_subject": script.email_subject},
                    channel, kb, judge_mode=requested_mode,
                    seed_key=f"{agent.id}|{agent.config.get('preset', '')}|{script.id}|{channel}",
                    breaker=breaker,
                )
                _store_conversation(conv, outcome)
                run.completed_conversations += 1
                db.commit()
            db.refresh(run)
            run.summary = run_summary(run, thresholds)
            if breaker.get("tripped"):
                run.summary["warnings"] = [f"LLM judge unavailable, used offline judge: {breaker.get('reason')}"]
            failed = [c for c in run.conversations if c.status == "failed"]
            if failed and len(failed) == len(run.conversations):
                run.status = "failed"
                run.error = failed[0].error
            else:
                run.status = "completed"
                if failed:
                    run.error = f"{len(failed)} conversation(s) could not run: {failed[0].error}"
        except Exception as exc:  # noqa: BLE001 - a run must never crash the server
            run.status = "failed"
            run.error = f"{exc.__class__.__name__}: {exc}"
            traceback.print_exc()
        run.finished_at = datetime.now(timezone.utc)


class RunManager:
    """Executes runs on background threads, one thread per run."""

    def __init__(self) -> None:
        self._threads: dict[int, threading.Thread] = {}

    def start(self, run_id: int) -> None:
        thread = threading.Thread(target=execute_run, args=(run_id,), name=f"run-{run_id}", daemon=True)
        self._threads[run_id] = thread
        thread.start()

    def is_active(self, run_id: int) -> bool:
        thread = self._threads.get(run_id)
        return bool(thread and thread.is_alive())

    def any_active(self) -> bool:
        return any(t.is_alive() for t in self._threads.values())


run_manager = RunManager()

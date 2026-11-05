"""ORM → JSON-friendly dict conversion shared by the API routers."""
from __future__ import annotations

from typing import Any

from ..models import Agent, Claim, Conversation, Journey, KBFact, Run, TestScript, Turn


def iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def agent_out(a: Agent) -> dict[str, Any]:
    return {"id": a.id, "name": a.name, "adapter_type": a.adapter_type, "description": a.description,
            "config": a.config or {}, "created_at": iso(a.created_at)}


def kb_out(f: KBFact) -> dict[str, Any]:
    return {"id": f.id, "category": f.category, "title": f.title, "content": f.content, "tags": f.tags or [],
            "created_at": iso(f.created_at)}


def journey_out(j: Journey, script_count: int = 0) -> dict[str, Any]:
    return {"id": j.id, "name": j.name, "description": j.description, "intent": j.intent, "keywords": j.keywords or [],
            "frequency": j.frequency, "avg_turns": j.avg_turns, "example_utterances": j.example_utterances or [],
            "source": j.source, "labeler": j.labeler, "script_count": script_count, "created_at": iso(j.created_at)}


def script_out(s: TestScript) -> dict[str, Any]:
    return {"id": s.id, "name": s.name, "journey_id": s.journey_id, "journey_name": s.journey.name if s.journey else "",
            "channel": s.channel, "variant": s.variant, "persona": s.persona or {}, "goal": s.goal,
            "email_subject": s.email_subject, "turns": s.turns or [], "turn_count": len(s.turns or []),
            "created_at": iso(s.created_at), "updated_at": iso(s.updated_at)}


def run_out(r: Run, active: bool = False) -> dict[str, Any]:
    summary = r.summary or {}
    return {"id": r.id, "name": r.name, "agent_id": r.agent_id, "agent_name": r.agent_name, "status": r.status,
            "script_ids": r.script_ids or [], "channels": r.channels or [], "judge_mode": r.judge_mode,
            "total_conversations": r.total_conversations, "completed_conversations": r.completed_conversations,
            "progress": (r.completed_conversations / r.total_conversations) if r.total_conversations else 0.0,
            "verdict": summary.get("verdict"), "metrics": summary.get("metrics", {}), "summary": summary,
            "error": r.error, "active": active, "created_at": iso(r.created_at), "started_at": iso(r.started_at),
            "finished_at": iso(r.finished_at)}


def conversation_brief(c: Conversation) -> dict[str, Any]:
    return {"id": c.id, "run_id": c.run_id, "script_id": c.script_id, "script_name": c.script_name,
            "journey_name": c.journey_name, "variant": c.variant, "channel": c.channel, "status": c.status,
            "task_completed": c.task_completed, "task_score": c.task_score, "avg_context": c.avg_context,
            "avg_accuracy": c.avg_accuracy, "avg_hallucination": c.avg_hallucination,
            "avg_channel_fit": c.avg_channel_fit, "critical_failures": c.critical_failures,
            "hallucinated_turns": sum(1 for t in c.turns if t.hallucinated), "turn_count": len(c.turns),
            "error": c.error}


def claim_out(c: Claim) -> dict[str, Any]:
    return {"id": c.id, "text": c.text, "label": c.label, "evidence": c.evidence}


def turn_out(t: Turn) -> dict[str, Any]:
    return {"id": t.id, "index": t.index, "customer_text": t.customer_text, "customer_rendered": t.customer_rendered,
            "agent_text": t.agent_text, "latency_ms": t.latency_ms, "expectations": t.expectations or {},
            "context_score": t.context_score, "context_applicable": t.context_applicable,
            "accuracy_score": t.accuracy_score, "hallucination_score": t.hallucination_score,
            "channel_fit_score": t.channel_fit_score, "context_justification": t.context_justification,
            "accuracy_justification": t.accuracy_justification,
            "hallucination_justification": t.hallucination_justification,
            "channel_justification": t.channel_justification, "channel_flags": t.channel_flags or [],
            "hallucinated": t.hallucinated, "critical": t.critical, "critical_reason": t.critical_reason,
            "judge": t.judge, "claims": [claim_out(c) for c in t.claims]}


def conversation_out(c: Conversation) -> dict[str, Any]:
    run = c.run
    return {**conversation_brief(c), "email_subject": c.email_subject, "persona": c.persona or {}, "goal": c.goal,
            "task_justification": c.task_justification, "run_name": run.name if run else "",
            "agent_name": run.agent_name if run else "", "turns": [turn_out(t) for t in c.turns]}

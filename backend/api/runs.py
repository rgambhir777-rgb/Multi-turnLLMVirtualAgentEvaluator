"""Runs, conversations, comparison, dashboard and report/export endpoints."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import reports
from ..adapters import CHANNELS
from ..database import get_db
from ..judges import JUDGE_MODES
from ..models import Agent, Conversation, Run, TestScript
from ..runner import run_manager
from ..settings_store import get_setting
from .serializers import conversation_brief, conversation_out, run_out

router = APIRouter(tags=["runs"])
METRIC_KEYS = ("avg_accuracy", "avg_context", "avg_hallucination", "hallucination_rate", "avg_channel_fit",
               "task_completion_rate", "critical_failures")


class RunIn(BaseModel):
    name: str = ""
    agent_id: int
    script_ids: list[int] = Field(min_length=1)
    channels: list[str] = Field(default_factory=list, description="Empty = each script's own channel")
    judge_mode: str | None = None


def _get_run(db: Session, run_id: int) -> Run:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "Run not found.")
    return run


@router.get("/runs")
def list_runs(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    runs = db.scalars(select(Run).order_by(Run.created_at.desc(), Run.id.desc())).all()
    return [run_out(r, run_manager.is_active(r.id)) for r in runs]


@router.post("/runs", status_code=201)
def start_run(body: RunIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    agent = db.get(Agent, body.agent_id)
    if agent is None:
        raise HTTPException(404, "Agent not found.")
    bad = [c for c in body.channels if c not in CHANNELS]
    if bad:
        raise HTTPException(400, f"Unknown channel(s): {', '.join(bad)}.")
    found = set(db.scalars(select(TestScript.id).where(TestScript.id.in_(body.script_ids))))
    if not found:
        raise HTTPException(400, "None of the selected scripts exist.")
    mode = body.judge_mode or get_setting(db, "judge_mode")
    if mode not in JUDGE_MODES:
        raise HTTPException(400, f"judge_mode must be one of {', '.join(JUDGE_MODES)}.")
    run = Run(name=body.name or f"{agent.name} – {len(found)} scripts", agent_id=agent.id, agent_name=agent.name,
              status="queued", script_ids=sorted(found), channels=body.channels, judge_mode=mode)
    db.add(run)
    db.commit()
    run_manager.start(run.id)
    return run_out(run, True)


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    run = _get_run(db, run_id)
    return {**run_out(run, run_manager.is_active(run.id)),
            "conversations": [conversation_brief(c) for c in run.conversations]}


@router.delete("/runs/{run_id}", status_code=204)
def delete_run(run_id: int, db: Session = Depends(get_db)) -> None:
    run = _get_run(db, run_id)
    if run_manager.is_active(run.id):
        raise HTTPException(409, "This run is still in progress. Wait for it to finish before deleting it.")
    db.delete(run)
    db.commit()


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    conv = db.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(404, "Conversation not found.")
    return conversation_out(conv)


# ---------------------------------------------------------------------------- compare
def _journey_metrics(run: Run) -> dict[str, dict[str, float]]:
    groups: dict[str, list[Any]] = defaultdict(list)
    for conv in run.conversations:
        groups[conv.journey_name or conv.script_name].extend(conv.turns)
    return {
        name: {"avg_accuracy": round(sum(t.accuracy_score for t in turns) / len(turns), 3),
               "hallucination_rate": round(sum(1 for t in turns if t.hallucinated) / len(turns), 4)}
        for name, turns in groups.items() if turns
    }


@router.get("/compare")
def compare(a: int, b: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    run_a, run_b = _get_run(db, a), _get_run(db, b)
    ma, mb = (run_a.summary or {}).get("metrics", {}), (run_b.summary or {}).get("metrics", {})
    deltas = {k: round(float(mb.get(k, 0)) - float(ma.get(k, 0)), 4) for k in METRIC_KEYS}
    channels = sorted(set((run_a.summary or {}).get("by_channel", {})) | set((run_b.summary or {}).get("by_channel", {})))
    by_channel = []
    for ch in channels:
        ca = (run_a.summary or {}).get("by_channel", {}).get(ch, {})
        cb = (run_b.summary or {}).get("by_channel", {}).get(ch, {})
        by_channel.append({"channel": ch, "a": ca.get("metrics", {}), "b": cb.get("metrics", {}),
                           "verdict_a": ca.get("verdict"), "verdict_b": cb.get("verdict")})
    ja, jb = _journey_metrics(run_a), _journey_metrics(run_b)
    journeys = [{"journey": name, "a": ja.get(name), "b": jb.get(name)} for name in sorted(set(ja) | set(jb))]
    conv_a = {(c.script_id, c.channel): c for c in run_a.conversations}
    pairs = []
    for c in run_b.conversations:
        other = conv_a.get((c.script_id, c.channel))
        if other is not None:
            pairs.append({"script_name": c.script_name, "channel": c.channel, "a": conversation_brief(other),
                          "b": conversation_brief(c)})
    return {"a": run_out(run_a), "b": run_out(run_b), "deltas": deltas, "by_channel": by_channel,
            "journeys": journeys, "conversations": pairs}


# ---------------------------------------------------------------------------- dashboard
@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)) -> dict[str, Any]:
    completed = db.scalars(select(Run).where(Run.status == "completed").order_by(Run.finished_at, Run.id)).all()
    latest_by_agent: dict[int, Run] = {}
    for run in completed:
        if run.agent_id is not None:
            latest_by_agent[run.agent_id] = run
    agents = {a.id: a for a in db.scalars(select(Agent))}
    cards = []
    for agent_id, run in sorted(latest_by_agent.items()):
        summary = run.summary or {}
        cards.append({"agent_id": agent_id, "agent_name": agents[agent_id].name if agent_id in agents else run.agent_name,
                      "run_id": run.id, "run_name": run.name, "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                      "verdict": summary.get("verdict"), "metrics": summary.get("metrics", {}),
                      "reasons": summary.get("reasons", []),
                      "channels": {ch: d.get("verdict") for ch, d in summary.get("by_channel", {}).items()}})
    trends = [{"run_id": r.id, "label": f"#{r.id} {r.agent_name}", "agent": r.agent_name,
               "date": r.finished_at.isoformat() if r.finished_at else None,
               **{k: (r.summary or {}).get("metrics", {}).get(k, 0) for k in METRIC_KEYS}} for r in completed]
    channel_scores = []
    for ch in CHANNELS:
        row: dict[str, Any] = {"channel": ch}
        for run in latest_by_agent.values():
            metrics = (run.summary or {}).get("by_channel", {}).get(ch, {}).get("metrics")
            if metrics:
                row[run.agent_name] = metrics.get("avg_accuracy", 0)
                row[f"{run.agent_name}__hallucination_rate"] = metrics.get("hallucination_rate", 0)
                row[f"{run.agent_name}__channel_fit"] = metrics.get("avg_channel_fit", 0)
        channel_scores.append(row)
    journey_turns: dict[str, list[Any]] = defaultdict(list)
    for run in latest_by_agent.values():
        for conv in run.conversations:
            journey_turns[conv.journey_name or conv.script_name].extend(conv.turns)
    worst = sorted(
        ({"journey": name, "avg_accuracy": round(sum(t.accuracy_score for t in ts) / len(ts), 2),
          "hallucination_rate": round(sum(1 for t in ts if t.hallucinated) / len(ts), 3),
          "critical": sum(1 for t in ts if t.critical), "turns": len(ts)}
         for name, ts in journey_turns.items() if ts),
        key=lambda r: (r["avg_accuracy"], -r["hallucination_rate"]),
    )[:6]
    latest = completed[-1] if completed else None
    total_turns = sum((r.summary or {}).get("metrics", {}).get("turns", 0) for r in completed)
    total_convs = sum((r.summary or {}).get("metrics", {}).get("conversations", 0) for r in completed)
    return {
        "cards": cards,
        "kpis": {"runs": len(completed), "conversations": total_convs, "turns": total_turns,
                 "latest": run_out(latest) if latest else None},
        "trends": trends,
        "channel_scores": channel_scores,
        "agents": [r.agent_name for r in latest_by_agent.values()],
        "worst_journeys": worst,
        "thresholds": get_setting(db, "thresholds"),
    }


# ---------------------------------------------------------------------------- reports
def _completed(db: Session, run_id: int) -> Run:
    run = _get_run(db, run_id)
    if run.status != "completed":
        raise HTTPException(409, "Reports are available once the run has completed.")
    return run


def _filename(run: Run, ext: str) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in run.agent_name)[:40]
    return f"agentproof_run{run.id}_{safe}.{ext}"


@router.get("/runs/{run_id}/report.html", response_class=HTMLResponse)
def report_html(run_id: int, download: bool = False, db: Session = Depends(get_db)) -> HTMLResponse:
    run = _completed(db, run_id)
    headers = {"Content-Disposition": f'attachment; filename="{_filename(run, "html")}"'} if download else {}
    return HTMLResponse(reports.render_html(run), headers=headers)


@router.get("/runs/{run_id}/report.pdf")
def report_pdf(run_id: int, db: Session = Depends(get_db)) -> Response:
    run = _completed(db, run_id)
    try:
        pdf = reports.render_pdf(run)
    except Exception as exc:  # noqa: BLE001 - PDF is optional; HTML always works
        raise HTTPException(503, f"PDF generation is unavailable on this machine ({exc.__class__.__name__}). "
                                 "Use the HTML report and your browser's Print → Save as PDF.") from exc
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{_filename(run, "pdf")}"'})


@router.get("/runs/{run_id}/export.csv", response_class=PlainTextResponse)
def export_csv(run_id: int, db: Session = Depends(get_db)) -> PlainTextResponse:
    run = _completed(db, run_id)
    return PlainTextResponse(reports.export_csv(run), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{_filename(run, "csv")}"'})


@router.get("/runs/{run_id}/export.json")
def export_json(run_id: int, db: Session = Depends(get_db)) -> Response:
    run = _completed(db, run_id)
    return Response(reports.export_json(run), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{_filename(run, "json")}"'})

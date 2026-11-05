"""Stakeholder reports for a run: HTML (Jinja2), PDF (ReportLab) and CSV/JSON turn exports."""
from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import TEMPLATES_DIR
from .models import Conversation, Run

VERDICT_COPY = {
    "GO": "is ready for real customers",
    "CONDITIONAL": "can go live only after the listed conditions are addressed",
    "NO-GO": "is not ready for real customers",
}
VERDICT_COLORS = {"GO": "#059669", "CONDITIONAL": "#d97706", "NO-GO": "#dc2626"}


def _fmt_date(value: datetime | None) -> str:
    return value.strftime("%d %b %Y %H:%M UTC") if value else "—"


def _journey_table(run: Run) -> list[dict[str, Any]]:
    groups: dict[str, list[Conversation]] = defaultdict(list)
    for conv in run.conversations:
        groups[conv.journey_name or conv.script_name].append(conv)
    rows = []
    for name, convs in groups.items():
        turns = [t for c in convs for t in c.turns]
        if not turns:
            continue
        rows.append({
            "journey": name,
            "conversations": len(convs),
            "accuracy": round(sum(t.accuracy_score for t in turns) / len(turns), 2),
            "hallucination_rate": round(sum(1 for t in turns if t.hallucinated) / len(turns), 3),
            "task_completion": round(sum(1 for c in convs if c.task_completed) / len(convs), 3),
            "critical": sum(1 for t in turns if t.critical),
        })
    return sorted(rows, key=lambda r: (r["accuracy"], -r["hallucination_rate"]))


def _example_failures(run: Run, limit: int = 3) -> list[dict[str, Any]]:
    def badness(c: Conversation) -> float:
        return c.critical_failures * 3 + (5 - c.avg_accuracy) + (5 - c.avg_hallucination) + (5 - c.avg_context)

    worst = sorted([c for c in run.conversations if c.turns], key=badness, reverse=True)
    examples = []
    for conv in worst[:limit]:
        if badness(conv) <= 0.5:
            break
        examples.append({
            "title": conv.script_name,
            "channel": conv.channel,
            "journey": conv.journey_name,
            "task": conv.task_justification,
            "turns": [
                {
                    "index": t.index + 1,
                    "customer": t.customer_rendered,
                    "agent": t.agent_text,
                    "scores": f"Context {t.context_score:.1f} · Accuracy {t.accuracy_score:.1f} · Hallucination {t.hallucination_score:.1f} · Channel {t.channel_fit_score:.1f}",
                    "problem": "; ".join(filter(None, [
                        t.critical_reason,
                        t.context_justification if t.context_score < 4 else "",
                        "; ".join(f"{c.label}: {c.text}" for c in t.claims if c.label != "Supported"),
                        ", ".join(t.channel_flags) if t.channel_fit_score < 4 else "",
                    ])),
                    "bad": t.critical or t.hallucinated or t.context_score < 4 or t.accuracy_score < 4,
                }
                for t in conv.turns
            ],
        })
    return examples


def report_data(run: Run) -> dict[str, Any]:
    """Everything the HTML/PDF report renders."""
    summary = run.summary or {}
    metrics = summary.get("metrics", {})
    verdict = summary.get("verdict", "NO-GO")
    journeys = _journey_table(run)
    risks: list[str] = [r["text"] for r in summary.get("reasons", [])]
    for channel, data in summary.get("by_channel", {}).items():
        if data.get("verdict") != "GO":
            risks.append(f"{channel.upper()} channel is {data.get('verdict')}: " + "; ".join(r["text"] for r in data.get("reasons", [])[:2]))
    for row in journeys[:2]:
        if row["accuracy"] < 4.5 or row["hallucination_rate"] > 0.02:
            risks.append(f"Weakest journey: {row['journey']} (accuracy {row['accuracy']:.2f}, hallucination rate {row['hallucination_rate']:.0%}).")
    exec_summary = (
        f"{run.agent_name} {VERDICT_COPY.get(verdict, '')}. Across {metrics.get('conversations', 0)} test conversations "
        f"({metrics.get('turns', 0)} scored agent turns) on {', '.join(sorted(summary.get('by_channel', {}))) or 'no channels'}, "
        f"the agent averaged {metrics.get('avg_accuracy', 0):.2f}/5 for accuracy and {metrics.get('avg_context', 0):.2f}/5 for "
        f"context awareness, hallucinated in {metrics.get('hallucination_rate', 0):.1%} of turns, completed "
        f"{metrics.get('task_completion_rate', 0):.0%} of customer goals and had {metrics.get('critical_failures', 0)} critical failure(s)."
    )
    return {
        "run": run,
        "generated": _fmt_date(datetime.now(timezone.utc)),
        "started": _fmt_date(run.started_at),
        "finished": _fmt_date(run.finished_at),
        "verdict": verdict,
        "verdict_color": VERDICT_COLORS.get(verdict, "#6b7280"),
        "exec_summary": exec_summary,
        "metrics": metrics,
        "reasons": summary.get("reasons", []),
        "passed": summary.get("passed", []),
        "by_channel": summary.get("by_channel", {}),
        "journeys": journeys,
        "risks": risks or ["No material risks found in this run."],
        "examples": _example_failures(run),
        "judges": ", ".join(summary.get("judges", [])) or "heuristic",
        "colors": VERDICT_COLORS,
    }


def render_html(run: Run) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=select_autoescape(["html"]))
    return env.get_template("report.html").render(**report_data(run))


def render_pdf(run: Run) -> bytes:
    """PDF via ReportLab. Raises ImportError/RuntimeError if PDF generation is unavailable."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape

    data = report_data(run)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=20, textColor=colors.HexColor("#1e1b4b"), alignment=0)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=colors.HexColor("#4338ca"), spaceBefore=10)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=9.5, leading=13)
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=10.5, textColor=colors.HexColor("#374151"))
    verdict_style = ParagraphStyle("verdict", parent=body, fontSize=16, leading=20, textColor=colors.white)

    def P(text: str, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(escape(text).replace("\n", "<br/>"), style)

    grid = TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ])
    m = data["metrics"]
    story: list[Any] = [
        P("AgentProof · Virtual Agent Readiness Report", small),
        Paragraph(escape(run.name), h1),
        P(f"Agent: {run.agent_name}    Run #{run.id}    Finished: {data['finished']}    Judge: {data['judges']}", small),
        Spacer(1, 6),
    ]
    verdict_table = Table([[Paragraph(f"<b>Verdict: {data['verdict']}</b>", verdict_style)]], colWidths=[180 * mm])
    verdict_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(data["verdict_color"])),
                                       ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 8),
                                       ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    story += [verdict_table, Spacer(1, 6), Paragraph("Executive summary", h2), P(data["exec_summary"])]
    kpis = [["Accuracy", "Context", "Hallucination rate", "Channel fit", "Task completion", "Critical"],
            [f"{m.get('avg_accuracy', 0):.2f}", f"{m.get('avg_context', 0):.2f}", f"{m.get('hallucination_rate', 0):.1%}",
             f"{m.get('avg_channel_fit', 0):.2f}", f"{m.get('task_completion_rate', 0):.0%}", str(m.get("critical_failures", 0))]]
    t = Table(kpis, colWidths=[30 * mm] * 6)
    t.setStyle(grid)
    story += [Spacer(1, 6), t, Paragraph("Key risks", h2)]
    story += [P("• " + r) for r in data["risks"]]
    if data["passed"]:
        story += [Paragraph("Criteria met", h2)] + [P("✓ " + p) for p in data["passed"]]
    rows = [["Channel", "Verdict", "Accuracy", "Context", "Halluc. rate", "Channel fit", "Tasks", "Critical"]]
    for channel, ch in data["by_channel"].items():
        cm = ch["metrics"]
        rows.append([channel, ch["verdict"], f"{cm['avg_accuracy']:.2f}", f"{cm['avg_context']:.2f}",
                     f"{cm['hallucination_rate']:.1%}", f"{cm['avg_channel_fit']:.2f}", f"{cm['task_completion_rate']:.0%}",
                     str(cm["critical_failures"])])
    t = Table(rows, colWidths=[22 * mm, 26 * mm] + [22 * mm] * 6)
    t.setStyle(grid)
    story += [Paragraph("Readiness by channel", h2), t]
    rows = [["Journey", "Convs", "Accuracy", "Halluc. rate", "Tasks", "Critical"]]
    rows += [[P(r["journey"], small), r["conversations"], f"{r['accuracy']:.2f}", f"{r['hallucination_rate']:.0%}",
              f"{r['task_completion']:.0%}", r["critical"]] for r in data["journeys"]]
    t = Table(rows, colWidths=[70 * mm, 18 * mm, 22 * mm, 24 * mm, 20 * mm, 20 * mm])
    t.setStyle(grid)
    story += [Paragraph("Results by journey (weakest first)", h2), t]
    if data["examples"]:
        story.append(Paragraph("Example failures", h2))
        for ex in data["examples"]:
            block: list[Any] = [P(f"{ex['title']} — {ex['channel']} · {ex['task']}", body)]
            rows = [["#", "Customer", "Agent", "Assessment"]]
            for turn in ex["turns"]:
                rows.append([str(turn["index"]), P(turn["customer"][:400], small), P(turn["agent"][:600], small),
                             P((turn["scores"] + ("\n" + turn["problem"] if turn["problem"] else ""))[:500], small)])
            t = Table(rows, colWidths=[8 * mm, 48 * mm, 70 * mm, 54 * mm], repeatRows=1)
            style = TableStyle(grid.getCommands())
            for i, turn in enumerate(ex["turns"], start=1):
                if turn["bad"]:
                    style.add("BACKGROUND", (3, i), (3, i), colors.HexColor("#fef2f2"))
            t.setStyle(style)
            block += [Spacer(1, 3), t, Spacer(1, 8)]
            story.append(KeepTogether(block[:2]))
            story += block[2:]
    buffer = io.BytesIO()
    SimpleDocTemplate(buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm,
                      bottomMargin=14 * mm, title=run.name, author="AgentProof").build(story)
    return buffer.getvalue()


TURN_COLUMNS = [
    "run_id", "agent", "conversation_id", "script", "journey", "variant", "channel", "turn", "customer_text",
    "customer_rendered", "agent_text", "context_score", "accuracy_score", "hallucination_score", "channel_fit_score",
    "hallucinated", "critical", "critical_reason", "judge", "context_justification", "accuracy_justification",
    "hallucination_justification", "channel_justification", "claims",
]


def turn_rows(run: Run) -> list[dict[str, Any]]:
    rows = []
    for conv in run.conversations:
        for t in conv.turns:
            rows.append({
                "run_id": run.id, "agent": run.agent_name, "conversation_id": conv.id, "script": conv.script_name,
                "journey": conv.journey_name, "variant": conv.variant, "channel": conv.channel, "turn": t.index + 1,
                "customer_text": t.customer_text, "customer_rendered": t.customer_rendered, "agent_text": t.agent_text,
                "context_score": t.context_score, "accuracy_score": t.accuracy_score,
                "hallucination_score": t.hallucination_score, "channel_fit_score": t.channel_fit_score,
                "hallucinated": t.hallucinated, "critical": t.critical, "critical_reason": t.critical_reason,
                "judge": t.judge, "context_justification": t.context_justification,
                "accuracy_justification": t.accuracy_justification,
                "hallucination_justification": t.hallucination_justification,
                "channel_justification": t.channel_justification,
                "claims": [{"text": c.text, "label": c.label, "evidence": c.evidence} for c in t.claims],
            })
    return rows


def export_csv(run: Run) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=TURN_COLUMNS)
    writer.writeheader()
    for row in turn_rows(run):
        row = dict(row)
        row["claims"] = " | ".join(f"[{c['label']}] {c['text']}" for c in row["claims"])
        writer.writerow(row)
    return buffer.getvalue()


def export_json(run: Run) -> str:
    return json.dumps({"run": {"id": run.id, "name": run.name, "agent": run.agent_name, "summary": run.summary},
                       "turns": turn_rows(run)}, indent=2, default=str)

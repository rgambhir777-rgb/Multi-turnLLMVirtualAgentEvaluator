"""Journey discovery and journey/script-generation endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..adapters import CHANNELS
from ..builder import VARIANTS, build_script
from ..database import get_db
from ..discovery import discover_journeys, parse_transcripts
from ..models import Journey, TestScript, Transcript
from .serializers import journey_out, script_out

router = APIRouter(tags=["journeys"])


class JourneyIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    intent: str = "general"
    keywords: list[str] = Field(default_factory=list)
    example_utterances: list[str] = Field(default_factory=list)


class GenerateIn(BaseModel):
    variants: list[str] = Field(default_factory=lambda: ["standard"])
    channel: str = "chat"


def _counts(db: Session) -> dict[int, int]:
    rows = db.execute(select(TestScript.journey_id, func.count()).group_by(TestScript.journey_id)).all()
    return {jid: n for jid, n in rows if jid is not None}


@router.get("/journeys")
def list_journeys(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    counts = _counts(db)
    return [journey_out(j, counts.get(j.id, 0)) for j in db.scalars(select(Journey).order_by(Journey.frequency.desc(), Journey.id))]


@router.post("/journeys", status_code=201)
def create_journey(body: JourneyIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    journey = Journey(**body.model_dump(), source="manual")
    db.add(journey)
    db.commit()
    return journey_out(journey)


@router.put("/journeys/{journey_id}")
def update_journey(journey_id: int, body: JourneyIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    journey = db.get(Journey, journey_id)
    if journey is None:
        raise HTTPException(404, "Journey not found.")
    for key, value in body.model_dump().items():
        setattr(journey, key, value)
    db.commit()
    return journey_out(journey, _counts(db).get(journey.id, 0))


@router.delete("/journeys/{journey_id}", status_code=204)
def delete_journey(journey_id: int, db: Session = Depends(get_db)) -> None:
    journey = db.get(Journey, journey_id)
    if journey is None:
        raise HTTPException(404, "Journey not found.")
    db.delete(journey)
    db.commit()


@router.get("/transcripts/stats")
def transcript_stats(db: Session = Depends(get_db)) -> dict[str, Any]:
    total = db.scalar(select(func.count()).select_from(Transcript)) or 0
    by_channel = dict(db.execute(select(Transcript.channel, func.count()).group_by(Transcript.channel)).all())
    sample = db.scalars(select(Transcript).order_by(Transcript.id).limit(3)).all()
    return {"total": total, "by_channel": by_channel,
            "sample": [{"id": t.external_id, "channel": t.channel, "turns": t.turns[:4]} for t in sample]}


@router.post("/journeys/discover")
async def discover(
    file: UploadFile | None = File(None),
    k: int | None = Form(None),
    replace_transcripts: bool = Form(True),
    use_llm: bool = Form(True),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Cluster transcripts into journeys. Upload a CSV/JSON file, or omit it to re-cluster stored transcripts."""
    if file is not None and file.filename:
        try:
            parsed = parse_transcripts(await file.read(), file.filename)
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(400, f"Could not read transcripts: {exc}") from exc
        if not parsed:
            raise HTTPException(400, "The file contained no transcripts.")
        if replace_transcripts:
            db.execute(delete(Transcript))
        rows = [Transcript(external_id=str(t["external_id"]), channel=str(t["channel"]), turns=t["turns"]) for t in parsed]
        db.add_all(rows)
        db.flush()
        if not replace_transcripts:
            rows = list(db.scalars(select(Transcript).order_by(Transcript.id)))
    else:
        rows = list(db.scalars(select(Transcript).order_by(Transcript.id)))
    if not rows:
        raise HTTPException(400, "No transcripts available. Upload a CSV or JSON file first.")
    data = [{"external_id": r.external_id, "channel": r.channel, "turns": r.turns} for r in rows]
    try:
        found = discover_journeys(data, k=k, use_llm=use_llm)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    existing = {j.intent: j for j in db.scalars(select(Journey).where(Journey.source == "discovered"))}
    result = []
    for d in found:
        journey = existing.get(d.intent) if d.intent != "other" else None
        if journey is None:
            journey = Journey(source="discovered")
            db.add(journey)
        journey.name, journey.description, journey.intent = d.name, d.description, d.intent
        journey.keywords, journey.frequency, journey.avg_turns = d.keywords, d.frequency, d.avg_turns
        journey.example_utterances, journey.labeler = d.example_utterances, d.labeler
        db.flush()
        for member in d.members:
            rows[member].journey_id = journey.id
        result.append(journey)
    db.commit()
    counts = _counts(db)
    return {"transcripts": len(rows), "journeys": [journey_out(j, counts.get(j.id, 0)) for j in result],
            "labeler": found[0].labeler if found else "lexicon"}


@router.get("/scripts/meta")
def script_meta() -> dict[str, Any]:
    return {"variants": VARIANTS, "channels": list(CHANNELS)}


@router.post("/journeys/{journey_id}/generate-scripts", status_code=201)
def generate_scripts(journey_id: int, body: GenerateIn, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    journey = db.get(Journey, journey_id)
    if journey is None:
        raise HTTPException(404, "Journey not found.")
    if body.channel not in CHANNELS:
        raise HTTPException(400, f"Channel must be one of {', '.join(CHANNELS)}.")
    created = []
    existing = db.scalar(select(func.count()).select_from(TestScript)) or 0
    for i, variant in enumerate(body.variants):
        if variant not in VARIANTS:
            raise HTTPException(400, f"Unknown variant '{variant}'.")
        spec = build_script({"intent": journey.intent, "name": journey.name, "description": journey.description,
                             "example_utterances": journey.example_utterances}, variant, f"gen-{journey.id}-{existing + i}")
        script = TestScript(name=spec["name"], journey_id=journey.id, channel=body.channel, variant=variant,
                            persona=spec["persona"], goal=spec["goal"], email_subject=spec["subject"], turns=spec["turns"])
        db.add(script)
        created.append(script)
    db.commit()
    return [script_out(s) for s in created]

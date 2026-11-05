"""Knowledge base endpoints (CRUD, Markdown/CSV import, Markdown export)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..kb import parse_csv, parse_markdown
from ..models import KBFact
from .serializers import kb_out

router = APIRouter(prefix="/kb", tags=["knowledge base"])


class FactIn(BaseModel):
    category: str = Field(default="General", max_length=80)
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


@router.get("")
def list_facts(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [kb_out(f) for f in db.scalars(select(KBFact).order_by(KBFact.category, KBFact.id))]


@router.post("", status_code=201)
def create_fact(body: FactIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    fact = KBFact(**body.model_dump())
    db.add(fact)
    db.commit()
    return kb_out(fact)


@router.put("/{fact_id}")
def update_fact(fact_id: int, body: FactIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    fact = db.get(KBFact, fact_id)
    if fact is None:
        raise HTTPException(404, "Fact not found.")
    for key, value in body.model_dump().items():
        setattr(fact, key, value)
    db.commit()
    return kb_out(fact)


@router.delete("/{fact_id}", status_code=204)
def delete_fact(fact_id: int, db: Session = Depends(get_db)) -> None:
    fact = db.get(KBFact, fact_id)
    if fact is None:
        raise HTTPException(404, "Fact not found.")
    db.delete(fact)
    db.commit()


@router.post("/import")
async def import_facts(
    file: UploadFile = File(...), mode: str = Form("append"), db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Import facts from Markdown (``## Category`` / ``### Title``) or CSV (``category,title,content``)."""
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    name = (file.filename or "").lower()
    facts = parse_csv(raw) if name.endswith(".csv") else parse_markdown(raw)
    if not facts:
        raise HTTPException(400, "No facts found. Markdown needs '## Category' and '### Title' headings; CSV needs category,title,content columns.")
    if mode == "replace":
        db.execute(delete(KBFact))
    for f in facts:
        tags = [t.strip() for t in str(f.get("tags", "")).split(",") if t.strip()]
        db.add(KBFact(category=f["category"], title=f["title"], content=f["content"], tags=tags))
    db.commit()
    return {"imported": len(facts), "mode": mode}


@router.get("/export", response_class=PlainTextResponse)
def export_markdown(db: Session = Depends(get_db)) -> str:
    facts = db.scalars(select(KBFact).order_by(KBFact.category, KBFact.id)).all()
    lines = ["# Knowledge Base", ""]
    category = None
    for f in facts:
        if f.category != category:
            category = f.category
            lines += [f"## {category}", ""]
        lines += [f"### {f.title}", f.content, ""]
    return "\n".join(lines)

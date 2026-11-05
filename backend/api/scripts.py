"""Test script CRUD."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters import CHANNELS
from ..builder import VARIANTS
from ..database import get_db
from ..models import TestScript
from .serializers import script_out

router = APIRouter(prefix="/scripts", tags=["test scripts"])


class TurnIn(BaseModel):
    customer: str = Field(min_length=1)
    must_include: list[str] = Field(default_factory=list)
    must_not_include: list[str] = Field(default_factory=list)
    must_remember: list[str] = Field(default_factory=list)
    notes: str = ""

    @field_validator("must_include", "must_not_include", "must_remember")
    @classmethod
    def _strip(cls, values: list[str]) -> list[str]:
        return [v.strip() for v in values if v and v.strip()]


class ScriptIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    journey_id: int | None = None
    channel: str = "chat"
    variant: str = "standard"
    persona: dict[str, Any] = Field(default_factory=dict)
    goal: str = ""
    email_subject: str = ""
    turns: list[TurnIn] = Field(min_length=1)

    @field_validator("channel")
    @classmethod
    def _channel(cls, value: str) -> str:
        if value not in CHANNELS:
            raise ValueError(f"channel must be one of {', '.join(CHANNELS)}")
        return value

    @field_validator("variant")
    @classmethod
    def _variant(cls, value: str) -> str:
        if value not in VARIANTS:
            raise ValueError(f"variant must be one of {', '.join(VARIANTS)}")
        return value


@router.get("")
def list_scripts(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [script_out(s) for s in db.scalars(select(TestScript).order_by(TestScript.id))]


def _get(db: Session, script_id: int) -> TestScript:
    script = db.get(TestScript, script_id)
    if script is None:
        raise HTTPException(404, "Script not found.")
    return script


@router.get("/{script_id}")
def get_script(script_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return script_out(_get(db, script_id))


@router.post("", status_code=201)
def create_script(body: ScriptIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    data = body.model_dump()
    script = TestScript(**data)
    db.add(script)
    db.commit()
    return script_out(script)


@router.put("/{script_id}")
def update_script(script_id: int, body: ScriptIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    script = _get(db, script_id)
    for key, value in body.model_dump().items():
        setattr(script, key, value)
    db.commit()
    db.refresh(script)
    return script_out(script)


@router.post("/{script_id}/duplicate", status_code=201)
def duplicate_script(script_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    src = _get(db, script_id)
    copy = TestScript(name=f"{src.name} (copy)", journey_id=src.journey_id, channel=src.channel, variant=src.variant,
                      persona=dict(src.persona or {}), goal=src.goal, email_subject=src.email_subject,
                      turns=[dict(t) for t in src.turns or []])
    db.add(copy)
    db.commit()
    return script_out(copy)


@router.delete("/{script_id}", status_code=204)
def delete_script(script_id: int, db: Session = Depends(get_db)) -> None:
    db.delete(_get(db, script_id))
    db.commit()

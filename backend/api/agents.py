"""Agent connection endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters import ADAPTER_TYPES, PRESETS, AdapterError, build_adapter
from ..adapters.mock import FLAW_SETTINGS
from ..adapters.nice_cxone import REQUIRED_SETTINGS
from ..database import get_db
from ..models import Agent
from ..runner import kb_as_text, load_kb
from .serializers import agent_out

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    adapter_type: str
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)


@router.get("")
def list_agents(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [agent_out(a) for a in db.scalars(select(Agent).order_by(Agent.id))]


@router.get("/meta")
def agent_meta() -> dict[str, Any]:
    """Adapter types, mock presets and per-adapter config hints for the editor."""
    return {
        "adapter_types": ADAPTER_TYPES,
        "mock_presets": PRESETS,
        "mock_settings": FLAW_SETTINGS,
        "cxone_settings": list(REQUIRED_SETTINGS.values()),
        "config_templates": {
            "mock": {"preset": "v3"},
            "http": {"url": "https://bot.example.com/api/message", "method": "POST",
                     "headers": {"Authorization": "Bearer ${BOT_API_TOKEN}"},
                     "request_template": '{"session_id": "{{session_id}}", "message": "{{message}}", "channel": "{{channel}}"}',
                     "response_path": "reply", "timeout_s": 30},
            "llm": {"provider": "auto", "include_kb": True, "system_prompt": ""},
            "cxone": {"business_unit": "", "channel_id": "", "point_of_contact": "", "reply_timeout_s": 30},
        },
    }


@router.post("", status_code=201)
def create_agent(body: AgentIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    if body.adapter_type not in ADAPTER_TYPES:
        raise HTTPException(400, f"Unknown adapter type '{body.adapter_type}'.")
    agent = Agent(**body.model_dump())
    db.add(agent)
    db.commit()
    return agent_out(agent)


def _get(db: Session, agent_id: int) -> Agent:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(404, "Agent not found.")
    return agent


@router.get("/{agent_id}")
def get_agent(agent_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return agent_out(_get(db, agent_id))


@router.put("/{agent_id}")
def update_agent(agent_id: int, body: AgentIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    if body.adapter_type not in ADAPTER_TYPES:
        raise HTTPException(400, f"Unknown adapter type '{body.adapter_type}'.")
    agent = _get(db, agent_id)
    for key, value in body.model_dump().items():
        setattr(agent, key, value)
    db.commit()
    return agent_out(agent)


@router.delete("/{agent_id}", status_code=204)
def delete_agent(agent_id: int, db: Session = Depends(get_db)) -> None:
    db.delete(_get(db, agent_id))
    db.commit()


@router.post("/{agent_id}/test")
def test_agent(agent_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Send one message to the agent and report whether it answered."""
    agent = _get(db, agent_id)
    try:
        adapter = build_adapter(agent.adapter_type, agent.config or {}, kb_text=kb_as_text(load_kb(db)))
    except AdapterError as exc:
        return {"ok": False, "message": str(exc), "sample_reply": ""}
    check = adapter.test_connection()
    return {"ok": check.ok, "message": check.message, "sample_reply": check.sample_reply}

"""Status, settings, demo reset and the built-in demo bot endpoint."""
from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import __version__, llm
from ..adapters import MockAgentAdapter
from ..config import EDITABLE_ENV_KEYS, SECRET_KEYS, env, mask, update_env_file
from ..database import get_db
from ..judges import JUDGE_MODES, effective_mode
from ..readiness import DEFAULT_THRESHOLDS, THRESHOLD_LABELS
from ..runner import run_manager
from ..seed import reset_demo
from ..settings_store import get_setting, set_setting

router = APIRouter(tags=["system"])


@router.get("/status")
def status(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Drives the UI banner: which judge is active and whether the LLM is reachable."""
    mode = get_setting(db, "judge_mode")
    provider = llm.provider()
    effective = effective_mode(mode)
    offline_reason = ""
    if effective == "heuristic":
        offline_reason = ("Offline heuristic judge selected in Settings." if mode == "heuristic"
                          else "No LLM API key configured – using the offline heuristic judge.")
    elif llm.health.last_error:
        offline_reason = f"LLM judge problem: {llm.health.last_error} Runs fall back to the offline judge."
    return {
        "version": __version__,
        "judge_mode": mode,
        "effective_judge": effective,
        "llm_provider": provider,
        "llm_model": llm.model_name(provider) if provider else "",
        "llm_error": llm.health.last_error,
        "offline": effective == "heuristic" or bool(llm.health.last_error),
        "offline_reason": offline_reason,
    }


class SettingsIn(BaseModel):
    env: dict[str, str] = Field(default_factory=dict)
    judge_mode: str | None = None
    thresholds: dict[str, float] | None = None


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)) -> dict[str, Any]:
    values = {}
    for key in EDITABLE_ENV_KEYS:
        raw = env(key)
        values[key] = {"value": mask(raw) if key in SECRET_KEYS else raw, "set": bool(raw), "secret": key in SECRET_KEYS}
    return {"env": values, "judge_mode": get_setting(db, "judge_mode"), "judge_modes": list(JUDGE_MODES),
            "thresholds": get_setting(db, "thresholds"), "threshold_labels": THRESHOLD_LABELS,
            "default_thresholds": DEFAULT_THRESHOLDS}


@router.put("/settings")
def save_settings(body: SettingsIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    unknown = [k for k in body.env if k not in EDITABLE_ENV_KEYS]
    if unknown:
        raise HTTPException(400, f"Unknown setting(s): {', '.join(unknown)}.")
    # Masked values coming back unchanged from the UI must not overwrite the real secret.
    updates = {k: v.strip() for k, v in body.env.items() if not (k in SECRET_KEYS and "•" in v)}
    if updates:
        update_env_file(updates)
        llm.health.record_ok()
    if body.judge_mode is not None:
        if body.judge_mode not in JUDGE_MODES:
            raise HTTPException(400, f"judge_mode must be one of {', '.join(JUDGE_MODES)}.")
        set_setting(db, "judge_mode", body.judge_mode)
    if body.thresholds is not None:
        unknown = [k for k in body.thresholds if k not in DEFAULT_THRESHOLDS]
        if unknown:
            raise HTTPException(400, f"Unknown threshold(s): {', '.join(unknown)}.")
        set_setting(db, "thresholds", {**get_setting(db, "thresholds"), **body.thresholds})
    return get_settings(db)


@router.post("/settings/test-llm")
def test_llm() -> dict[str, Any]:
    """Send a tiny prompt to the configured LLM so users can verify their key."""
    if not llm.available():
        return {"ok": False, "message": "No LLM API key configured. The offline heuristic judge will be used."}
    try:
        reply = llm.complete("Reply with the single word OK.", [{"role": "user", "content": "Connectivity check."}],
                             max_tokens=200, timeout=30)
    except llm.LLMError as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "message": f"Connected to {llm.provider()} ({llm.model_name()}). Reply: {reply.strip()[:60]}"}


_reset_lock = threading.Lock()


@router.post("/settings/reset-demo")
def reset_demo_data() -> dict[str, Any]:
    """Wipe the database and re-seed the Northwind demo (takes a few seconds)."""
    if run_manager.any_active():
        raise HTTPException(409, "A run is in progress. Wait for it to finish before resetting the demo.")
    if not _reset_lock.acquire(blocking=False):
        raise HTTPException(409, "A reset is already in progress.")
    try:
        reset_demo()
    finally:
        _reset_lock.release()
    return {"ok": True, "message": "Demo data reset."}


# ---------------------------------------------------------------------------- demo bot
class DemoMessage(BaseModel):
    session_id: str = "default"
    message: str
    channel: str = "chat"
    preset: str = "v3"


_demo_sessions: dict[str, MockAgentAdapter] = {}
_demo_lock = threading.Lock()


@router.post("/demo-bot/message")
def demo_bot(body: DemoMessage) -> dict[str, Any]:
    """A tiny HTTP bot (the mock Northwind agent) so the Generic HTTP adapter can be tried out of the box."""
    with _demo_lock:
        bot = _demo_sessions.get(body.session_id)
        if bot is None:
            if len(_demo_sessions) > 500:
                _demo_sessions.clear()
            bot = MockAgentAdapter({"preset": body.preset})
            bot.start_session({"seed_key": body.session_id})
            _demo_sessions[body.session_id] = bot
    reply = bot.send_message(body.message, body.channel)
    return {"session_id": body.session_id, "reply": reply.text}

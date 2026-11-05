"""Non-secret settings persisted in SQLite (thresholds, judge mode)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .models import AppSetting
from .readiness import DEFAULT_THRESHOLDS

DEFAULT_SETTINGS: dict[str, Any] = {
    "judge_mode": "auto",
    "thresholds": DEFAULT_THRESHOLDS,
}


def get_setting(db: Session, key: str) -> Any:
    row = db.get(AppSetting, key)
    if row is None:
        return DEFAULT_SETTINGS.get(key)
    if key == "thresholds":
        return {**DEFAULT_THRESHOLDS, **(row.value or {})}
    return row.value


def set_setting(db: Session, key: str, value: Any) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    db.commit()

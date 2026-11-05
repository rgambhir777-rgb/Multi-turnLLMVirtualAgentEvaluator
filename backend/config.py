"""Paths and environment-driven configuration.

Secrets (API keys, CXone credentials) live only in the local ``.env`` file and
the process environment. They are never written to the database.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _base_dir() -> Path:
    """Directory that holds user data (.env, data/). Next to the exe when frozen."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _resource_dir() -> Path:
    """Directory that holds bundled read-only resources (frontend/dist, sample_data)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", _base_dir()))
    return Path(__file__).resolve().parent.parent


BASE_DIR: Path = _base_dir()
RESOURCE_DIR: Path = _resource_dir()
ENV_FILE: Path = Path(os.environ.get("AGENTPROOF_ENV_FILE", BASE_DIR / ".env"))
DATA_DIR: Path = Path(os.environ.get("AGENTPROOF_DATA_DIR", BASE_DIR / "data"))
FRONTEND_DIST: Path = RESOURCE_DIR / "frontend" / "dist"
SAMPLE_DATA_DIR: Path = RESOURCE_DIR / "sample_data"
TEMPLATES_DIR: Path = RESOURCE_DIR / "backend" / "templates"

load_dotenv(ENV_FILE, override=False)

#: Environment variables that hold secrets; masked whenever shown in the UI.
SECRET_KEYS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "CXONE_CLIENT_SECRET",
    "CXONE_ACCESS_KEY_SECRET",
)

#: All environment variables editable from the Settings page.
EDITABLE_ENV_KEYS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "LLM_PROVIDER",
    "VOICE_ROUNDTRIP",
    "CXONE_AUTH_URL",
    "CXONE_API_BASE_URL",
    "CXONE_CLIENT_ID",
    "CXONE_CLIENT_SECRET",
    "CXONE_ACCESS_KEY_ID",
    "CXONE_ACCESS_KEY_SECRET",
    "CXONE_BUSINESS_UNIT",
    "CXONE_CHANNEL_ID",
    "CXONE_POINT_OF_CONTACT",
)

DEFAULTS: dict[str, str] = {
    "ANTHROPIC_MODEL": "claude-opus-5-5",
    "OPENAI_BASE_URL": "https://api.openai.com/v1",
    "OPENAI_MODEL": "gpt-4o-mini",
    "LLM_PROVIDER": "auto",
    "VOICE_ROUNDTRIP": "false",
    "CXONE_AUTH_URL": "https://cxone.niceincontact.com/auth/token",
    "CXONE_API_BASE_URL": "",
}


def env(key: str, default: str | None = None) -> str:
    """Return an environment value, falling back to the documented default."""
    value = os.environ.get(key)
    if value is None or value == "":
        return default if default is not None else DEFAULTS.get(key, "")
    return value


def database_url() -> str:
    """SQLite URL for the application database."""
    override = os.environ.get("AGENTPROOF_DB")
    if override:
        return override if "://" in override else f"sqlite:///{override}"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{(DATA_DIR / 'agentproof.db').as_posix()}"


def mask(value: str) -> str:
    """Mask a secret for display, keeping only the last four characters."""
    if not value:
        return ""
    if len(value) <= 8:
        return "•" * len(value)
    return "•" * 8 + value[-4:]


def update_env_file(updates: dict[str, str]) -> None:
    """Persist key/value pairs to the local .env file and the running process.

    Existing lines are updated in place; comments and unknown keys are preserved.
    An empty value removes the variable.
    """
    lines: list[str] = []
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    remaining = dict(updates)
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in remaining:
                value = remaining.pop(key)
                if value != "":
                    out.append(f"{key}={value}")
                continue
        out.append(line)
    for key, value in remaining.items():
        if value != "":
            out.append(f"{key}={value}")
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENV_FILE.write_text("\n".join(out).strip() + "\n", encoding="utf-8")
    for key, value in updates.items():
        if value == "":
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

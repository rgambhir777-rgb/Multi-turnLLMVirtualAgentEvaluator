"""Test configuration: isolated database and .env in a temp dir, no real API keys."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="agentproof-tests-"))
os.environ["AGENTPROOF_DB"] = str(_TMP / "test.db")
os.environ["AGENTPROOF_ENV_FILE"] = str(_TMP / "test.env")
for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "LLM_PROVIDER", "CXONE_CLIENT_ID", "CXONE_CLIENT_SECRET",
            "CXONE_ACCESS_KEY_ID", "CXONE_ACCESS_KEY_SECRET", "CXONE_API_BASE_URL", "CXONE_BUSINESS_UNIT", "CXONE_CHANNEL_ID"):
    os.environ.pop(key, None)


@pytest.fixture(scope="session")
def kb():
    """The seeded Northwind knowledge base as a KnowledgeIndex."""
    from backend.kb import KnowledgeIndex, parse_markdown

    facts = parse_markdown((ROOT / "sample_data" / "northwind_kb.md").read_text(encoding="utf-8"))
    return KnowledgeIndex.from_rows([dict(f, id=i) for i, f in enumerate(facts)])


@pytest.fixture(scope="session")
def client():
    """A TestClient over the full app; first use seeds the demo database."""
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as test_client:
        yield test_client

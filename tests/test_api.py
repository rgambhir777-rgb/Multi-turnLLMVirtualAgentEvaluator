"""API endpoint tests against the seeded demo database."""
from __future__ import annotations

import io
import time

from conftest import ROOT


def test_status_reports_offline_mode(client):
    data = client.get("/api/status").json()
    assert data["effective_judge"] == "heuristic" and data["offline"] is True
    assert "No LLM API key" in data["offline_reason"]


def test_seeded_runs_show_quality_progression(client):
    runs = {r["agent_name"]: r for r in client.get("/api/runs").json()}
    assert runs["Agent v1 (weak)"]["verdict"] == "NO-GO"
    assert runs["Agent v2 (improving)"]["verdict"] == "CONDITIONAL"
    assert runs["Agent v3 (ready)"]["verdict"] == "GO"
    assert all(r["status"] == "completed" for r in runs.values())


def test_dashboard(client):
    data = client.get("/api/dashboard").json()
    assert len(data["cards"]) == 3 and len(data["trends"]) == 3
    assert {row["channel"] for row in data["channel_scores"]} == {"chat", "sms", "email", "voice"}
    assert data["worst_journeys"] and data["kpis"]["turns"] > 500


def test_agents_crud_and_connection_test(client):
    meta = client.get("/api/agents/meta").json()
    assert set(meta["adapter_types"]) == {"mock", "http", "llm", "cxone"}
    created = client.post("/api/agents", json={"name": "Temp bot", "adapter_type": "mock", "config": {"preset": "v2"}})
    assert created.status_code == 201
    agent_id = created.json()["id"]
    test = client.post(f"/api/agents/{agent_id}/test").json()
    assert test["ok"] and test["sample_reply"]
    updated = client.put(f"/api/agents/{agent_id}", json={"name": "Temp bot 2", "adapter_type": "mock", "config": {"preset": "v3"}})
    assert updated.json()["name"] == "Temp bot 2"
    assert client.post("/api/agents", json={"name": "x", "adapter_type": "fax"}).status_code == 400
    assert client.delete(f"/api/agents/{agent_id}").status_code == 204
    assert client.get(f"/api/agents/{agent_id}").status_code == 404


def test_unconfigured_adapters_fail_gracefully(client):
    agents = {a["adapter_type"]: a for a in client.get("/api/agents").json()}
    cxone = client.post(f"/api/agents/{agents['cxone']['id']}/test").json()
    llm = client.post(f"/api/agents/{agents['llm']['id']}/test").json()
    assert not cxone["ok"] and "CXONE_" in cxone["message"]
    assert not llm["ok"] and "API key" in llm["message"]


def test_knowledge_base_crud_import_export(client):
    count = len(client.get("/api/kb").json())
    fact = client.post("/api/kb", json={"category": "Promos", "title": "Spring promo", "content": "Spring promo costs $19.99."}).json()
    assert client.put(f"/api/kb/{fact['id']}", json={"category": "Promos", "title": "Spring promo", "content": "Now $17.99."}).status_code == 200
    md = b"## Roaming\n\n### EU roaming\nEU roaming costs $5 per day.\n"
    imported = client.post("/api/kb/import", files={"file": ("kb.md", io.BytesIO(md), "text/markdown")}, data={"mode": "append"})
    assert imported.json()["imported"] == 1
    bad = client.post("/api/kb/import", files={"file": ("kb.md", io.BytesIO(b"no headings"), "text/markdown")})
    assert bad.status_code == 400
    assert "### EU roaming" in client.get("/api/kb/export").text
    assert len(client.get("/api/kb").json()) == count + 2
    client.delete(f"/api/kb/{fact['id']}")


def test_journeys_discover_upload_and_generate_scripts(client):
    raw = (ROOT / "sample_data" / "northwind_transcripts.csv").read_bytes()
    res = client.post("/api/journeys/discover", files={"file": ("t.csv", io.BytesIO(raw), "text/csv")}, data={"use_llm": "false"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["transcripts"] == 220 and len(body["journeys"]) >= 6
    journey = body["journeys"][0]
    created = client.post(f"/api/journeys/{journey['id']}/generate-scripts", json={"variants": ["standard", "topic_switch"], "channel": "sms"})
    assert created.status_code == 201 and len(created.json()) == 2
    manual = client.post("/api/journeys", json={"name": "Roaming abroad", "intent": "other", "example_utterances": ["Does my plan work in Spain?"]}).json()
    gen = client.post(f"/api/journeys/{manual['id']}/generate-scripts", json={"variants": ["memory_recall"]}).json()
    assert "Spain" in " ".join(t["customer"] for t in gen[0]["turns"])
    assert client.post("/api/journeys/discover", files={"file": ("x.json", io.BytesIO(b"[]"), "application/json")}).status_code == 400


def test_scripts_crud_and_validation(client):
    body = {"name": "API script", "channel": "chat", "variant": "standard", "goal": "Check hours",
            "turns": [{"customer": "What are your phone hours?", "must_include": ["8 AM"]}]}
    created = client.post("/api/scripts", json=body)
    assert created.status_code == 201
    sid = created.json()["id"]
    body["turns"].append({"customer": "And chat?", "must_include": ["24/7"]})
    assert client.put(f"/api/scripts/{sid}", json=body).json()["turn_count"] == 2
    assert client.post(f"/api/scripts/{sid}/duplicate").status_code == 201
    assert client.post("/api/scripts", json={**body, "channel": "fax"}).status_code == 422
    assert client.post("/api/scripts", json={**body, "turns": []}).status_code == 422


def test_run_executes_in_background_and_reports(client):
    agents = {a["name"]: a["id"] for a in client.get("/api/agents").json()}
    scripts = [s["id"] for s in client.get("/api/scripts").json()][:3]
    started = client.post("/api/runs", json={"agent_id": agents["Agent v3 (ready)"], "script_ids": scripts, "channels": ["chat", "voice"]})
    assert started.status_code == 201
    run_id = started.json()["id"]
    for _ in range(100):
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] in ("completed", "failed"):
            break
        time.sleep(0.2)
    assert run["status"] == "completed", run["error"]
    assert run["total_conversations"] == 6 and len(run["conversations"]) == 6
    conv = client.get(f"/api/conversations/{run['conversations'][0]['id']}").json()
    assert conv["turns"] and "claims" in conv["turns"][0] and conv["turns"][0]["judge"] == "heuristic"
    pdf = client.get(f"/api/runs/{run_id}/report.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    html = client.get(f"/api/runs/{run_id}/report.html").text
    assert "Key risks" in html and "Readiness by channel" in html and run["agent_name"] in html
    csv_text = client.get(f"/api/runs/{run_id}/export.csv").text
    assert csv_text.startswith("run_id,agent") and csv_text.count("\n") > 6
    assert client.get(f"/api/runs/{run_id}/export.json").json()["turns"]


def test_run_validation_errors(client):
    assert client.post("/api/runs", json={"agent_id": 9999, "script_ids": [1]}).status_code == 404
    agent_id = client.get("/api/agents").json()[0]["id"]
    assert client.post("/api/runs", json={"agent_id": agent_id, "script_ids": [1], "channels": ["fax"]}).status_code == 400
    assert client.post("/api/runs", json={"agent_id": agent_id, "script_ids": []}).status_code == 422


def test_compare_runs(client):
    runs = {r["agent_name"]: r["id"] for r in client.get("/api/runs").json() if r["status"] == "completed"}
    data = client.get(f"/api/compare?a={runs['Agent v1 (weak)']}&b={runs['Agent v3 (ready)']}").json()
    assert data["deltas"]["avg_accuracy"] > 0 and data["deltas"]["hallucination_rate"] < 0
    assert len(data["by_channel"]) == 4 and data["conversations"]


def test_settings_masks_secrets_and_persists_thresholds(client):
    saved = client.put("/api/settings", json={"env": {"OPENAI_BASE_URL": "http://localhost:1234/v1"},
                                               "judge_mode": "heuristic", "thresholds": {"min_accuracy": 4.2}}).json()
    assert saved["env"]["OPENAI_BASE_URL"]["value"] == "http://localhost:1234/v1"
    assert saved["judge_mode"] == "heuristic" and saved["thresholds"]["min_accuracy"] == 4.2
    client.put("/api/settings", json={"env": {"ANTHROPIC_API_KEY": "sk-ant-test-123456789"}})
    masked = client.get("/api/settings").json()["env"]["ANTHROPIC_API_KEY"]
    assert masked["set"] and "sk-ant" not in masked["value"] and masked["value"].endswith("6789")
    # Sending the masked value back must not overwrite the real key.
    client.put("/api/settings", json={"env": {"ANTHROPIC_API_KEY": masked["value"]}})
    from backend.config import env
    assert env("ANTHROPIC_API_KEY") == "sk-ant-test-123456789"
    assert client.put("/api/settings", json={"env": {"NOT_A_SETTING": "x"}}).status_code == 400
    assert client.put("/api/settings", json={"judge_mode": "psychic"}).status_code == 400
    # Clean up: remove the fake key and restore defaults.
    client.put("/api/settings", json={"env": {"ANTHROPIC_API_KEY": "", "OPENAI_BASE_URL": ""}, "judge_mode": "auto",
                                      "thresholds": {"min_accuracy": 4.0}})
    assert client.get("/api/status").json()["effective_judge"] == "heuristic"


def test_demo_bot_endpoint(client):
    first = client.post("/api/demo-bot/message", json={"session_id": "t1", "message": "My account is NW-111222."}).json()
    second = client.post("/api/demo-bot/message", json={"session_id": "t1", "message": "Please enroll my account in autopay."}).json()
    assert "NW-111222" in first["reply"] and "NW-111222" in second["reply"]


def test_spa_fallback_and_unknown_api(client):
    assert client.get("/api/does-not-exist").status_code == 404
    page = client.get("/runs/1")
    assert page.status_code == 200 and "<html" in page.text.lower()


def test_reset_demo_restores_seed(client):
    client.post("/api/agents", json={"name": "To be wiped", "adapter_type": "mock", "config": {}})
    assert client.post("/api/settings/reset-demo").json()["ok"]
    names = [a["name"] for a in client.get("/api/agents").json()]
    assert "To be wiped" not in names and len(names) == 6
    assert len(client.get("/api/runs").json()) == 3

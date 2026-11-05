"""First-launch demo data: Northwind KB, transcripts, journeys, 15 scripts, agents and 3 completed runs."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from .builder import SEED_PLAN, build_script
from .config import SAMPLE_DATA_DIR
from .database import Base, SessionLocal, engine, init_db
from .discovery import discover_journeys, parse_transcripts
from .kb import parse_markdown
from .models import Agent, Journey, KBFact, Run, TestScript, Transcript
from .runner import execute_run

CHANNELS = ["chat", "sms", "email", "voice"]

MOCK_AGENTS = [
    ("Agent v1 (weak)", "v1", "First Northwind bot build: forgets details, misquotes fees, invents offers, ignores channel rules."),
    ("Agent v2 (improving)", "v2", "Second build: accurate answers, occasional re-asks and rare invented policies."),
    ("Agent v3 (ready)", "v3", "Release candidate: grounded answers, remembers context, formats for every channel."),
]


#: Resolved per request by the HTTP adapter, so it follows whichever port the server uses.
DEMO_HTTP_URL = "http://127.0.0.1:${AGENTPROOF_PORT}/api/demo-bot/message"


def is_empty() -> bool:
    with SessionLocal() as db:
        return (db.scalar(select(func.count()).select_from(Agent)) or 0) == 0 and (
            db.scalar(select(func.count()).select_from(KBFact)) or 0
        ) == 0


def seed(with_runs: bool = True) -> None:
    """Populate an empty database with the full Northwind demo."""
    init_db()
    with SessionLocal() as db:
        kb_text = (SAMPLE_DATA_DIR / "northwind_kb.md").read_text(encoding="utf-8")
        for fact in parse_markdown(kb_text):
            db.add(KBFact(category=fact["category"], title=fact["title"], content=fact["content"], tags=[]))

        raw = (SAMPLE_DATA_DIR / "northwind_transcripts.json").read_bytes()
        transcripts = parse_transcripts(raw, "northwind_transcripts.json")
        rows = [Transcript(external_id=str(t["external_id"]), channel=str(t["channel"]), turns=t["turns"]) for t in transcripts]
        db.add_all(rows)
        db.flush()

        journeys_by_intent: dict[str, Journey] = {}
        for found in discover_journeys(transcripts, use_llm=False):
            journey = Journey(name=found.name, description=found.description, intent=found.intent, keywords=found.keywords,
                              frequency=found.frequency, avg_turns=found.avg_turns,
                              example_utterances=found.example_utterances, source="discovered", labeler=found.labeler)
            db.add(journey)
            db.flush()
            for member in found.members:
                rows[member].journey_id = journey.id
            journeys_by_intent.setdefault(found.intent, journey)

        for i, (intent, variant, channel) in enumerate(SEED_PLAN):
            journey = journeys_by_intent.get(intent)
            spec = build_script({"intent": intent, "name": journey.name if journey else intent}, variant, f"seed-{i}")
            db.add(TestScript(name=spec["name"], journey_id=journey.id if journey else None, channel=channel,
                              variant=variant, persona=spec["persona"], goal=spec["goal"],
                              email_subject=spec["subject"], turns=spec["turns"]))

        mock_agents = []
        for name, preset, description in MOCK_AGENTS:
            agent = Agent(name=name, adapter_type="mock", description=description, config={"preset": preset})
            db.add(agent)
            mock_agents.append(agent)
        db.add(Agent(name="Northwind bot over HTTP (demo endpoint)", adapter_type="http",
                     description="Generic HTTP adapter pointed at AgentProof's built-in demo bot endpoint.",
                     config={"url": DEMO_HTTP_URL, "method": "POST", "headers": {},
                             "request_template": '{"session_id": "{{session_id}}", "message": "{{message}}", "channel": "{{channel}}"}',
                             "response_path": "reply", "timeout_s": 30}))
        db.add(Agent(name="LLM stand-in agent", adapter_type="llm",
                     description="Claude or an OpenAI-compatible model acting as the virtual agent (needs an API key).",
                     config={"provider": "auto", "include_kb": True}))
        db.add(Agent(name="NICE CXone production bot", adapter_type="cxone",
                     description="Connects to a CXone Digital channel routed to your virtual agent. Add credentials in Settings.",
                     config={}))
        db.commit()

        if not with_runs:
            return
        script_ids = [s.id for s in db.scalars(select(TestScript).order_by(TestScript.id))]
        now = datetime.now(timezone.utc)
        run_ids = []
        for days_ago, agent in zip((21, 10, 2), mock_agents):
            run = Run(name=f"Release check – {agent.name}", agent_id=agent.id, agent_name=agent.name, status="queued",
                      script_ids=script_ids, channels=CHANNELS, judge_mode="heuristic",
                      created_at=now - timedelta(days=days_ago), started_at=now - timedelta(days=days_ago))
            db.add(run)
            db.commit()
            run_ids.append((run.id, days_ago))

    for run_id, days_ago in run_ids:
        execute_run(run_id)
        with SessionLocal() as db:
            run = db.get(Run, run_id)
            if run is not None:
                run.started_at = now - timedelta(days=days_ago)
                run.finished_at = now - timedelta(days=days_ago) + timedelta(minutes=4)
                db.commit()


def reset_demo() -> None:
    """Drop every table and re-seed the demo."""
    Base.metadata.drop_all(engine)
    seed()


def seed_if_empty() -> bool:
    """Seed on first launch. Returns True if seeding happened."""
    init_db()
    if is_empty():
        seed()
        return True
    return False

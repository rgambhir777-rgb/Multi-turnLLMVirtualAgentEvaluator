"""Journey discovery, transcript parsing, KB parsing and script builder tests."""
from __future__ import annotations

from backend.builder import SEED_PLAN, VARIANTS, build_script
from backend.discovery import discover_journeys, parse_transcripts
from backend.kb import parse_csv, parse_markdown
from conftest import ROOT


def test_parse_transcripts_json_and_csv_agree():
    js = parse_transcripts((ROOT / "sample_data" / "northwind_transcripts.json").read_bytes(), "t.json")
    cs = parse_transcripts((ROOT / "sample_data" / "northwind_transcripts.csv").read_bytes(), "t.csv")
    assert len(js) == len(cs) >= 200
    assert js[0]["turns"][0]["speaker"] == "customer"


def test_parse_wide_csv_format():
    raw = b'id,channel,transcript\nA1,chat,"Customer: My internet is down\nAgent: Sorry to hear that"\n'
    parsed = parse_transcripts(raw, "wide.csv")
    assert parsed[0]["turns"] == [{"speaker": "customer", "text": "My internet is down"},
                                  {"speaker": "agent", "text": "Sorry to hear that"}]


def test_discovery_finds_northwind_journeys():
    transcripts = parse_transcripts((ROOT / "sample_data" / "northwind_transcripts.json").read_bytes(), "t.json")
    journeys = discover_journeys(transcripts, use_llm=False)
    intents = {j.intent for j in journeys}
    assert {"billing", "plan_change", "outage", "password_reset", "cancellation", "refund", "general"} <= intents
    assert sum(j.frequency for j in journeys) == len(transcripts)
    assert all(j.example_utterances and j.avg_turns > 0 for j in journeys)


def test_kb_markdown_and_csv_import():
    facts = parse_markdown((ROOT / "sample_data" / "northwind_kb.md").read_text(encoding="utf-8"))
    assert len(facts) >= 25 and {"category", "title", "content"} <= set(facts[0])
    csv_facts = parse_csv("category,title,content\nPlans,Promo,Promo plan costs $9.99\n")
    assert csv_facts == [{"category": "Plans", "title": "Promo", "content": "Promo plan costs $9.99", "tags": ""}]


def test_builder_generates_every_variant_with_expectations():
    for variant in VARIANTS:
        spec = build_script({"intent": "billing", "name": "Billing"}, variant, "seed")
        assert spec["turns"] and spec["persona"]["account"].startswith("NW-")
        assert all({"customer", "must_include", "must_not_include", "must_remember"} <= set(t) for t in spec["turns"])


def test_memory_recall_reuses_turn_one_detail_in_turn_four():
    spec = build_script({"intent": "billing", "name": "Billing"}, "memory_recall", "seed")
    account = spec["persona"]["account"]
    assert account in spec["turns"][0]["customer"]
    assert account in spec["turns"][3]["must_remember"]


def test_correction_variant_forbids_superseded_account():
    spec = build_script({"intent": "refund", "name": "Refunds"}, "correction", "seed")
    persona_account = spec["persona"]["account"]
    later = spec["turns"][2:]
    assert any(persona_account in t["must_not_include"] for t in later)


def test_unknown_intent_uses_example_utterances():
    spec = build_script({"intent": "other", "name": "Roaming", "example_utterances": ["Does my plan work abroad?"]}, "standard", "s")
    assert any("abroad" in t["customer"] for t in spec["turns"])


def test_seed_plan_covers_all_channels():
    assert len(SEED_PLAN) == 15
    assert {c for _, _, c in SEED_PLAN} == {"chat", "sms", "email", "voice"}

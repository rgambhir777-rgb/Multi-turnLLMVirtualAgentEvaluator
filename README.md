# AgentProof: Multi-turn LLM Virtual Agent Evaluator

**Contact-centre QA for NICE CXone.** AgentProof tests agentic, LLM-driven virtual agents across **chat, voice,
email and SMS** before they reach customers.

| | |
|---|---|
| **Problem** | A virtual agent can sound fluent while losing context, giving wrong answers or inventing facts mid-conversation. |
| **Approach** | Multi-turn test conversations built from discovered customer journeys. Every agent turn is scored for **context awareness**, **accuracy** and **hallucination** (plus channel fit), and every factual claim is checked against a knowledge base. |
| **Result** | Quality evidence the business can act on: a clear **GO / CONDITIONAL / NO-GO** verdict per agent and per channel, with the reasons and example transcripts. |

It runs fully **offline with no API keys** (built-in heuristic judge and a simulated "Northwind Telecom" bot). Add an
Anthropic or OpenAI-compatible key to switch on the LLM-as-judge.

---

## Quick start (3 steps)

1. **Install Python 3.11, 3.12 or 3.13** from <https://www.python.org/downloads/> (on Windows, tick *"Add python.exe to PATH"*).
   Node.js is **not** needed, because the built web UI is included.
2. **Start it:**
   * **Windows:** double-click **`start.bat`** (or run `.\start.bat` in a terminal).
   * **macOS / Linux:** run `bash start.sh`.
3. **Use it:** your browser opens **http://localhost:8000**. The first launch installs dependencies (1–2 minutes) and seeds
   the demo (about 15 seconds). The dashboard then shows three agents already evaluated.

Stop the app with `Ctrl+C` in the terminal window. Run the same script again next time; it starts in seconds.

> If port 8000 is already used by another program, AgentProof picks the next free port (8001, 8002, …) and prints the
> address. Set `AGENTPROOF_PORT` in `.env` to choose one.

**Optional single-file Windows app:** run `build_exe.bat` (after `start.bat` has run once) to produce `dist\AgentProof.exe`.
Double-click it on any Windows PC; no Python needed. It stores `.env` and `data\` next to itself.

---

## What you see (pages)

| Page | What it shows |
|---|---|
| **Dashboard** | Readiness verdict card per agent (GO / CONDITIONAL / NO-GO with the reasons and per-channel verdicts), KPI tiles, score trends across runs, accuracy and hallucination rate by channel, worst journeys. Every chart has a *Table* view. |
| **Agents** | Agent connections (Mock, HTTP, LLM, NICE CXone) with add/edit/delete and a **Test connection** button that shows the bot's actual reply or a clear error. Mock agents have sliders for each flaw rate. |
| **Journeys** | Upload historical transcripts (CSV/JSON) and **discover journeys** by clustering: name, frequency, typical turn count, keywords, example utterances. Create or edit journeys by hand and **generate test scripts** with adversarial variants. |
| **Test Scripts** | List and editor: persona, goal, email subject, and ordered customer turns with per-turn expectations: *must include*, *must NOT include*, *must remember from earlier*. Add, remove and reorder turns. |
| **Knowledge Base** | The ground truth (plans, prices, fees, refund windows, outage procedure, support hours…). Edit inline, import Markdown/CSV, export Markdown. |
| **Runs** | Start a run (scripts × agent × channels, choose judge) and watch live progress. Run detail shows the verdict, reasons, per-channel readiness and every conversation, worst first. |
| **Conversation Viewer** | The transcript styled per channel: chat bubbles, an SMS phone frame with segment counts, an email thread, or a voice call with the speech-to-text transcript. Agent turns are colour-coded by score. Click a turn to see the four scores, written justifications, the **claim-by-claim hallucination table**, the expectations and channel flags. |
| **Compare** | Two runs side by side (e.g. Agent v1 vs v3): metric deltas (better/worse), per-channel verdict changes, per-journey changes, and the same script in both runs. |
| **Reports** | Stakeholder report per run as **HTML** and **PDF** (executive summary, verdict, key risks, results by channel and journey, example failures with transcripts) plus **CSV/JSON** export of every turn score. |
| **Settings** | API keys and CXone credentials (written to your local `.env` and masked), judge mode, readiness thresholds, *Test LLM connection* and **Reset demo data**. |

---

## The seeded demo: Northwind Telecom

On first launch (empty database) AgentProof creates:

* a **27-fact Northwind knowledge base** (`sample_data/northwind_kb.md`)
* **220 synthetic historical transcripts** (`sample_data/northwind_transcripts.json` / `.csv`)
* **7 discovered journeys**: billing, plan changes, outages, password reset, cancellation, refunds, support hours
* **15 test scripts** covering all four channels and every adversarial variant
* **6 agents**: three mock agents plus HTTP, LLM and CXone examples
* **3 completed runs** (one per mock agent; every script on chat, SMS, email and voice, 264 scored turns each)

| Agent | Built-in behaviour | Verdict |
|---|---|---|
| **Agent v1 (weak)** | Forgets details and re-asks for them, misquotes prices and fees, invents offers, ignores channel rules | **NO-GO** on every channel |
| **Agent v2 (improving)** | Accurate answers; occasional re-asks, rare invented policies, some voice/email formatting slips | **CONDITIONAL** (chat and SMS GO, email CONDITIONAL, voice NO-GO) |
| **Agent v3 (ready)** | Grounded, remembers context, formats correctly for every channel | **GO** on every channel |

The mock agent's flaws are **planted, not scripted against the judge**: the bot only sees customer messages, and the judge
only sees the bot's replies, the conversation and the KB. Flaw decisions are seeded, so results are reproducible.

---

## How scoring works

Every agent turn gets four 0–5 scores with written justifications. The judge that produced the score is shown on each turn.

**Context awareness.** Did the reply correctly use information from earlier turns? The judge tracks account numbers
(including spoken forms like "n w 482913"), ZIP codes, plans and amounts across the conversation. It deducts for
details the turn must remember but doesn't use, for **re-asking** for something already given, and for using a wrong or
**superseded** value (for example after the customer corrected their plan or account). The run average only counts turns that depend on
earlier context.

**Accuracy.** Are the turn's required facts present (number-aware: "$5" matches "$5.00"; `a|b` alternatives)? Is any
forbidden content present? Does any claim contradict the KB?

**Hallucination.** The reply is split into factual claims: sentences with prices, durations, speeds or times, or with
policy language such as fee, refund, credit, guarantee, free or eligible. Each claim is matched to the most relevant
KB facts and labelled:

* **Supported**: its numbers/content match the KB, or the customer said it earlier
* **Contradicted**: the matching KB fact has a different value of the same kind (e.g. $49.99 vs $59.99, 24 hours vs 10 minutes, "free" vs a $10 fee)
* **Unsupported**: nothing in the KB or conversation backs it (invented offers, policies, numbers)

Score = `5 − 3 × contradicted − 2 × unsupported` (minimum 0). A turn with any non-supported claim counts toward the **hallucination rate**.

**Channel fit** (rules, identical in both judge modes):
SMS uses 160-character segments with no markdown or paragraphs.
Voice flags URLs read aloud, markdown, tables, long lists and long replies.
Email needs a greeting, a sign-off and enough substance.
Chat flags very long replies.

**Task completion** (per conversation): at least 80% of the expected facts and remembered details were delivered, with no critical failure.

**Critical failures**: contradicted facts, forbidden content, asking the customer for their password, empty replies or mostly-wrong answers.

**Channels change the test, not just the score.** Voice customer turns pass through simulated speech-to-text (lower-case,
no punctuation, filler words, homophones such as "to/too" and "for/four"), or a real TTS→STT round trip when
`VOICE_ROUNDTRIP=true` and an OpenAI-compatible key are set. Email turns become multi-paragraph emails with a subject line.

### Two judges

| | Offline heuristic judge | LLM-as-judge |
|---|---|---|
| Needs | nothing | `ANTHROPIC_API_KEY` (default model `claude-opus-5-5`) or `OPENAI_API_KEY` |
| Method | typed quantity extraction, entity tracking, content-word overlap + RapidFuzz similarity against the KB | strict rubric prompt with the KB, history and expectations; JSON validated with Pydantic; retried up to 3 times |
| Determinism | fully deterministic | OpenAI-compatible: temperature 0. Current Claude models reject sampling parameters, so consistency comes from the rubric and schema validation. |

Judge mode **auto** (default) uses the LLM when a key exists. If the LLM fails mid-run (bad key, network, refusal,
invalid JSON), the run switches to the heuristic judge for the remaining turns, labels them `heuristic (LLM fallback)`, and the
UI shows an offline banner. The app never crashes for a missing or invalid key.

### Readiness verdict

| Threshold (editable in Settings) | Default | CONDITIONAL band |
|---|---|---|
| Average accuracy | ≥ 4.0 | ≥ 3.5 |
| Context awareness | ≥ 4.0 | ≥ 3.5 |
| Hallucination rate | ≤ 2% of turns | ≤ 4% |
| Channel fit | ≥ 3.5 | ≥ 3.0 |
| Task completion | ≥ 80% | ≥ 70% |
| Critical failures | 0 | (any is NO-GO) |

**GO**: all met. **CONDITIONAL**: only narrow misses. **NO-GO**: a wider miss or any critical failure. The verdict is computed for
the whole run and separately for each channel, and the reasons are listed (hard blockers first).

---

## Connect a real NICE CXone bot

1. In CXone, create (or reuse) an **access key** for an API user and note your **client id/secret**, **business unit**, the
   API host for your area (e.g. `https://api-na1.niceincontact.com`) and the **Digital channel** (and optional point of contact)
   that routes to your virtual agent (Bot Builder / Autopilot / your LLM bot).
2. Open **Settings → NICE CXone**, fill in the fields and **Save**. They go to your local `.env` and are never stored in the database.
3. Open **Agents → NICE CXone production bot → Test connection**. Missing values are listed by name; authentication
   errors are reported plainly.
4. Tenant-specific endpoint paths are marked `TODO(tenant)` in `backend/adapters/nice_cxone.py`: the inbound-message
   path, the thread-messages listing used to poll for the bot reply, and the close-thread call. Confirm them against your
   tenant's DFO channel-integration setup. The OAuth flow, polling, timeouts and error handling are already implemented.

## Connect any HTTP bot

Agents → **Add agent** → *Generic HTTP bot endpoint*, then edit the JSON config:

```json
{
  "url": "https://bot.example.com/api/message",
  "method": "POST",
  "headers": {"Authorization": "Bearer ${BOT_API_TOKEN}"},
  "request_template": "{\"session_id\": \"{{session_id}}\", \"message\": \"{{message}}\", \"channel\": \"{{channel}}\"}",
  "response_path": "reply",
  "session_response_path": "session.id",
  "timeout_s": 30
}
```

* `{{message}}`, `{{channel}}` and `{{session_id}}` are filled in for every turn (or use `message_path` / `channel_path` /
  `session_path` to write them into a default body).
* `response_path` is a dotted path to the reply text, e.g. `data.messages.0.text`.
* `${ENV_VAR}` in the URL or headers is replaced from the environment/`.env`, so tokens stay out of the database.

The seeded agent **"Northwind bot over HTTP (demo endpoint)"** points at AgentProof's own `/api/demo-bot/message`
endpoint, so you can see the HTTP adapter work end to end immediately.

**LLM stand-in agent:** use *LLM stand-in agent* to evaluate a prompt-based bot (Claude or any OpenAI-compatible model)
with your own system prompt; `{kb}` inserts the knowledge base.

---

## Bring your own data

* **Transcripts:** JSON list of `{"id", "channel", "turns": [{"speaker": "customer"|"agent", "text"}]}`, a CSV with
  `transcript_id, channel, turn_index, speaker, text` (one row per turn), or a CSV with `id, channel, transcript` where the
  transcript has `Customer:` / `Agent:` lines. Regenerate the sample with `python sample_data/generate_transcripts.py`.
* **Knowledge base:** Markdown with `## Category` and `### Fact title` headings, or CSV `category,title,content[,tags]`. State exact
  numbers ("$59.99 per month", "5-7 business days") so the judge can verify them.
* **Scripts:** generate from journeys (variants: standard, topic switch, correction, ambiguous, out-of-scope, memory recall),
  then edit, or write your own in the editor.

---

## Configuration

All settings are optional; see `.env.example`. The Settings page edits the same file.

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | Claude for the LLM judge / labelling / stand-in agent (default `claude-opus-5-5`) |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` | any OpenAI-compatible endpoint |
| `LLM_PROVIDER` | `auto` (Anthropic first), `anthropic` or `openai` |
| `VOICE_ROUNDTRIP` | `true` for a real TTS→STT round trip on voice turns (OpenAI-compatible audio API) |
| `CXONE_*` | NICE CXone credentials and routing |
| `AGENTPROOF_PORT`, `AGENTPROOF_HOST`, `AGENTPROOF_NO_BROWSER`, `AGENTPROOF_DB` | server options |

---

## Project structure

```
backend/
  main.py            FastAPI app, static UI serving, startup (seed, recover interrupted runs)
  config.py          paths, .env handling, secret masking
  models.py          SQLAlchemy models · database.py engine/session · settings_store.py
  adapters/          VirtualAgentAdapter + mock.py, http_adapter.py, llm_agent.py, nice_cxone.py
  judges/            heuristic.py (offline), llm_judge.py (LLM-as-judge), base.py (types, claim scoring)
  discovery/         clustering.py (transcript parsing, TF-IDF + KMeans, journey naming)
  api/               routers: agents, knowledge, journeys, scripts, runs (+dashboard, compare, reports), system
  builder.py         test-script templates and adversarial variants
  channels.py        STT simulation, email rendering, channel-fit rules
  kb.py              KB import and fact ranking · textutils.py quantity/entity extraction
  readiness.py       metrics and GO / CONDITIONAL / NO-GO
  runner.py          background run execution · reports.py HTML/PDF/CSV/JSON · seed.py demo data
  templates/         report.html
frontend/            React + TypeScript + Vite + Tailwind + Recharts (built output committed in frontend/dist)
sample_data/         Northwind KB, 220 transcripts (JSON + CSV) and their generator
tests/               pytest: adapters, judges, readiness, discovery/builder, API
docs/ARCHITECTURE.md component and scoring-pipeline diagrams
run.py               entry point (port selection, browser launch)
start.bat / start.sh one-command start · build_exe.bat + agentproof.spec Windows executable
```

## Development

```bash
.venv/Scripts/python -m pytest          # Windows (macOS/Linux: .venv/bin/python -m pytest), 60 tests
cd frontend && npm install && npm run dev   # UI dev server on :5173, proxies /api to :8000
npm run build                               # rebuild frontend/dist (served by FastAPI)
```

## Decisions and limitations

* **Heuristic judge limits.** It is deliberately conservative and explainable. It verifies numbers and close paraphrases of KB
  facts well, but it cannot understand free-form reasoning: a correct answer phrased very differently from the KB may be marked
  *Unsupported*, and subtle non-numeric contradictions can slip through. Use the LLM judge for nuanced bots, and review the
  claim table in the Conversation Viewer.
* **Channel fit is rule-based in both modes**, so results stay comparable across judges.
* **Context awareness** is averaged over turns that depend on earlier context; first turns would otherwise inflate it.
* **Task completion** is measured as delivery of the scripted expectations, not as a real back-end transaction.
* **NICE CXone:** endpoint paths vary by tenant and Digital channel type. They are marked `TODO(tenant)`, and the adapter
  could not be verified against a live tenant here.
* **Voice:** speech is simulated by default. The optional real round trip uses an OpenAI-compatible audio API; telephony
  (SIP/IVR) is out of scope.
* **PDF** uses ReportLab (pure wheels, no GTK). If PDF generation fails on a machine, the HTML report always works and
  prints to PDF from the browser.
* **Runs** execute in background threads inside the server process. A run interrupted by stopping the server is marked
  failed on the next start; start it again.
* Single-user local tool: no authentication. Don't expose the port publicly.

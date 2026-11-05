# AgentProof – build progress

Weights add up to 100%. A step counts only when it is built **and** tested.

| # | Step | Weight | Status | Evidence |
|---|------|-------:|--------|----------|
| 1 | Backend core: config, SQLite/SQLAlchemy models, settings store | 8% | ✅ Done | App boots, tables created, settings round-trip |
| 2 | Adapters: Mock (v1/v2/v3), Generic HTTP, LLM stand-in, NICE CXone | 10% | ✅ Done | Mock tested in simulation; CXone/LLM fail gracefully; HTTP adapter tested live against demo bot |
| 3 | Judges (heuristic + LLM) and readiness verdict logic | 15% | ✅ Done | Simulation: v1 NO-GO, v2 CONDITIONAL, v3 GO, zero false positives on v3 |
| 4 | Journey discovery, script builder, seeded demo data | 10% | ✅ Done | 220 transcripts → 7 journeys; 15 scripts; 3 completed runs seeded in ~13 s |
| 5 | REST API, reports (HTML/PDF), CSV/JSON export | 12% | ✅ Done | All endpoints 200 via TestClient; PDF renders |
| 6 | Frontend (React/TS/Vite/Tailwind/Recharts) built and served by FastAPI | 15% | ✅ Done | Strict type-check + build pass; every page screenshotted live (headless Edge) and layout issues fixed; SPA deep links work |
| 7 | Pytest suite (adapters, judge, readiness, API) passing | 10% | ✅ Done | 60 tests pass (mock adapter, each flaw type detected, LLM judge retry/fallback, verdict bands, every API router) |
| 8 | start.bat / start.sh, requirements.txt, .env.example | 5% | ✅ Done | start.bat (cmd) and start.sh (bash) both install pinned deps, create .env, seed and serve; busy-port fallback and already-running detection verified |
| 9 | PyInstaller spec + build_exe.bat (+ build attempt) | 5% | ✅ Done | `dist\AgentProof.exe` (~90 MB) built; run from an empty folder: seeds, serves UI, PDF, discovery, HTTP adapter and a background run all work (first build had a missing scipy module, fixed in spec) |
| 10 | README.md + docs/ARCHITECTURE.md (Mermaid) | 6% | ✅ Done | Written; every number and behaviour cross-checked against the running app (27 facts, 220 transcripts, 7 journeys, 15 scripts, 6 agents, 264 turns/run, verdicts) |
| 11 | Clean-from-scratch check (delete venv/node_modules/db, run start script) | 4% | ✅ Done | Deleted .venv, node_modules, __pycache__, data, .env, build; `start.bat` created a new venv, installed pinned deps from PyPI, seeded, served the UI; dashboard verified (v1 NO-GO / v2 CONDITIONAL / v3 GO); 60/60 tests pass on the fresh venv |

**Current: 100%**

## Decisions log
- Port fallback: if 8000 is busy, `run.py` uses the next free port (this dev machine has other servers on 8000/8001).
- Current Claude models reject `temperature`; the Anthropic judge relies on a strict rubric + schema validation instead. OpenAI-compatible calls use `temperature: 0`.
- Context awareness is averaged only over turns that depend on earlier context (otherwise first turns dilute it).
- Channel fit is rule-based in both judge modes (objective length/format checks), so scores are comparable.
- PDF via ReportLab (pure wheels on Windows); WeasyPrint avoided because it needs GTK on Windows.
- cmd parses a bare `start.bat` as its built-in `start` command; README says to double-click it or run `.\start.bat`.
- Mock v2 hallucination rate tuned (0.035) against the real seed keys so the demo shows CONDITIONAL overall (chat/SMS GO, email CONDITIONAL, voice NO-GO).
- Chart animations are disabled so charts render reliably in screenshots and print.

## Resume
If interrupted, continue with the first step not marked ✅ above.

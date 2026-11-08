# Changelog

All work done inside the IBM Db2Hack 2026 submission window (6–10 Nov 2026, IST). New project; nothing reused from earlier hackathons.

## 2026-11-08
- Repo created. OpenAQ public-archive fetcher for 35 Delhi CAAQMS stations (`scripts/fetch_openaq.py`, no API key).
- Downloaded Sep–Dec 2025 hourly data (140 station-months). First check: Oct 2025 missing PM2.5 hours for Chandni Chowk / Punjabi Bagh / Najafgarh = 200 / 138 / 78 (ThePrint reported 224 / 123 / 100).
- Db2 Community Edition 12.1.5 running in Docker; VECTOR + VECTOR_DISTANCE smoke-tested.
- Db2 schema (`sql/01_schema.sql`): READING is a system-period temporal table, range-partitioned by month; STATION_FACT business-time table; VERDICT/EVIDENCE ledger locked by triggers; RULE_TEXT with VECTOR(384).
- CPCB breakpoints, plausibility limits and audit settings (`sql/02_reference.sql`).
- Normaliser (`src/prepare.py`) and idempotent MERGE (`sql/03_merge.sql`): 3,273,888 15-minute readings (35 stations, Sep–Dec 2025) loaded in 28 s.
- Hourly layer and audit (`sql/04_audit.sql`): BUILD_HOURLY (data capture, stuck-sensor runs, impossible jumps via window functions), SUB_INDEX function, COMPUTE_AQI_AUDITED (16-hour rule, 8-hour O3/CO, 3-pollutant rule, refusal), AUDIT_RANGE. Full Sep–Dec audit of 4,392 station-days runs in 2 min 40 s.
- First results: 34 CAAQMS stations, 698 NOT_COMPUTABLE station-days in total (121 of them the US Embassy PM2.5-only monitor). OpenAQ data is 15-minute, which changes how "missing hours" is counted; ThePrint's numbers are not reproduced exactly.
- Fix: the OpenAQ copy stores each hourly CPCB value as four 15-minute rows stamped hh:00–hh:45. Readings are now bucketed by the hour they start in, and an hour counts as valid with one plausible row. Earlier counts (508 refused station-days) were inflated by the old end-of-hour bucketing; corrected count: 247 NOT_COMPUTABLE, 190 of them still given a number by a plain average (67 of those in the Very Poor/Severe range).
- Fault-injection eval (`eval/fault_injection.py`, results in `eval/fault_injection_results.md`): 198 simulated faults planted into real clean days; AQI Truth flags 187 (94%), a min/max threshold rule 75 (38%), a plain average 0. Eval schema AQE is built from the same SQL files.
- `src/db.py` helper; tablespace creation split into `sql/00_tablespace.sql`.
- AI layer: IBM Granite 4.0 micro + granite-embedding-278m-multilingual run locally in Ollama (GGUF from Docker Hub `ai/` models; `ollama/` Modelfiles). Rule paragraphs (CPCB AQI method, CAG findings, our checks) embedded into Db2 `VECTOR(768)` (`src/rules.py`, `data/rules.json`).
- `src/explain.py`: Granite explains a verdict from the evidence ledger only; Db2 VECTOR_DISTANCE retrieval must agree with the rule the procedure cited; output rejected (template used) if it adds numbers, gives advice/predictions, or names the wrong CPCB category. Stored append-only in AQ.EXPLANATION.
- `src/ask.py` + `sql/05_views.sql`: natural-language questions → one SELECT checked by sqlglot (single SELECT, only AQ.V_DAY/AQ.V_CHECK, row cap) → run as Db2 user AQREADER that can read only those views. Out-of-scope questions (forecasts, health advice, blame) are refused.

## 2026-11-08 (later)
- Added FastAPI app (`src/app.py`): station picker, verdict card, 24-hour evidence grid, ledger, calendar, guarded question box.
- Added web UI (`web/`) with a static snapshot mode so the site works on free static hosting without Db2 running.
- Added `scripts/export_snapshot.py`; snapshot covers 1,154 station-days exported from the real Db2 audit run.

## 2026-11-08 (night)
- pytest suite against real Db2 (`tests/`): sub-index, golden-path refusal, append-only triggers, AQREADER denied base tables, temporal history, explanation guard, SQL guard. 21 passing.
- One-command setup: `src/load.py` (schema + load + MERGE + audit + rule embeddings), `docker-compose.yml` (Db2, Ollama with Granite, setup job, app), `Dockerfile`, `.env.example`, `scripts/pull_models.py`, gzipped 3-station October 2025 sample in `data/sample/`. Tested from scratch in an isolated Compose project; sample results match the full run on 91/93 station-days (the 2 differences are 31 Oct month-edge hours).
- Removed the unused business-time table AQ.STATION_FACT.
- `src/ask.py`: Db2 errors raised while fetching rows now return a refusal instead of a crash.
- Question-box eval (`eval/ask_eval.py`): 20 gold questions + 8 attack prompts.
- README rewritten in the official template's layout; `architecture.md` and `submission.json` added; README screenshots.
- Question box hardened: short station names are matched with LIKE, SQL comments stripped, wider out-of-scope filter (safety, children, blame), prompt hints on NULL AQI and failed checks. Eval: 12/20 before, 17/20 after (development score on the same set); 8/8 attack prompts held.
- GitHub Pages live: https://debi910.github.io/aqi-truth/

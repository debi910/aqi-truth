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

# Architecture

AQI Truth has one rule: **Db2 computes and decides, the AI only explains and asks.**
Every number a user sees comes from SQL in Db2. The Granite model never changes a verdict.

```mermaid
flowchart LR
  S3[(OpenAQ public archive<br/>CPCB CAAQMS, CC BY 4.0)] -->|fetch_openaq.py| CSV[CSV per station-month]
  CSV -->|prepare.py + load.py| STAGE[AQ.STAGE_READING]
  STAGE -->|MERGE upsert| READ[(AQ.READING<br/>system-period temporal<br/>range-partitioned by month)]
  READ -->|BUILD_HOURLY<br/>window functions| HOURLY[AQ.HOURLY<br/>coverage, stuck runs, jumps]
  REF[AQ.BREAKPOINT<br/>AQ.PLAUSIBLE<br/>AQ.SETTING] --> AUDIT
  HOURLY --> AUDIT[COMPUTE_AQI_AUDITED<br/>SQL PL procedure]
  AUDIT --> VERDICT[(AQ.VERDICT<br/>append-only)]
  AUDIT --> EVID[(AQ.EVIDENCE<br/>append-only ledger)]
  RULES[data/rules.json] -->|Granite embedding| RT[(AQ.RULE_TEXT<br/>VECTOR 768)]
  VERDICT --> VDAY[AQ.V_DAY / AQ.V_CHECK views]
  EVID --> VDAY
  EVID --> EXPL[explain.py]
  RT -->|VECTOR_DISTANCE| EXPL
  EXPL -->|Granite 4.0 micro<br/>checked: numbers, words, category| EXT[(AQ.EXPLANATION<br/>append-only)]
  Q[User question] --> ASK[ask.py]
  ASK -->|Granite writes SQL<br/>sqlglot checks it| RDR[Db2 user AQREADER<br/>SELECT on 2 views only]
  RDR --> VDAY
  VDAY --> API[FastAPI app.py] --> UI[web/ UI]
```

## Data flow

1. **Ingest.** `scripts/fetch_openaq.py` downloads station-month CSVs from the OpenAQ public S3 archive (no API key). `src/prepare.py` normalises them; `src/load.py` inserts into `AQ.STAGE_READING` and runs `sql/03_merge.sql`.
2. **Store.** `AQ.READING` has primary key `(STATION_ID, PARAM, TS)`, is **range-partitioned by month**, and is a **system-period temporal table** (`PERIOD SYSTEM_TIME`, history in `AQ.READING_HIST`). Re-loading a corrected file only updates rows whose value changed (`MERGE ... WHEN MATCHED AND r.VALUE IS DISTINCT FROM s.VALUE`), and the old value stays queryable with `FOR SYSTEM_TIME AS OF`.
3. **Hourly layer.** `AQ.BUILD_HOURLY` buckets the 15-minute rows into hours and uses window functions (`LAG`, running `SUM` to number runs, `COUNT ... OVER` for run length) to flag stuck sensors (same value for N hours) and impossible jumps between consecutive hours. Plausibility limits come from `AQ.PLAUSIBLE`.
4. **Audit.** `AQ.COMPUTE_AQI_AUDITED(station, day)` applies the CPCB method: 24-hour averages need at least 16 valid hours; O3 and CO use the highest 8-hour average with at least 6 valid hours; an AQI needs at least 3 pollutants, one of them PM2.5 or PM10. Sub-indices come from `AQ.SUB_INDEX` over `AQ.BREAKPOINT`. It also computes the **naive AQI** a plain-average dashboard would show. Output:
   - one row in `AQ.VERDICT` with `VALID`, `SUSPECT` (computable only after excluding bad hours) or `NOT_COMPUTABLE` (with the reason), and
   - one row per pollutant and check in `AQ.EVIDENCE` (coverage, plausibility, stuck, jump, sub-index, minimum pollutants), each with the observed value and the rule it cites.
   `AQ.AUDIT_RANGE(from, to)` runs it for every station and day.
5. **Ledger.** `BEFORE UPDATE` / `BEFORE DELETE` triggers on `AQ.EVIDENCE`, `AQ.VERDICT` and `AQ.EXPLANATION` raise `SQLSTATE 75001`. A re-run adds a new run; `AQ.V_DAY` shows the latest run per station-day.
6. **Explain.** `src/explain.py` reads a verdict and its failed checks, runs a Db2 `VECTOR_DISTANCE` search over `AQ.RULE_TEXT`, and checks that the nearest rules include the rule the procedure cited. Granite 4.0 micro writes two sentences. Code rejects the text and stores a template instead if it contains a number not in the evidence, advice or prediction words, or a CPCB category that does not match the AQI.
7. **Ask.** `src/ask.py` refuses forecasts, health advice and blame questions before any model call. Otherwise Granite writes one SQL statement; `sqlglot` must parse it as a single `SELECT` over `AQ.V_DAY` / `AQ.V_CHECK` only, and a row cap is added. Db2 then runs it as `AQREADER`, a user whose only privileges are `CONNECT` and `SELECT` on those two views, so even a query that slipped past the parser cannot read or change anything else.

## Why these Db2 features

| Feature | Where | Why it is needed here |
|---|---|---|
| Range partitioning by month | `AQ.READING` | 3.27M rows for four months; audits read one day at a time |
| System-period temporal table | `AQ.READING` | Government feeds get revised; an audit must be able to show what the data said when it was judged |
| MERGE | `sql/03_merge.sql` | Idempotent reloads; only changed values create history |
| SQL PL procedures and a function | `sql/04_audit.sql` | The CPCB method runs next to the data, the same way for the app, the tests and the evaluation |
| Window functions | `BUILD_HOURLY` | Stuck runs and jumps are sequence properties, not row properties |
| Declared global temporary table | `COMPUTE_AQI_AUDITED` | Per-call working set without touching shared tables |
| `FINAL TABLE (INSERT ...)` | `COMPUTE_AQI_AUDITED` | Gets the new run id in one statement |
| Triggers raising SQLSTATE | ledger tables | Evidence cannot be edited after the fact, even by the app's own user |
| `VECTOR(768, FLOAT32)` + `VECTOR_DISTANCE` | `AQ.RULE_TEXT` | Rule retrieval happens in Db2 and is cross-checked against the procedure's citation |
| Least-privilege authorization ID | `AQREADER` | The natural-language box is safe by database permission, not only by prompt |
| CHECK constraints | `AQ.VERDICT` | Only the three verdict states can exist |

## Runtime

`docker-compose.yml` starts Db2 Community Edition 12.1.5, Ollama 0.12.6 with the IBM Granite GGUF files from Docker Hub, a one-shot `setup` job (download models, build schema, load the 3-station sample, audit, embed rules) and the FastAPI app on port 8000. The public demo site is a static export of the full 34-station run (`scripts/export_snapshot.py`), so it works without a database.

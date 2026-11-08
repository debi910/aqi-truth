# AQI Truth

> **One-Line Pitch:** Delhi's air-quality dashboards print a number even when the monitors were blank, frozen or reporting impossible values. AQI Truth puts the official CPCB method inside IBM Db2, so Db2 checks every hour and **refuses to give an AQI when the data cannot support one**, with a tamper-proof evidence ledger for each decision.

- **Live demo:** https://debi910.github.io/aqi-truth/ (calls the hosted Db2 + Granite server when it is up; otherwise shows a clearly labelled export of the same run)
- **Demo video:** _to be added_
- **Code:** https://github.com/debi910/aqi-truth

![Verdict card: a plain average shows 175, Db2 says no AQI is computable](docs/screenshots/verdict.png)

---

## Table of Contents
- [Problem Statement](#problem-statement)
- [Solution Overview](#solution-overview)
- [Results on real data](#results-on-real-data)
- [IBM Db2 Integration](#ibm-db2-integration)
- [AI / LLM Architecture](#ai--llm-architecture)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Setup & Installation](#setup--installation)
- [Configuration](#configuration)
- [Running the Project](#running-the-project)
- [Testing & Verification](#testing--verification)
- [Screenshots & Demo](#screenshots--demo)
- [What is real, what is simulated](#what-is-real-what-is-simulated)
- [Known Limitations & Future Roadmap](#known-limitations--future-roadmap)
- [Data sources and licences](#data-sources-and-licences)
- [Team Members & Credits](#team-members--credits)

---

## Problem Statement
- India's AQI is computed from Continuous Ambient Air Quality Monitoring Stations (CAAQMS). The CPCB method says a 24-hour average needs **at least 16 hours of data** and an AQI needs **at least 3 pollutants, one of them PM2.5 or PM10** ([CPCB](https://cpcb.nic.in/National-Air-Quality-Index/)).
- The Comptroller and Auditor General found that Delhi's AQI was not a reliable measure, partly because stations did not meet data-availability norms ([ThePrint on the CAG report, Apr 2025](https://theprint.in/india/delhis-air-was-toxic-for-56-of-the-days-in-last-5-years-aqi-no-reliable-measure-cag-report/2573600); [Newslaundry, Apr 2025](https://www.newslaundry.com/2025/04/01/delhi-air-quality-data-unreliable-cag-report-confirms-newslaundry-probe)). In November 2025 ThePrint reported **hundreds of hours of missing October PM2.5 data** at Delhi monitors around Diwali ([ThePrint, 8 Nov 2025](https://theprint.in/environment/delhis-aqi-monitors-didnt-go-blank-just-on-diwali-hundreds-of-hours-of-october-pm2-5-data-missing/2779540)).
- Apps, news tickers and many open-source dashboards average whatever values arrived. A day with 9 hours of data, or with a sensor stuck on one value, still gets a confident number and a colour.
- **Who it is for:** journalists and researchers checking an AQI claim, city officials who need to know which station-days to trust, and developers who republish CPCB data.
- **Why existing tools fall short:** they show the data; none of the ones we found records *whether the official rule allowed a number at all*, and why.

---

## Solution Overview
For every station and day, Db2 runs the CPCB method and returns one of three verdicts:

| Verdict | Meaning |
|---|---|
| `VALID` | Enough valid hours, nothing excluded. Same as the official method. |
| `SUSPECT` | Computable only after excluding impossible, stuck or jumping readings. |
| `NOT_COMPUTABLE` | The rules do not allow an AQI. Db2 stores the reason instead of a number. |

Next to each verdict it stores the **naive AQI** a plain-average dashboard would show, and an **evidence ledger** row for every pollutant and check (coverage, plausibility, stuck sensor, jump, sub-index, minimum pollutants), each with the observed value and the rule it cites. Ledger rows cannot be updated or deleted.

On top of that:
- **Explanations:** IBM Granite 4.0 micro writes a two-sentence explanation from the ledger. Code rejects it if it adds numbers, gives advice or names the wrong AQI category.
- **Question box:** ask in plain English ("Which stations had the most days with no computable AQI?"). Granite writes SQL, code checks it, and Db2 runs it as a user that can only read two views.
- **Web app:** a Delhi map of the 34 monitors, a 122-day strip per station, the verdict card (naive number struck through next to the Db2 stamp), the 24-hour grid, the evidence ledger, Granite's explanation, and the question box with a **Live / Recorded** switch. Live answers stream in: the page shows each stage (scope guard, Granite writing SQL token by token, SQL checker, Db2 as `AQREADER`) with a running timer.

---

## Results on real data
34 Delhi CAAQMS stations, 1 Sep to 31 Dec 2025, 1,872,155 fifteen-minute readings of the six AQI pollutants (weather channels are dropped at load), 4,148 station-days. MERGE load 28 s; full audit 2 min 40 s on a 4-core cloud container.

| Finding | Count |
|---|---|
| Station-days where CPCB rules allow **no AQI** | 247 |
| …of which a plain average **still shows a number** | **190** |
| …of those, shown as Very Poor or Severe | 67 |
| Station-days computable only after excluding bad readings (`SUSPECT`) | 893 |

Example: **Chandni Chowk, 23 Oct 2025.** From mid-afternoon the monitor reports only zeros. A plain average gives **175 (Moderate)**. Db2: only 2 pollutants had 16 valid hours and neither was a PM, so **no AQI is computable**.

**Fault-injection test** ([eval/fault_injection_results.md](eval/fault_injection_results.md)). We planted 198 known faults into real, clean pollutant-days (drawn from 9,781 available) and ran the same Db2 procedures on a separate schema:

| Planted fault | AQI Truth (Db2) | Min/max threshold rule | Plain average |
|---|---|---|---|
| Stuck sensor (6 h) | 33/33 | 0/33 | 0/33 |
| Spike ×10 (1 h) | 22/33 | 9/33 | 0/33 |
| Dropout (10 h) | 33/33 | 0/33 | 0/33 |
| Sentinel −9999 (3 h) | 33/33 | 33/33 | 0/33 |
| Zeros (4 h) | 33/33 | 0/33 | 0/33 |
| Unit scale ×1000 (4 h) | 33/33 | 33/33 | 0/33 |
| **Total caught** | **187/198 (94%)** | 75/198 (38%) | 0/198 |
| False alarms on 100 clean days | 0 | 0 | 0 |

**Question box** ([eval/ask_eval_results.md](eval/ask_eval_results.md)): Granite 4.0 micro answered **18 of 20** test questions correctly (same rows as a hand-written gold query). This is a development score: the prompt hints and the station-name fix were added after a first run scored 12/20 on the same questions. All **8 of 8** attack prompts (delete, update, read base tables or the catalog, forecasts, health advice, blame) were refused or answered from the two views only, and the verdict and reading row counts were unchanged afterwards.

**ThePrint comparison, stated honestly.** ThePrint counted 224 / 123 / 100 missing October PM2.5 hours at Chandni Chowk / Punjabi Bagh / Najafgarh from the CPCB portal. In the OpenAQ copy we count 200 / 138 / 78 hours with no row at all, or 245 / 138 / 82 hours with no plausible row. **We do not reproduce their numbers.** Two public copies of the same government data disagree, and "missing" depends on a validity rule that is not published. That gap is part of the problem this project addresses.

---

## IBM Db2 Integration
- **Db2 Edition & Environment:** Db2 Community Edition 12.1.5 (`icr.io/db2_community/db2:12.1.5.0`) in Docker.
- **Connector / Driver Used:** `ibm_db` / `ibm_db_dbi` (Python DB-API).
- **Database Schema / Data Models** (all in [`sql/`](sql)):
  - `AQ.READING`: range-partitioned by month, **system-period temporal** (`AQ.READING_HIST`), primary key `(STATION_ID, PARAM, TS)`.
  - `AQ.STAGE_READING` → `MERGE` (only changed values update, so revisions land in history).
  - `AQ.BREAKPOINT` (CPCB bands), `AQ.PLAUSIBLE` (limits, stuck hours, max jump), `AQ.SETTING` (16 h, 6 h, 3 pollutants).
  - `AQ.HOURLY`: per-hour coverage, plausibility, stuck-run and jump flags.
  - `AQ.VERDICT`, `AQ.EVIDENCE`, `AQ.EXPLANATION`: append-only, enforced by triggers raising `SQLSTATE 75001`.
  - `AQ.RULE_TEXT`: CPCB/CAG rule paragraphs with `VECTOR(768, FLOAT32)` embeddings.
  - Views `AQ.V_DAY`, `AQ.V_CHECK`; Db2 user `AQREADER` has `SELECT` on these two views and nothing else.
  - `AQ.ASK_LOG`: every question-box request (question, SQL, outcome, Granite and Db2 time), append-only by trigger; also the source of reusable SQL for repeated questions. `AQREADER` cannot read it.
- **Key Queries & Operations:**
  - `AQ.BUILD_HOURLY`: window functions (`LAG`, running `SUM` to number value runs, `COUNT() OVER` for run length) find stuck sensors and impossible jumps.
  - `AQ.COMPUTE_AQI_AUDITED`: SQL PL procedure with a declared global temporary table; 24 h averages with the 16-hour rule, highest 8 h window for O3/CO, `AQ.SUB_INDEX` function, three-pollutant rule; writes the verdict with `FINAL TABLE (INSERT …)` and one evidence row per check.
  - `AQ.AUDIT_RANGE`: audits every station-day in a range.
  - `VECTOR_DISTANCE(…, COSINE)` retrieves rule text inside Db2.
  - `FOR SYSTEM_TIME AS OF` shows what a reading was before a revision (covered by a test).

More detail and a diagram: [architecture.md](architecture.md).

---

## AI / LLM Architecture
- **Rule:** AI explains, code computes. Db2 makes every decision; the model never changes a verdict or a number.
- **Framework:** none; about 200 lines of Python (`src/explain.py`, `src/ask.py`, `src/llm.py`, `src/rules.py`).
- **Models:** IBM **Granite 4.0 micro** (text) and IBM **Granite embedding multilingual 278M** (768-dim), both run locally in Ollama from the GGUF files published on Docker Hub (`ai/granite-4.0-micro`, `ai/granite-embedding-multilingual`). No API key, no cost.
- **Grounded explanations:** the prompt holds only the verdict and its failed ledger rows. Db2 `VECTOR_DISTANCE` retrieves the nearest rule texts, and code checks that they include the rule the procedure cited (`VECTOR_AGREES` is stored). The reply is rejected, and a template stored instead, if it has any number not in the facts, words like "should", "safe", "health", "forecast" or "fraud", or a CPCB category that does not match.
- **Guarded questions:** out-of-scope questions (forecasts, health, blame) are refused before any model call. Granite writes SQL; `sqlglot` must parse it as exactly one `SELECT` over `AQ.V_DAY` / `AQ.V_CHECK`; a row cap is added; Db2 runs it as `AQREADER`.
- **Latency on a CPU:** Granite reads the ~470-token prompt in 16 s (dev container) to 26 s (the demo Codespace) and writes the SQL in about 4–6 s; Db2 answers in well under a second. Through the public link a new question took 32 s end to end, with the first SQL token at 28 s. A 30% shorter prompt cut 5 s but dropped accuracy from 18/20 to 10/20, so the prompt stays. What changed instead: the model is pinned in memory (a reload after idle cost 10–100 s), generation stops at the end of the statement, the SQL streams to the page as it is written, and an identical earlier question reuses its logged, already-checked SQL, which Db2 runs live in ~0.1 s (labelled on the page, with an "Ask Granite fresh" button). The app has Granite answer the sample questions once at startup, so they are instant for visitors.

---

## Tech Stack
- **Backend / Core:** Python 3.12, FastAPI, SQL PL in Db2
- **Database:** IBM Db2 Community Edition 12.1.5
- **AI:** IBM Granite 4.0 micro, IBM Granite embedding (Ollama 0.12.6)
- **Frontend / UI:** plain HTML/CSS/JS (IBM Plex fonts), static snapshot mode for GitHub Pages
- **Libraries & Tools:** ibm_db, sqlglot, requests, pytest, Docker Compose, Playwright (screenshots)

---

## Prerequisites
- Docker with Compose v2, about 8 GB RAM free and 10 GB disk (Db2 image plus 2.5 GB of Granite model files)
- Internet access to `icr.io`, Docker Hub and PyPI on first start
- Optional, for running tests outside Docker: Python 3.10+

---

## Setup & Installation

```bash
git clone https://github.com/debi910/aqi-truth && cd aqi-truth
cp .env.example .env          # then set your own two passwords
docker compose up -d --build  # first start: Db2 creates its database (5-10 min) and Granite downloads
docker compose logs -f setup  # wait for "rule texts embedded"
# then open http://localhost:8000
```

The `setup` job builds the schema, loads the shipped sample (3 stations, October 2025: Chandni Chowk, ITO, Anand Vihar), runs the audit and embeds the rule texts. On the sample, 91 of 93 station-days match the full run exactly; the other two (31 Oct) differ by a few AQI points because the sample has no November hours.

**Hosted demo in GitHub Codespaces** (free, no card): on the repo page click **Code → Codespaces → Create codespace on main** (choose the 4-core machine). The stack starts by itself (`deploy/codespace_start.sh`, about 25 minutes the first time) and port 8000 is made public. Some networks block `*.github.dev`, so the script also opens a free Cloudflare quick tunnel (no account) as a second route; the `keep-demo-alive` workflow publishes its address on the `endpoint` branch and the Pages site uses whichever route answers first. The workflow (`deploy/keepalive_runner.sh`) keeps the Codespace up through the judging window as a chain of ~5.5-hour runs (GitHub's cron fires unreliably, so it only restarts the chain), and stops it outside the window so the free hours are not wasted.

**Hosted demo on a VM** (Ubuntu, 8 GB RAM, ports 80/443 open, a public DNS name):
```bash
curl -fsSL https://raw.githubusercontent.com/debi910/aqi-truth/main/deploy/vm_setup.sh | sudo DOMAIN=<vm-dns-name> bash
```
It installs Docker, generates passwords, starts Db2, Granite, the app and Caddy (HTTPS), then loads all 34 stations.

**Full dataset** (34 stations, Sep–Dec 2025):
```bash
python scripts/fetch_openaq.py data/raw 2025 09,10,11,12
docker compose run --rm -v "$PWD/data/raw:/app/data/raw" setup python src/load.py data/raw 2025-09-01 2025-12-31
```

---

## Configuration
```bash
cp .env.example .env
```
| Variable | Purpose |
|---|---|
| `DB2_PASSWORD` | password of the Db2 instance owner `db2inst1` |
| `DB2_READER_PASSWORD` | password of `aqreader`, the read-only user for the question box |
| `DB2_HOST`, `DB2_PORT`, `DB2_DATABASE` | where Db2 runs (defaults suit Compose) |
| `OLLAMA_URL`, `LLM_MODEL`, `EMBED_MODEL` | local Granite models |

> **Security Warning:** never commit `.env`. `.env.example` holds placeholders only.

---

## Running the Project
- App and API: `docker compose up -d`, then http://localhost:8000
- Audit a range: `CALL AQ.AUDIT_RANGE('2025-10-01', '2025-10-31')`
- One station-day: `CALL AQ.COMPUTE_AQI_AUDITED(11603, '2025-10-23', ?)`
- Explain a run: `python src/explain.py <RUN_ID>`
- Ask: `python src/ask.py "Which stations had the most days with no computable AQI?"`
- Rebuild the static site: `python scripts/export_snapshot.py`

---

## Testing & Verification
```bash
pip install -r requirements.txt
set -a; . ./.env; set +a; export DB2_HOST=localhost OLLAMA_URL=http://localhost:11434
pytest tests/                      # 26 tests; the Db2 ones skip if DB2_PASSWORD is unset
python eval/fault_injection.py     # rebuilds schema AQE and plants 198 faults
python eval/ask_eval.py            # 20 gold questions + 8 attack prompts (18/20, 8/8)
```
The tests run against a real Db2, not mocks. They check: CPCB sub-index values; the Chandni Chowk refusal end to end; that `UPDATE`/`DELETE` on the ledger fail with `75001`; that `AQREADER` is denied `AQ.READING`, `AQ.VERDICT` and `AQ.EVIDENCE`; that a revised reading is still visible `FOR SYSTEM_TIME AS OF`; that an explanation with an invented number is rejected; and that the SQL guard blocks writes, joins to base tables, catalog reads and stacked statements.

---

## Screenshots & Demo
- **Live Demo Link:** https://debi910.github.io/aqi-truth/ — talks to the live Db2 + Granite server when it is up (green "Live" pill; during judging it is kept up), otherwise falls back to a clearly labelled read-only export of the same run.
- **Demo Video Link:** _to be added_

| | |
|---|---|
| ![Hour grid](docs/screenshots/hour-grid.png) | 24 hours × 6 pollutants for Chandni Chowk, 23 Oct 2025. Red: implausible values (zeros). |
| ![Evidence ledger](docs/screenshots/evidence-ledger.png) | Append-only evidence rows, each with the rule and its source. |
| ![Calendar](docs/screenshots/calendar.png) | 34 stations × 122 days, coloured by verdict. |

---

## What is real, what is simulated
| Part | Status |
|---|---|
| Station readings, Sep–Dec 2025 | **Real**: CPCB CAAQMS data as archived by OpenAQ |
| CPCB breakpoints, 16-hour, 8-hour and 3-pollutant rules | **Real**: from the CPCB AQI method |
| Plausibility limits, stuck hours, max jump | **Our engineering choice**, listed in `sql/02_reference.sql` |
| Faults in the fault-injection test | **Simulated**, planted into real clean days |
| Naive AQI | **Our model** of a plain-average dashboard, not a copy of any specific app |
| ThePrint / CAG figures | **Quoted** with links; not reproduced |

---

## Known Limitations & Future Roadmap
- **Units:** OpenAQ labels NO2, SO2 and CO as "ppb", but the values match CPCB's native units (µg/m³, CO in mg/m³), so we treat them as CPCB units. If that assumption is wrong for a station, its gaseous sub-indices are off.
- **15-minute rows:** the OpenAQ copy repeats each hourly value as four 15-minute rows; we bucket by the hour they start in and count an hour as present with one plausible row. Different choices change "missing hour" counts (see the ThePrint comparison).
- **No official ground truth** of which station-days CPCB itself rejected; the fault-injection test measures detection on planted faults, not on real failures.
- **Revisions:** the temporal table records revisions on reload, but we have only one snapshot of the archive, so no real revisions are shown yet.
- **Question box** uses a small local model on CPU: a new question takes about 20–35 s, and it can misread questions (see the eval). Wrong answers are still read-only and limited to the two views.
- **Hosting** is a free GitHub Codespace plus a Cloudflare quick tunnel; neither has an uptime guarantee.
- **Next:** daily ingestion so revisions are captured as they happen, the other Indian cities in the same archive, and a public "refusal feed" newsrooms can embed.

---

## Data sources and licences
- Air-quality data: CPCB CAAQMS via the [OpenAQ public archive](https://openaq-data-archive.s3.amazonaws.com) (OpenAQ data is CC BY 4.0). `data/sample/` holds three station-months from it.
- AQI method: [CPCB National Air Quality Index](https://cpcb.nic.in/National-Air-Quality-Index/).
- Reporting: ThePrint and Newslaundry articles linked above, quoted in `data/rules.json`.
- Models: IBM Granite 4.0 micro and Granite embedding (Apache 2.0).
- Map outline: Delhi boundary by [DataMeet India](https://github.com/datameet/Municipal_Spatial_Data) (CC BY 4.0), in `data/geo/`. Icons drawn after Lucide (ISC).

---

## Team Members & Credits
| Name | GitHub Handle | Role / Contribution |
|---|---|---|
| Debi Prasad Samal | [@debi910](https://github.com/debi910) | Solo entrant: idea, Db2 design, build, evaluation |

Built with help from Claude (Anthropic) as a coding assistant; all numbers come from the code and data in this repository.

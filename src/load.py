"""One-command setup: build the Db2 schema, load OpenAQ CSVs, MERGE, run the audit, embed rule texts.
Usage: python src/load.py RAW_DIR FROM_DAY TO_DAY [--schema AQ] [--no-embed]
Example (sample shipped in the repo): python src/load.py data/sample 2025-10-01 2025-10-31"""
import argparse, csv, os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(__file__))
from db import connect, run_script
import prepare

ROOT = os.path.join(os.path.dirname(__file__), "..")
POLLUTANTS = {"pm25", "pm10", "no2", "so2", "o3", "co"}
SCRIPTS = ["00_tablespace.sql", "01_schema.sql", "02_reference.sql", "04_audit.sql", "05_views.sql"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw"); ap.add_argument("day_from"); ap.add_argument("day_to")
    ap.add_argument("--schema", default="AQ"); ap.add_argument("--no-embed", action="store_true")
    a = ap.parse_args()
    s = a.schema.upper()
    conn = connect(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM SYSCAT.SCHEMATA WHERE SCHEMANAME = ?", (s,))
    if cur.fetchone()[0]:
        print(f"schema {s} exists: dropping it"); cur.callproc("SYSPROC.ADMIN_DROP_SCHEMA", (s, None, "ERRSCHEMA", "ERRTABLE")); conn.commit()
    for f in SCRIPTS:
        try:
            run_script(conn, os.path.join(ROOT, "sql", f), schema=None if s == "AQ" else s)
        except Exception as e:
            if f == "00_tablespace.sql" and "SQL0601N" in str(e): conn.rollback(); continue   # tablespace already there
            raise
    t = time.time()
    out = tempfile.mkdtemp(); prepare.main(a.raw, out)
    with open(os.path.join(out, "stations.del")) as fh:
        for r in csv.reader(fh):
            cur.execute(f"INSERT INTO {s}.STATION VALUES (?,?,?,?,?)", (int(r[0]), r[1], r[2] or None, r[3], r[4]))
    batch = []
    with open(os.path.join(out, "readings.del")) as fh:
        for r in csv.reader(fh):
            if r[1] not in POLLUTANTS: continue        # weather channels are not part of the AQI
            # ibm_db sizes string parameters from the first row of a batch, so pad to fixed widths
            batch.append((int(r[0]), r[1].ljust(4), r[2], float(r[3]) if r[3] else None, r[4][:10].ljust(10)))
            if len(batch) == 20000:
                cur.executemany(f"INSERT INTO {s}.STAGE_READING VALUES (?, RTRIM(CAST(? AS VARCHAR(12))), ?, ?, RTRIM(CAST(? AS VARCHAR(10))))", batch); batch = []
    if batch: cur.executemany(f"INSERT INTO {s}.STAGE_READING VALUES (?, RTRIM(CAST(? AS VARCHAR(12))), ?, ?, RTRIM(CAST(? AS VARCHAR(10))))", batch)
    conn.commit()
    run_script(conn, os.path.join(ROOT, "sql", "03_merge.sql"), schema=None if s == "AQ" else s)
    cur.execute(f"SELECT COUNT(*) FROM {s}.READING"); print(f"{cur.fetchone()[0]} readings merged in {time.time()-t:.0f}s")
    t = time.time()
    cur.callproc(f"{s}.BUILD_HOURLY", (f"{a.day_from} 00:00:00", f"{a.day_to} 23:59:59")); conn.commit()
    cur.callproc(f"{s}.AUDIT_RANGE", (a.day_from, a.day_to)); conn.commit()
    cur.execute(f"SELECT STATUS, COUNT(*) FROM {s}.V_DAY GROUP BY STATUS ORDER BY 1")
    print(f"audit done in {time.time()-t:.0f}s:", dict(cur.fetchall()))
    if not a.no_embed and s == "AQ":
        import requests, rules
        for _ in range(120):            # the Ollama container registers the Granite models after they download
            try:
                if any(m["name"].startswith(rules.EMBED_MODEL) for m in requests.get(rules.OLLAMA + "/api/tags", timeout=5).json()["models"]): break
            except Exception: pass
            time.sleep(5)
        rules.load_rules(os.path.join(ROOT, "data", "rules.json")); print("rule texts embedded")

if __name__ == "__main__":
    main()

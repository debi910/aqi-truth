"""AQI Truth web API (FastAPI). Serves the page in web/ and reads everything from Db2."""
import datetime as dt, os, sys
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
sys.path.insert(0, os.path.dirname(__file__))
from db import connect, rows
import explain as ex, ask as asker

WEB = os.path.join(os.path.dirname(__file__), "..", "web")
app = FastAPI(title="AQI Truth")
_conn = None
def conn():
    global _conn
    if _conn is None: _conn = connect()
    return _conn

PARAMS = ["pm25", "pm10", "no2", "so2", "o3", "co"]

@app.get("/api/stations")
def stations():
    return [dict(id=r[0], name=r[1], operator=r[2]) for r in rows(conn(),
        "SELECT STATION_ID, NAME, OPERATOR FROM AQ.STATION WHERE STATION_ID <> 8118 ORDER BY NAME")]

@app.get("/api/calendar")
def calendar():
    rs = rows(conn(), "SELECT STATION_ID, DAY, STATUS, AQI, NAIVE_AQI FROM AQ.V_DAY WHERE STATION_ID <> 8118 ORDER BY STATION_ID, DAY")
    return [dict(s=r[0], d=str(r[1]), st=r[2][0], a=r[3], n=r[4]) for r in rs]

@app.get("/api/stats")
def stats():
    r = rows(conn(), """SELECT COUNT(*), SUM(CASE WHEN STATUS='NOT_COMPUTABLE' THEN 1 ELSE 0 END),
        SUM(CASE WHEN STATUS='NOT_COMPUTABLE' AND NAIVE_AQI IS NOT NULL THEN 1 ELSE 0 END),
        SUM(CASE WHEN STATUS='NOT_COMPUTABLE' AND NAIVE_AQI > 300 THEN 1 ELSE 0 END),
        SUM(CASE WHEN STATUS='SUSPECT' THEN 1 ELSE 0 END),
        (SELECT COUNT(*) FROM AQ.READING WHERE STATION_ID <> 8118) FROM AQ.V_DAY""")[0]
    return dict(station_days=r[0], not_computable=r[1], shown_anyway=r[2], shown_anyway_very_poor=r[3], suspect=r[4], readings=r[5])

def day_payload(station: int, day: str, with_llm: bool):
    d = dt.date.fromisoformat(day)
    v = rows(conn(), "SELECT RUN_ID, STATION, OPERATOR, STATUS, AQI, NAIVE_AQI, PROMINENT, VALID_PARAMS, REASON FROM AQ.V_DAY WHERE STATION_ID=? AND DAY=?", (station, d))
    if not v: raise HTTPException(404, "no audit for that station and day")
    run, name, op, status, aqi, naive, prom, nparams, reason = v[0]
    ev = rows(conn(), """SELECT E.PARAM, E.CHECK_CODE, E.OBSERVED, E.PASSED, E.RULE_REF, R.SOURCE, R.URL
                          FROM AQ.EVIDENCE E LEFT JOIN AQ.RULE_TEXT R ON R.RULE_REF = E.RULE_REF
                         WHERE E.RUN_ID=? ORDER BY E.PASSED, E.PARAM, E.CHECK_CODE""", (run,))
    start = dt.datetime.combine(d, dt.time())
    hrs = rows(conn(), """SELECT PARAM, HOUR(HR - 1 SECOND), N_RAW, N_OK, AVG_OK, AVG_ALL, FLAT, JUMP, IS_VALID
                            FROM AQ.HOURLY WHERE STATION_ID=? AND HR > ? AND HR <= ?""", (station, start, start + dt.timedelta(days=1)))
    grid = {p: [None] * 24 for p in PARAMS}
    for p, h, nraw, nok, aok, aall, flat, jump, valid in hrs:
        if p in grid:
            grid[p][h] = dict(v=None if aok is None else round(aok, 1), raw=None if aall is None else round(aall, 1),
                              k="ok" if valid else ("stuck" if flat else ("bad" if nok == 0 else "short")), j=bool(jump))
    expl = rows(conn(), "SELECT TEXT, MODEL, RULE_REFS, VECTOR_AGREES FROM AQ.EXPLANATION WHERE RUN_ID=? ORDER BY CREATED_AT DESC FETCH FIRST 1 ROW ONLY", (run,))
    if not expl and with_llm:
        e = ex.explain(conn(), run); expl = [(e["text"], e["model"], ",".join(e["cited"]), int(e["vector_agrees"]))]
    return dict(run_id=run, station=name, operator=op, day=day, status=status, aqi=aqi, naive_aqi=naive, prominent=prom,
                valid_params=nparams, reason=reason, grid=grid,
                evidence=[dict(param=r[0], check=r[1], observed=r[2], passed=bool(r[3]), rule=r[4], source=r[5], url=r[6]) for r in ev],
                explanation=dict(text=expl[0][0], model=expl[0][1], rules=expl[0][2], vector_agrees=bool(expl[0][3])) if expl else None)

@app.get("/api/day")
def day(station: int, day: str, llm: bool = True):
    return day_payload(station, day, llm)

class Q(BaseModel):
    question: str

@app.post("/api/ask")
def ask_q(q: Q):
    if len(q.question) > 300: raise HTTPException(400, "question too long")
    r = asker.ask(q.question)
    if r.get("rows"):
        r["rows"] = [[str(c) if isinstance(c, (dt.date, dt.datetime)) else c for c in row] for row in r["rows"]]
    return r

@app.get("/")
def index():
    return FileResponse(os.path.join(WEB, "index.html"))
app.mount("/", StaticFiles(directory=WEB), name="web")

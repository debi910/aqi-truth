"""Read-only natural-language questions over the audited views.
Granite writes one SELECT; code checks it (sqlglot: single SELECT, only AQ.V_DAY / AQ.V_CHECK, row cap);
Db2 runs it as AQREADER, an authorization ID that can read those two views and nothing else."""
import os, re, sys
import sqlglot
from sqlglot import exp
sys.path.insert(0, os.path.dirname(__file__))
from llm import generate
import ibm_db, ibm_db_dbi

ALLOWED = {"V_DAY", "V_CHECK"}
OUT_OF_SCOPE = re.compile(r"\b(predict\w*|forecast\w*|tomorrow|next week|will it|will the|should i|safe|unsafe|health\w*|child\w*|kids?|mask|fraud|who is responsible|responsible for)\b", re.I)
SCHEMA = """Db2 views (schema AQ):
AQ.V_DAY(STATION VARCHAR, OPERATOR VARCHAR, DAY DATE, STATUS VARCHAR -- 'VALID'|'SUSPECT'|'NOT_COMPUTABLE',
         AQI SMALLINT -- audited AQI, NULL when NOT_COMPUTABLE, NAIVE_AQI SMALLINT -- plain average, PROMINENT VARCHAR, VALID_PARAMS SMALLINT, REASON VARCHAR)
AQ.V_CHECK(STATION VARCHAR, DAY DATE, PARAM VARCHAR -- pm25|pm10|no2|so2|o3|co|ALL, CHECK_CODE VARCHAR -- COVERAGE|PLAUSIBLE|STUCK|JUMP|SUBINDEX|MIN_PARAMS,
           OBSERVED VARCHAR, PASSED SMALLINT -- 1 passed 0 failed, RULE_REF VARCHAR)
Station names look like 'Chandni Chowk, Delhi - IITM' (always match with LIKE '%Chandni Chowk%'). Data covers 2025-09-01 to 2025-12-31.
AQI is NULL on NOT_COMPUTABLE days: add AQI IS NOT NULL when ranking by AQI. A failed check has PASSED = 0."""
EXAMPLES = """Q: Which stations had the most days with no computable AQI?
SQL: SELECT STATION, COUNT(*) AS DAYS FROM AQ.V_DAY WHERE STATUS = 'NOT_COMPUTABLE' GROUP BY STATION ORDER BY DAYS DESC
Q: On Diwali 2025 (21 October) which stations were suspect?
SQL: SELECT STATION, AQI, NAIVE_AQI FROM AQ.V_DAY WHERE DAY = '2025-10-21' AND STATUS = 'SUSPECT'
Q: How many jump checks failed at Okhla in November?
SQL: SELECT COUNT(*) FROM AQ.V_CHECK WHERE STATION LIKE '%Okhla%' AND CHECK_CODE = 'JUMP' AND PASSED = 0 AND DAY BETWEEN '2025-11-01' AND '2025-11-30'"""

def reader():
    dsn = (f"DATABASE={os.getenv('DB2_DATABASE','AQIDB')};HOSTNAME={os.getenv('DB2_HOST','localhost')};PORT={os.getenv('DB2_PORT','50000')};"
           f"PROTOCOL=TCPIP;UID={os.getenv('DB2_READER_USER','aqreader')};PWD={os.environ['DB2_READER_PASSWORD']};")
    return ibm_db_dbi.Connection(ibm_db.connect(dsn, "", ""))

class Refused(Exception):
    pass

def check_sql(sql):
    sql = sql.strip().rstrip(";")
    # Models often write LIMIT n; Db2 uses FETCH FIRST n ROWS ONLY.
    sql = re.sub(r"\s+LIMIT\s+(\d+)\s*$", r" FETCH FIRST \1 ROWS ONLY", sql, flags=re.I)
    sql = re.sub(r"--[^\n]*", "", sql)
    # Db2 sorts NULL as the highest value; an AQI ranking must not put refused (NULL) days first.
    sql = re.sub(r"\b((?:\w+\.)?(?:NAIVE_)?AQI|MAX\(\s*(?:\w+\.)?AQI\s*\))\s+DESC\b(?!\s+NULLS)", r"\1 DESC NULLS LAST", sql, flags=re.I)
    # Users type short names ("ITO", "Punjabi Bagh"); stored names are longer, so exact matches become LIKE.
    sql = re.sub(r"\bSTATION\s*=\s*'([^',]+)[^']*'", lambda m: f"STATION LIKE '%{m.group(1).strip()}%'", sql, flags=re.I)
    try:
        trees = sqlglot.parse(re.sub(r"FETCH\s+FIRST\s+\d+\s+ROWS\s+ONLY", "", sql, flags=re.I))
    except Exception as e:
        raise Refused(f"could not parse the generated SQL ({e.__class__.__name__})")
    if len(trees) != 1 or not isinstance(trees[0], exp.Select):
        raise Refused("only a single SELECT is allowed")
    tables = {t.name.upper() for t in trees[0].find_all(exp.Table)}
    if not tables or not tables <= ALLOWED or any((t.db or "").upper() not in ("AQ", "") for t in trees[0].find_all(exp.Table)):
        raise Refused(f"query touches tables outside the audited views: {sorted(tables - ALLOWED) or sorted(tables)}")
    if not re.search(r"FETCH\s+FIRST", sql, re.I):
        sql += " FETCH FIRST 50 ROWS ONLY"
    return sql

def ask(question, conn=None):
    if OUT_OF_SCOPE.search(question):
        return dict(refused=True, why="AQI Truth only answers questions about what the monitors recorded and how the audit judged it. "
                                      "It does not predict air quality or give health advice.")
    raw = generate(f"{SCHEMA}\n\n{EXAMPLES}\n\nWrite one Db2 SELECT for the question. Reply with SQL only, no explanation.\nQ: {question}\nSQL:",
                   max_tokens=200, system="You translate questions into a single read-only Db2 SQL SELECT over the given views.")
    sql = re.sub(r"^```\w*|```$", "", raw.strip(), flags=re.M).strip().split("\n\n")[0]
    sql = re.sub(r"^SQL:\s*", "", sql)
    try:
        sql = check_sql(sql)
    except Refused as e:
        return dict(refused=True, why=f"The generated query was blocked: {e}.", sql=sql)
    conn = conn or reader()
    cur = conn.cursor()
    try:
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        data = [list(r) for r in cur.fetchall()]
    except Exception as e:
        return dict(refused=True, why=f"Db2 rejected the query: {str(e)[-160:]}", sql=sql)
    return dict(refused=False, sql=sql, columns=cols, rows=data)

if __name__ == "__main__":
    print(ask(" ".join(sys.argv[1:])))

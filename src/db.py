"""Tiny Db2 helper (ibm_db). Connection settings come from environment variables."""
import os, re
import ibm_db, ibm_db_dbi

def connect():
    dsn = (f"DATABASE={os.getenv('DB2_DATABASE','AQIDB')};HOSTNAME={os.getenv('DB2_HOST','localhost')};"
           f"PORT={os.getenv('DB2_PORT','50000')};PROTOCOL=TCPIP;UID={os.getenv('DB2_USER','db2inst1')};"
           f"PWD={os.environ['DB2_PASSWORD']};")
    return ibm_db_dbi.Connection(ibm_db.connect(dsn, "", ""))

def run_script(conn, path, schema=None):
    """Run a '@'-terminated SQL script, optionally rewriting schema AQ -> `schema`."""
    sql = open(path, encoding="utf-8").read()
    if schema:
        sql = re.sub(r"\bAQ\.", schema + ".", sql).replace("CREATE SCHEMA AQ@", f"CREATE SCHEMA {schema}@")
    cur = conn.cursor()
    for stmt in [s.strip() for s in sql.split("@")]:
        body = "\n".join(l for l in stmt.splitlines() if not l.strip().startswith("--")).strip()
        if body:
            cur.execute(stmt)
    conn.commit()

def rows(conn, sql, params=()):
    cur = conn.cursor(); cur.execute(sql, params); return cur.fetchall()

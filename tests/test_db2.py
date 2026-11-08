"""Run against a real Db2 loaded with the Sep-Dec 2025 data (or the sample in data/sample)."""
import datetime as dt, os
import pytest
import ibm_db_dbi
from conftest import needs_db2

pytestmark = needs_db2

def one(conn, sql, params=()):
    cur = conn.cursor(); cur.execute(sql, params); return cur.fetchone()

def test_sub_index_matches_cpcb_breakpoints(conn):
    # CPCB PM2.5: 0-30 -> 0-50, 31-60 -> 51-100, 61-90 -> 101-200
    assert one(conn, "VALUES AQ.SUB_INDEX('pm25', 30)")[0] == 50
    assert one(conn, "VALUES AQ.SUB_INDEX('pm25', 60)")[0] == 100
    assert one(conn, "VALUES AQ.SUB_INDEX('pm25', 0)")[0] == 0

def test_golden_path_refusal_chandni_chowk_23_oct(conn):
    """Monitor sent only implausible zeros after 14:00: CPCB rules give no AQI, a plain average still gives one."""
    cur = conn.cursor()
    out = cur.callproc("AQ.COMPUTE_AQI_AUDITED", (11603, dt.date(2025, 10, 23), 0))
    run_id = out[2]
    status, aqi, naive = one(conn, "SELECT STATUS, AQI, NAIVE_AQI FROM AQ.VERDICT WHERE RUN_ID = ?", (run_id,))
    assert status == "NOT_COMPUTABLE" and aqi is None and naive is not None
    failed = one(conn, "SELECT COUNT(*) FROM AQ.EVIDENCE WHERE RUN_ID = ? AND PASSED = 0", (run_id,))[0]
    assert failed >= 1
    conn.commit()

@pytest.mark.parametrize("stmt", ["UPDATE AQ.EVIDENCE SET PASSED = 1 WHERE PASSED = 0",
                                  "DELETE FROM AQ.EVIDENCE",
                                  "UPDATE AQ.VERDICT SET AQI = 50"])
def test_ledger_is_append_only(conn, stmt):
    cur = conn.cursor()
    with pytest.raises(Exception) as e:
        cur.execute(stmt)
    conn.rollback()
    assert "75001" in str(e.value)

def test_reader_can_only_see_the_two_views():
    from ask import reader
    r = reader(); cur = r.cursor()
    cur.execute("SELECT COUNT(*) FROM AQ.V_DAY"); assert cur.fetchone()[0] > 0
    for t in ("AQ.READING", "AQ.VERDICT", "AQ.EVIDENCE"):
        with pytest.raises(Exception) as e:
            cur.execute(f"SELECT COUNT(*) FROM {t}")
        assert "SQL0551N" in str(e.value) or "42501" in str(e.value)
    r.close()

def test_reading_keeps_history_when_a_value_is_revised(conn):
    """System-period temporal table: an overwritten reading stays queryable FOR SYSTEM_TIME AS OF."""
    cur = conn.cursor()
    sid, param, ts, val = one(conn, "SELECT STATION_ID, PARAM, TS, VALUE FROM AQ.READING FETCH FIRST 1 ROW ONLY")
    before = one(conn, "VALUES CURRENT TIMESTAMP")[0]
    cur.execute("UPDATE AQ.READING SET VALUE = VALUE + 1 WHERE STATION_ID=? AND PARAM=? AND TS=?", (sid, param, ts))
    old = one(conn, "SELECT VALUE FROM AQ.READING FOR SYSTEM_TIME AS OF ? WHERE STATION_ID=? AND PARAM=? AND TS=?",
              (before, sid, param, ts))
    conn.rollback()
    assert float(old[0]) == float(val)

def test_explanation_guard_rejects_invented_numbers(conn, monkeypatch):
    import explain
    run_id = one(conn, "SELECT MAX(RUN_ID) FROM AQ.VERDICT WHERE STATION_ID = 11603 AND DAY = '2025-10-23'")[0]
    monkeypatch.setattr(explain, "nearest_rules", lambda c, t, k=3: [("CPCB-24H-16", "rule text")])
    monkeypatch.setattr(explain, "generate", lambda *a, **k: "The AQI was 999 and people should stay indoors.")
    out = explain.explain(conn, run_id)
    assert out["model"].startswith("template") and "999" not in out["text"]

def test_question_log_is_append_only_and_hidden_from_reader(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM AQ.ASK_LOG"); assert cur.fetchone()[0] >= 0
    with pytest.raises(Exception) as e:
        cur.execute("DELETE FROM AQ.ASK_LOG")
    conn.rollback()
    assert "75001" in str(e.value)
    from ask import reader
    with pytest.raises(Exception):
        reader().cursor().execute("SELECT COUNT(*) FROM AQ.ASK_LOG")

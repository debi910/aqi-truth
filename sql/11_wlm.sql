-- Db2 workload management for the question box. Add-only; undo: sql/11_undo.sql.
-- Every connection as AQREADER (the ID that runs Granite-written SQL) is mapped to its own service class, and Db2
-- itself stops an activity there that returns more than 5,000 rows or runs longer than a minute (SQL4712N).
-- These sit behind the app's own limits (sqlglot checks, FETCH FIRST 50 ROWS, a 10 s client timeout), so a
-- question-box query never reaches them; they hold even for a client that skips those limits.
CREATE SERVICE CLASS AQ_QBOX@
CREATE WORKLOAD AQ_QBOX_WL SESSION_USER ('AQREADER') SERVICE CLASS AQ_QBOX@
GRANT USAGE ON WORKLOAD AQ_QBOX_WL TO USER AQREADER@
CREATE THRESHOLD AQ_QBOX_ROWS FOR SERVICE CLASS AQ_QBOX ACTIVITIES ENFORCEMENT DATABASE
  WHEN SQLROWSRETURNED > 5000 STOP EXECUTION@
CREATE THRESHOLD AQ_QBOX_TIME FOR SERVICE CLASS AQ_QBOX ACTIVITIES ENFORCEMENT DATABASE
  WHEN ACTIVITYTOTALTIME > 1 MINUTE STOP EXECUTION@

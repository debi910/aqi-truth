-- Read-only views for the app and the natural-language question box.
CREATE OR REPLACE VIEW AQ.V_DAY AS
SELECT V.RUN_ID, V.STATION_ID, S.NAME AS STATION, S.OPERATOR, V.DAY, V.STATUS, V.AQI, V.NAIVE_AQI,
       V.PROMINENT, V.VALID_PARAMS, V.REASON
  FROM AQ.VERDICT V JOIN AQ.STATION S ON S.STATION_ID = V.STATION_ID
 WHERE V.RUN_ID = (SELECT MAX(X.RUN_ID) FROM AQ.VERDICT X WHERE X.STATION_ID = V.STATION_ID AND X.DAY = V.DAY)
   -- The US Embassy monitor measures PM2.5 only, so CPCB's 3-pollutant AQI never applies to it; it is kept in
   -- AQ.READING but left out of the audited views so every count matches the 34 CAAQMS stations.
   AND S.STATION_ID <> 8118                       -- OpenAQ location 8118 = US Embassy, New Delhi@

CREATE OR REPLACE VIEW AQ.V_CHECK AS
SELECT D.STATION, D.DAY, E.PARAM, E.CHECK_CODE, E.OBSERVED, E.PASSED, E.RULE_REF
  FROM AQ.V_DAY D JOIN AQ.EVIDENCE E ON E.RUN_ID = D.RUN_ID@

-- Plain-language explanations written by the LLM, append-only like the evidence they explain.
CREATE TABLE AQ.EXPLANATION (
  RUN_ID     BIGINT NOT NULL REFERENCES AQ.VERDICT,
  MODEL      VARCHAR(60) NOT NULL,
  TEXT       VARCHAR(2000) NOT NULL,
  GROUNDED   SMALLINT NOT NULL,           -- 1 = every number in TEXT appears in the evidence
  RULE_REFS  VARCHAR(200) NOT NULL,
  VECTOR_AGREES SMALLINT NOT NULL,        -- 1 = vector search found the same rule the procedure cited
  CREATED_AT TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP,
  PRIMARY KEY (RUN_ID, CREATED_AT)
)@
CREATE TRIGGER AQ.EXPLANATION_NO_UPDATE NO CASCADE BEFORE UPDATE ON AQ.EXPLANATION
 FOR EACH ROW SIGNAL SQLSTATE '75001' SET MESSAGE_TEXT = 'Explanations are append-only'@

-- A separate Db2 authorization ID for the question box: it can read the audited views and nothing else.
GRANT CONNECT ON DATABASE TO USER AQREADER@
GRANT SELECT ON AQ.V_DAY TO USER AQREADER@
GRANT SELECT ON AQ.V_CHECK TO USER AQREADER@

# AQI Truth

**Delhi publishes an AQI even on days its monitors were mostly blank. IBM Db2 refuses to.**

Work in progress for IBM Db2Hack 2026. An audit layer over India's official air-quality monitoring data (CPCB CAAQMS, via the OpenAQ public archive) where IBM Db2 computes the official AQI method, enforces the 16-valid-hours rule, detects gaps, stuck sensors and silent revisions, and keeps a tamper-evident evidence ledger. The LLM only explains verdicts.

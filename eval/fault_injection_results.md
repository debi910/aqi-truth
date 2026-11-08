# Fault-injection results

Faults are simulated; the days they are planted into are real.

| Planted fault | Cases | AQI Truth (Db2) flags | Min/max threshold flags | Plain average flags |
|---|---|---|---|---|
| Stuck | 33 | 33 (100%) | 0 (0%) | 0 (0%) |
| Spike | 33 | 22 (66%) | 9 (27%) | 0 (0%) |
| Dropout | 33 | 33 (100%) | 0 (0%) | 0 (0%) |
| Sentinel | 33 | 33 (100%) | 33 (100%) | 0 (0%) |
| Zero | 33 | 33 (100%) | 0 (0%) | 0 (0%) |
| Scale | 33 | 33 (100%) | 33 (100%) | 0 (0%) |
| No fault (false alarms) | 100 | 0 (0%) | 0 (0%) | 0 (0%) |

Faults caught: AQI Truth 187/198 (94%), threshold 75/198 (38%), plain average 0/198. False alarms on clean days: AQI Truth 0/100, threshold 0/100.
Clean real param-days available: 9781; seed 7.

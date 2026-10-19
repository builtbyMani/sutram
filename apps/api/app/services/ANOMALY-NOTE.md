# ANOMALY-NOTE.md — ANO-01 log-anomaly integration guide

Module: `apps/api/app/services/anomaly.py` (built & verified 2026-10-19; no wiring done)

## Exact public signature

```python
detect_log_anomalies(sessions, contamination=0.1, random_state=42)
# -> list[{"session", "score", "explanation", "features"}], sorted by score desc
```

- `sessions`: list of dicts, each with numeric `hour_of_day` (0–23),
  `failed_attempts` (int), `bytes_transferred` (float). Extra keys
  (session_id, user, …) pass through untouched inside `"session"`.
  Missing/non-numeric features → `ValueError` (fail loud, don't guess).
- `score`: `-decision_function`, so **higher = more anomalous**.
- `explanation`: top-2 deviating features vs the inlier profile, e.g.
  `"failed_attempts=40 (typical 1); hour_of_day=11 (typical 15)"`.
- Returns `[]` when fewer than `MIN_SESSIONS = 10` sessions are supplied
  (too little data to model — honest empty, not garbage).

Internals: `StandardScaler` → `IsolationForest(contamination=0.1,
random_state=42)`. Scaling is load-bearing: without it bytes_transferred
(millions) drowns out hour_of_day (0–23). Explanations use standardized
distance from the inlier median; features with |z| < 1 are not named.

## DB table the wiring phase must create

```sql
CREATE TABLE anomalies (
  id INTEGER PRIMARY KEY,
  artifact_id INTEGER REFERENCES artifacts(id),
  feature_json TEXT,      -- {"hour_of_day":..,"failed_attempts":..,"bytes_transferred":..}
  score REAL,             -- higher = more anomalous
  explanation TEXT,       -- human-readable, names contributing features
  created_ts TEXT          -- UTC ISO
);
```

## Wiring checklist

1. `POST /api/logs/{id}/anomalies`: load the log artifact, parse it into
   per-session dicts (parser is wiring-phase work — any auth/activity log
   with timestamps, failure counts, byte counts), call
   `detect_log_anomalies`, insert one `anomalies` row per flagged session
   (`feature_json` = the `features` dict, `score`, `explanation`).
2. Findings rule `login-anomaly`: one finding per anomaly row with
   `rule_or_model="isolation-forest"`, `confidence` derived from rank/score
   (suggestion: `min(0.95, 0.5 + score)` — score scale is data-dependent,
   calibrate on the fixture), `artifact_ids_json=[log artifact id]`,
   snippet = the explanation.
3. New pip dep: `scikit-learn==1.9.1` (verified version).

## Measured verification numbers (2026-10-19)

Fixture: 20 normal sessions (hours 8–17, 0–2 failed attempts, 1e5–5e6 bytes)
+ 3 planted anomalies. Result: **exactly 3/23 flagged, 0 false positives** —
- `anom-exfil` (8.7e9 bytes): score 0.152 —
  "bytes_transferred=8.7e+09 (typical 2.33688e+06); failed_attempts=0 (typical 1)"
- `anom-bruteforce` (40 fails): score 0.124 —
  "failed_attempts=40 (typical 1); hour_of_day=11 (typical 15)"
- `anom-night` (03:00): score 0.008 —
  "hour_of_day=3 (typical 15)"
- Recall 1.0 on planted anomalies; every explanation names the right
  driving feature; < 10 sessions → `[]`.

## Known limits

- Unsupervised: it flags *statistical* outliers, not confirmed malice —
  the finding description should say so.
- `contamination=0.1` assumes ~10% outlier rate; on tiny or homogeneous
  logs the flags are weak — the MIN_SESSIONS guard and the score ordering
  are the honesty mechanisms. Do not lower MIN_SESSIONS without a reason.
- Scores are not probabilities; don't present them as such in the UI —
  show rank + explanation, keep the raw score in provenance.

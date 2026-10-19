"""Log-session anomaly detection — ANO-01.

Scores per-session activity with an IsolationForest over
{hour_of_day, failed_attempts, bytes_transferred} and explains each flag by
naming the features that deviate most from the inlier profile.

Public API for the wiring phase:
    detect_log_anomalies(sessions, contamination=0.1, random_state=42)
        -> list[{"session", "score", "explanation", "features"}]

- `sessions`: list of dicts, each carrying at least the three feature keys
  (extra keys such as session_id / user pass through untouched inside
  "session").
- `score`: -decision_function, so HIGHER means more anomalous.
- `explanation`: names the top-2 contributing features with their values vs
  the inlier-typical values, e.g.
  "failed_attempts=40 (typical 0); hour_of_day=3 (typical 10)".
- Returns [] when fewer than MIN_SESSIONS sessions are supplied (too little
  data to model honestly).

Features are standardized before fitting — without that, bytes_transferred
(millions) would drown out hour_of_day (0-23) entirely.
"""

__all__ = ["FEATURES", "MIN_SESSIONS", "detect_log_anomalies"]

FEATURES = ("hour_of_day", "failed_attempts", "bytes_transferred")
MIN_SESSIONS = 10


def _as_feature_matrix(sessions):
    """Validate and extract the (n, 3) feature matrix."""
    X, missing = [], []
    for i, s in enumerate(sessions):
        row, row_ok = [], True
        for f in FEATURES:
            if f not in s:
                missing.append((i, f))
                row_ok = False
            else:
                try:
                    row.append(float(s[f]))
                except (TypeError, ValueError):
                    raise ValueError(
                        f"session {i}: feature {f!r} is not numeric: {s[f]!r}")
        if row_ok:
            X.append(row)
    if missing:
        bad = ", ".join(f"session {i} missing {f!r}" for i, f in missing[:5])
        raise ValueError(f"sessions missing required features: {bad}")
    return X


def _explain(point, inlier_median, inlier_std, top_k=2):
    """Name the top-k features by standardized deviation from inliers."""
    scored = []
    for f, v, med, sd in zip(FEATURES, point, inlier_median, inlier_std):
        z = abs(v - med) / (sd + 1e-9)
        scored.append((z, f, v, med))
    scored.sort(reverse=True)
    parts = []
    for z, f, v, med in scored[:top_k]:
        if z < 1.0:
            continue  # not meaningfully deviant; don't pad the explanation
        parts.append(f"{f}={v:g} (typical {med:g})")
    if not parts:  # degenerate: flagged but nothing stands out
        z, f, v, med = scored[0]
        parts.append(f"{f}={v:g} (typical {med:g})")
    return "; ".join(parts)


def detect_log_anomalies(sessions, contamination=0.1, random_state=42):
    """Flag anomalous log sessions. See module docstring for the contract."""
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    import numpy as np

    sessions = list(sessions)
    if len(sessions) < MIN_SESSIONS:
        return []

    X = np.asarray(_as_feature_matrix(sessions), dtype=float)
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)

    model = IsolationForest(contamination=contamination,
                            random_state=random_state)
    pred = model.fit_predict(Xs)          # -1 = anomaly, 1 = inlier
    scores = -model.decision_function(Xs)  # higher = more anomalous

    inlier_mask = pred == 1
    if np.any(inlier_mask):
        inlier_med = np.median(X[inlier_mask], axis=0)
        inlier_std = np.std(X[inlier_mask], axis=0)
    else:  # degenerate: everything flagged; fall back to global stats
        inlier_med = np.median(X, axis=0)
        inlier_std = np.std(X, axis=0)

    out = []
    for s, row, is_out, score in zip(sessions, X, pred == -1, scores):
        if not is_out:
            continue
        out.append({
            "session": s,
            "score": float(score),
            "explanation": _explain(row, inlier_med, inlier_std),
            "features": {f: float(v) for f, v in zip(FEATURES, row)},
        })
    out.sort(key=lambda d: d["score"], reverse=True)
    return out


# ----------------------------------------------------------------------------
# Self-test: 20 normal + 3 planted anomalies (fixture shape from the plan).
# ----------------------------------------------------------------------------

def _fixture_sessions(seed=7):
    import numpy as np
    rng = np.random.default_rng(seed)
    sessions = []
    for i in range(20):
        sessions.append({
            "session_id": f"normal-{i:02d}",
            "hour_of_day": int(rng.integers(8, 18)),
            "failed_attempts": int(rng.integers(0, 3)),
            "bytes_transferred": float(rng.uniform(1e5, 5e6)),
        })
    sessions.append({"session_id": "anom-night",
                     "hour_of_day": 3, "failed_attempts": 1,
                     "bytes_transferred": 2.1e6})          # 3 AM login
    sessions.append({"session_id": "anom-bruteforce",
                     "hour_of_day": 11, "failed_attempts": 40,
                     "bytes_transferred": 3.0e5})          # 40 failed attempts
    sessions.append({"session_id": "anom-exfil",
                     "hour_of_day": 14, "failed_attempts": 0,
                     "bytes_transferred": 8.7e9})          # huge transfer
    return sessions


def self_test():
    sessions = _fixture_sessions()
    flagged = detect_log_anomalies(sessions)
    flagged_ids = {f["session"]["session_id"] for f in flagged}
    expected = {"anom-night", "anom-bruteforce", "anom-exfil"}
    missing = expected - flagged_ids
    false_pos = flagged_ids - expected

    ok = True
    print(f"  flagged {len(flagged)}/{len(sessions)} sessions")
    for f in flagged:
        s = f["session"]
        print(f"    {s['session_id']}: score {f['score']:.3f} | "
              f"{f['explanation']}")
    good = not missing and len(false_pos) <= 2
    ok &= good
    if missing:
        print(f"  FAIL: missed planted anomalies: {sorted(missing)}")
    if len(false_pos) > 2:
        print(f"  FAIL: too many false positives: {sorted(false_pos)}")

    # explanations must name the right driving feature
    expl = {f["session"]["session_id"]: f["explanation"] for f in flagged}
    checks = [
        ("anom-night", "hour_of_day"),
        ("anom-bruteforce", "failed_attempts"),
        ("anom-exfil", "bytes_transferred"),
    ]
    for sid, feat in checks:
        good = sid in expl and feat in expl[sid]
        ok &= good
        print(f"  explanation for {sid} names {feat}: "
              f"{'OK' if good else 'FAIL'}")

    # too little data -> honest empty result, not garbage
    good = detect_log_anomalies(sessions[:5]) == []
    ok &= good
    print(f"  < MIN_SESSIONS returns []: {'OK' if good else 'FAIL'}")

    print("ANOMALY SELF-TEST", "PASSED" if ok else "FAILED")
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if self_test() else 1)

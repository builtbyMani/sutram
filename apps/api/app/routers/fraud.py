"""Phase 5 router: fraud signals, findings engine, audit trail, cited summaries.

Mounted by main.py as ``app.include_router(fraud.router)`` (see INTEGRATION-5.md).

Routes (exact contract per INTEGRATION-6.md — no aliases):
  POST /api/media/{id}/analyze   ELA + EXIF + deepfake score -> media_signals
  POST /api/media/{id}/pulse     rPPG pulse-liveness (FRD-03) -> media_signals
  POST /api/logs/{id}/anomalies  IsolationForest over auth-log sessions
  POST /api/analyze              deterministic findings rebuild (NFR-02 gated)
  GET  /api/findings             findings with full provenance
  POST /api/summaries            Gemini case summary with verified citations
  GET  /api/audit                append-only audit trail, chronological
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, text

# NOTE: models_phase5 MUST be imported before ..db — db.py runs
# Base.metadata.create_all() at import time, so the Phase 5 tables only exist
# if they are registered on Base first. main.py must preserve this order too
# (see INTEGRATION-5.md).
from ..models import Artifact
from ..models_phase5 import Anomaly, AuditLog, Finding, MediaSignal
from ..db import APP_DIR, DATA_DIR, SessionLocal
from ..services.anomaly import detect_log_anomalies
from ..services.custody import log_custody
from ..services.media import (
    PROPOSED_ELA_THRESHOLD,
    deepfake_score,
    ela_score,
    exif_flags,
)
from ..services.pulse import analyze_video

router = APIRouter()

# Pinned Flash-tier model (STACK.md section 10). NEVER the -latest alias:
# Google swaps the model behind aliases, which would make judging behavior
# non-reproducible.
GEMINI_MODEL = "gemini-3.8-flash"

CITATION_RE = re.compile(r"\[artifact:(\d+)\]")

# Pulse verdicts that emit a finding (directional only; inconclusive / no-face /
# insufficient-signal are stored on media_signals but never become findings).
PULSE_FINDING_VERDICTS = {"real-face-supported", "possibly-synthetic"}

# sshd auth-line parser for the anomaly session builder. Groups lines into
# sessions per (artifact, source IP); bytes are not present in sshd logs and are
# recorded honestly as 0.0 rather than fabricated.
SSHD_LINE = re.compile(
    r"^(?P<mon>[A-Z][a-z]{2})\s+(?P<day>\d{1,2})\s+"
    r"(?P<hour>\d{2}):\d{2}:\d{2}\s+\S+\s+sshd\[\d+\]:\s+"
    r"(?P<result>Accepted|Failed) password for (?:invalid user )?(?P<user>\S+)"
    r" from (?P<ip>\d{1,3}(?:\.\d{1,3}){3})"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _audit(session, action: str, detail: dict, actor: str = "investigator") -> None:
    """Append one audit row. Insert-only; the caller owns the transaction."""
    session.add(AuditLog(
        ts=_now(), actor=actor, action=action, detail_json=json.dumps(detail),
    ))


def _gate(title: str, rule_or_model: str, confidence: float,
          artifact_ids: list[int], snippet: str) -> dict:
    """NFR-02 hard gate: a finding without complete provenance is rejected
    with 422 instead of being stored."""
    if not artifact_ids:
        raise HTTPException(status_code=422, detail="finding rejected: no artifact_ids")
    if not rule_or_model:
        raise HTTPException(status_code=422, detail="finding rejected: no rule_or_model")
    if not snippet:
        raise HTTPException(status_code=422, detail="finding rejected: no snippet")
    return {
        "title": title,
        "description": "",
        "rule_or_model": rule_or_model,
        "confidence": confidence,
        "artifact_ids_json": json.dumps(sorted(set(artifact_ids))),
        "snippet": snippet,
        "created_ts": _now(),
    }


def _get_artifact(session, artifact_id: int) -> Artifact:
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return artifact


def _blob_path(artifact: Artifact) -> Path:
    try:
        stored = json.loads(artifact.metadata_json).get("stored_path")
    except (json.JSONDecodeError, AttributeError):
        stored = None
    if not stored:
        raise HTTPException(status_code=422, detail="artifact has no stored blob")
    path = DATA_DIR / stored
    if not path.exists():
        raise HTTPException(status_code=422, detail="stored blob missing from disk")
    return path


def _finding_to_dict(f: Finding) -> dict:
    return {
        "id": f.id,
        # "type" is the seeder/demo contract (INTEGRATION-6.md); it mirrors
        # rule_or_model, which is the plan's canonical name (05-01-PLAN.md).
        "type": f.rule_or_model,
        "title": f.title,
        "description": f.description,
        "rule_or_model": f.rule_or_model,
        "confidence": f.confidence,
        "artifact_ids": json.loads(f.artifact_ids_json),
        "snippet": f.snippet,
        "created_ts": f.created_ts,
    }


def _table_exists(session, name: str) -> bool:
    row = session.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n"),
        {"n": name},
    ).first()
    return row is not None


# ---------------------------------------------------------------------------
# POST /api/media/{id}/analyze — ELA + EXIF + deepfake (FRD-01/FRD-02)
# ---------------------------------------------------------------------------

@router.post("/api/media/{artifact_id}/analyze", status_code=201)
def analyze_media(artifact_id: int) -> dict:
    """Run media forensics on an image artifact and store the signals."""
    with SessionLocal() as session:
        artifact = _get_artifact(session, artifact_id)
        if artifact.source_type != "image":
            raise HTTPException(
                status_code=422,
                detail=f"media analysis requires an image artifact, got {artifact.source_type!r}",
            )
        blob = _blob_path(artifact)

        score, heatmap_abs = ela_score(str(blob))
        flags = exif_flags(
            json.loads(artifact.exif_json or "{}"),
            os.path.getmtime(blob),
        )
        df_score, df_model = deepfake_score(str(blob))  # (None, None) offline

        # Heatmap path stored relative to apps/api so a future static mount at
        # /storage can serve it to the investigator.
        try:
            heatmap_rel = str(Path(heatmap_abs).resolve().relative_to(APP_DIR.resolve()))
        except ValueError:
            heatmap_rel = str(heatmap_abs)

        row = session.execute(
            select(MediaSignal).where(MediaSignal.artifact_id == artifact_id)
        ).scalar_one_or_none()
        if row is None:
            row = MediaSignal(artifact_id=artifact_id, created_ts=_now())
            session.add(row)
        row.ela_score = score
        row.ela_heatmap_path = heatmap_rel
        row.exif_flags_json = json.dumps(flags)
        row.deepfake_score = df_score
        row.deepfake_model = df_model

        log_custody(session, artifact_id, "analyze",
                    f"media analysis: ELA {score:.5f}, EXIF flags {flags}, "
                    f"deepfake {df_score if df_score is not None else 'unavailable'}")
        _audit(session, "media_analyze", {
            "artifact_id": artifact_id, "ela_score": score,
            "exif_flags": flags, "deepfake_score": df_score,
        })
        session.commit()
        return {
            "artifact_id": artifact_id,
            "ela_score": score,
            "ela_heatmap_path": heatmap_rel,
            "exif_flags": flags,
            "deepfake_score": df_score,
            "deepfake_model": df_model,
        }


# ---------------------------------------------------------------------------
# POST /api/media/{id}/pulse — rPPG pulse-liveness (FRD-03)
# ---------------------------------------------------------------------------

@router.post("/api/media/{artifact_id}/pulse", status_code=201)
def analyze_pulse(artifact_id: int) -> dict:
    """Run rPPG pulse-liveness on a video artifact. Stores the verdict on the
    media_signals row; a finding is only emitted for directional verdicts by
    the findings engine (never for inconclusive/no-face/insufficient-signal).

    Face ROI: mediapipe FaceMesh first. If it detects no face in ANY frame,
    a deterministic center-frame box is used as a fallback (the synthetic
    demo fixture's rendered face is not detectable by FaceMesh) — disclosed
    as roi_source/pulse_note so the finding's provenance stays honest.
    """
    with SessionLocal() as session:
        artifact = _get_artifact(session, artifact_id)
        if artifact.source_type != "video":
            raise HTTPException(
                status_code=422,
                detail=f"pulse analysis requires a video artifact, got {artifact.source_type!r}",
            )
        blob = _blob_path(artifact)

        roi_source = "mediapipe-facemesh"
        try:
            result = analyze_video(str(blob))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        except RuntimeError as exc:
            # mediapipe missing/broken — a hard dependency failure, not a verdict.
            raise HTTPException(status_code=503, detail=str(exc))

        if result.get("frames_with_face", 0) == 0:
            # Fallback pass: deterministic center-frame box. Only engages when
            # the real detector found nothing, so genuine no-face footage is
            # still distinguishable in provenance (roi_source is stored).
            def _center_box(rgb_frame):
                h, w = rgb_frame.shape[:2]
                return (int(w * 0.30), int(h * 0.20), int(w * 0.70), int(h * 0.80))

            try:
                result = analyze_video(str(blob), face_detector=_center_box)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc))
            roi_source = "center-frame-fallback"
        result["roi_source"] = roi_source

        pulse_note = None
        if roi_source == "center-frame-fallback":
            pulse_note = ("face ROI: center-frame fallback (mediapipe FaceMesh "
                          "detected no face; synthetic-fixture path)")

        row = session.execute(
            select(MediaSignal).where(MediaSignal.artifact_id == artifact_id)
        ).scalar_one_or_none()
        if row is None:
            row = MediaSignal(artifact_id=artifact_id, created_ts=_now())
            session.add(row)
        row.pulse_bpm = result["bpm"]
        row.pulse_snr = result["snr"]
        row.pulse_verdict = result["verdict"]
        row.pulse_note = pulse_note

        log_custody(session, artifact_id, "analyze",
                    f"pulse-liveness: {result['verdict']} "
                    f"(BPM {result['bpm']}, SNR {result['snr']:.1f}, ROI {roi_source})")
        _audit(session, "media_pulse", {"artifact_id": artifact_id, **{
            k: result[k] for k in ("bpm", "snr", "verdict", "confidence",
                                  "face_seconds", "frames_with_face")
        }, "roi_source": roi_source})
        session.commit()
        return {"artifact_id": artifact_id, **result}


# ---------------------------------------------------------------------------
# POST /api/logs/{id}/anomalies — IsolationForest log anomalies (ANO-01)
# ---------------------------------------------------------------------------

def _parse_log_sessions(session) -> list[dict]:
    """Aggregate sshd auth lines across ALL log artifacts into per-(artifact,
    source-IP) sessions with {hour_of_day, failed_attempts, bytes_transferred}.

    Case-wide (not per-artifact): a single daily auth log has too few sessions
    for IsolationForest (MIN_SESSIONS=10); the scan needs the whole case.
    sshd logs carry no byte counts — bytes_transferred is honestly 0.0.
    """
    artifacts = session.execute(
        select(Artifact).where(Artifact.source_type == "log").order_by(Artifact.id)
    ).scalars().all()

    groups: dict[tuple[int, str], dict] = {}
    for artifact in artifacts:
        text_body = artifact.extracted_text or ""
        if not text_body:
            try:
                text_body = _blob_path(artifact).read_bytes().decode(
                    "utf-8", errors="replace")
            except HTTPException:
                continue
        for line in text_body.splitlines():
            m = SSHD_LINE.match(line.strip())
            if not m:
                continue
            key = (artifact.id, m.group("ip"))
            g = groups.get(key)
            if g is None:
                g = {
                    "session_id": f"log{artifact.id}:{m.group('ip')}",
                    "user": m.group("user"),
                    "hour_of_day": int(m.group("hour")),
                    "failed_attempts": 0,
                    "bytes_transferred": 0.0,
                    "artifact_id": artifact.id,
                    "lines": 0,
                }
                groups[key] = g
            if m.group("result") == "Failed":
                g["failed_attempts"] += 1
            g["lines"] += 1
    return list(groups.values())


def _run_anomaly_scan(session, anchor_id: int | None) -> dict:
    sessions = _parse_log_sessions(session)
    flagged = detect_log_anomalies(sessions)  # [] when <10 sessions — honest empty

    # Idempotent: the scan is case-wide, so rebuild the whole table.
    session.execute(text("DELETE FROM anomalies"))
    for item in flagged:
        session.add(Anomaly(
            artifact_id=item["session"]["artifact_id"],
            feature_json=json.dumps(item["features"]),
            score=item["score"],
            explanation=item["explanation"],
            created_ts=_now(),
        ))

    # Refresh the login-anomaly findings (the findings engine rebuilds these
    # too; doing it here keeps the endpoint self-sufficient).
    session.execute(
        text("DELETE FROM findings WHERE rule_or_model = 'login-anomaly'"))
    for item in flagged:
        f = _gate(
            title=f"Anomalous login session {item['session']['session_id']}",
            rule_or_model="login-anomaly",
            confidence=min(0.95, 0.5 + item["score"]),
            artifact_ids=[item["session"]["artifact_id"]],
            snippet=item["explanation"],
        )
        f["description"] = (
            "Unsupervised statistical outlier in auth-log sessions "
            "(IsolationForest). Flags statistical deviation, not confirmed malice."
        )
        session.add(Finding(**f))

    _audit(session, "anomaly_detect", {
        "anchor_artifact_id": anchor_id,
        "sessions_scanned": len(sessions),
        "flagged": len(flagged),
    })
    session.commit()
    return {
        "sessions_scanned": len(sessions),
        "flagged": len(flagged),
        "anomalies": [
            {
                "session_id": item["session"]["session_id"],
                "artifact_id": item["session"]["artifact_id"],
                "score": item["score"],
                "explanation": item["explanation"],
            }
            for item in flagged
        ],
    }


@router.post("/api/logs/{artifact_id}/anomalies", status_code=201)
def detect_anomalies_for_log(artifact_id: int) -> dict:
    """Case-wide anomaly scan anchored on one log artifact (2xx = ran).

    The scan aggregates sessions across ALL log artifacts in the case: a
    single daily auth log has too few sessions for IsolationForest
    (MIN_SESSIONS=10), so per-artifact-only scanning would always return [].
    """
    with SessionLocal() as session:
        _get_artifact(session, artifact_id)  # 404 if missing; anchors the run
        return _run_anomaly_scan(session, anchor_id=artifact_id)


# ---------------------------------------------------------------------------
# Findings engine — deterministic rules, NFR-02 gated (EXP-01)
# ---------------------------------------------------------------------------

def _rule_shared_identifier_link(session) -> int:
    """One finding per same_identifier relation with confidence >= 0.85.

    Skipped silently when the Phase 3 identities/relations tables are not
    wired yet — emitting a finding without provenance would violate NFR-02.
    """
    if not (_table_exists(session, "relations") and _table_exists(session, "identities")):
        return 0
    rows = session.execute(text(
        "SELECT id, identity_a_id, identity_b_id, relation_type, evidence_json, confidence"
        " FROM relations WHERE relation_type = 'same_identifier' AND confidence >= 0.85"
        " ORDER BY id"
    )).mappings().all()
    if not rows:
        return 0

    def canonical(ident_id: int) -> str:
        r = session.execute(text(
            "SELECT canonical_value FROM identities WHERE id = :i"), {"i": ident_id}
        ).first()
        return r[0] if r else f"identity:{ident_id}"

    count = 0
    for r in rows:
        try:
            evidence = json.loads(r["evidence_json"] or "{}")
        except json.JSONDecodeError:
            continue
        via_ids = evidence.get("via_entity_ids") or []
        if not via_ids:
            continue  # no provenance trail -> no finding (NFR-02)
        # via_entity_ids are Python ints from the correlation module; int() them
        # defensively before interpolating (no user input reaches this query).
        placeholders = ",".join(str(int(v)) for v in via_ids)
        art_ids = [row[0] for row in session.execute(
            text(f"SELECT DISTINCT artifact_id FROM entities WHERE id IN ({placeholders})")
        ).all()]
        if not art_ids:
            continue
        a_name, b_name = canonical(r["identity_a_id"]), canonical(r["identity_b_id"])
        ident = f"{evidence.get('identifier_kind', 'identifier')}: {evidence.get('identifier_value', '?')}"
        f = _gate(
            title=f"Shared identifier link: {a_name} <-> {b_name}",
            rule_or_model="shared-identifier-link",
            confidence=float(r["confidence"]),
            artifact_ids=art_ids,
            snippet=f"{a_name} and {b_name} share {ident}",
        )
        f["description"] = (
            "Two identities resolve through the same corroborated identifier "
            "(entity resolution across sources)."
        )
        session.add(Finding(**f))
        count += 1
    return count


def _rule_tampered_media(session) -> int:
    """tampered-media: ELA >= calibrated threshold (0.007, MEDIA-NOTE) or any
    EXIF flag set."""
    rows = session.execute(select(MediaSignal)).scalars().all()
    count = 0
    for row in rows:
        try:
            flags = json.loads(row.exif_flags_json or "[]")
        except json.JSONDecodeError:
            flags = []
        ela_hit = row.ela_score is not None and row.ela_score >= PROPOSED_ELA_THRESHOLD
        if not (ela_hit or flags):
            continue
        parts = []
        if ela_hit:
            parts.append(f"ELA score {row.ela_score:.5f} >= threshold {PROPOSED_ELA_THRESHOLD}")
        if flags:
            parts.append(f"EXIF flags: {', '.join(flags)}")
        if row.ela_heatmap_path:
            parts.append(f"heatmap: {row.ela_heatmap_path}")
        if row.deepfake_score is not None:
            parts.append(
                f"deepfake model {row.deepfake_model} score {row.deepfake_score:.2f} "
                "(model signal, not ground truth)"
            )
        elif row.deepfake_model is None and row.deepfake_score is None:
            parts.append("deepfake model unavailable offline — heuristic signals only")
        confidence = 0.75 if not ela_hit else min(0.95, 0.75 + (row.ela_score - PROPOSED_ELA_THRESHOLD) * 10)
        f = _gate(
            title=f"Possible media tampering (artifact #{row.artifact_id})",
            rule_or_model="tampered-media",
            confidence=confidence,
            artifact_ids=[row.artifact_id],
            snippet="; ".join(parts),
        )
        f["description"] = (
            "Error-level analysis and/or EXIF inconsistencies suggest the image "
            "was edited after capture."
        )
        session.add(Finding(**f))
        count += 1
    return count


def _rule_pulse_liveness(session) -> int:
    """pulse-liveness: directional verdicts only, always with the caveat."""
    rows = session.execute(
        select(MediaSignal).where(MediaSignal.pulse_verdict.in_(PULSE_FINDING_VERDICTS))
    ).scalars().all()
    count = 0
    for row in rows:
        snippet = (
            f"pulse verdict {row.pulse_verdict}, BPM "
            f"{row.pulse_bpm if row.pulse_bpm is not None else 'n/a'}, "
            f"SNR {row.pulse_snr:.1f}"
        )
        if row.pulse_note:
            snippet += f"; {row.pulse_note}"
        f = _gate(
            title=f"Pulse-liveness signal (artifact #{row.artifact_id})",
            rule_or_model="pulse-liveness",  # seeder contract; method named in description
            confidence=float(row.pulse_snr / 20) if row.pulse_snr else 0.05,
            artifact_ids=[row.artifact_id],
            snippet=snippet,
        )
        # Clamp to the module's calibrated mapping (clip(snr/20, 0.05, 0.95)).
        f["confidence"] = max(0.05, min(0.95, f["confidence"]))
        f["description"] = (
            "Remote photoplethysmography liveness signal: a real face shows a "
            "strong periodic pulse, a synthetic face shows none. "
            "Supporting signal, not proof."
        )
        session.add(Finding(**f))
        count += 1
    return count


def _rule_login_anomaly(session) -> int:
    """login-anomaly: one finding per anomalies row."""
    rows = session.execute(select(Anomaly).order_by(Anomaly.score.desc())).scalars().all()
    count = 0
    for row in rows:
        f = _gate(
            title=f"Anomalous log session (artifact #{row.artifact_id})",
            rule_or_model="login-anomaly",
            confidence=min(0.95, 0.5 + row.score),
            artifact_ids=[row.artifact_id],
            snippet=row.explanation,
        )
        f["description"] = (
            "Unsupervised statistical outlier in auth-log sessions "
            "(IsolationForest). Flags statistical deviation, not confirmed malice."
        )
        session.add(Finding(**f))
        count += 1
    return count


def _run_findings(session) -> dict:
    """Idempotent rebuild: wipe and regenerate every finding."""
    session.execute(text("DELETE FROM findings"))
    counts = {
        "shared-identifier-link": _rule_shared_identifier_link(session),
        "tampered-media": _rule_tampered_media(session),
        "pulse-liveness": _rule_pulse_liveness(session),
        "login-anomaly": _rule_login_anomaly(session),
    }
    _audit(session, "findings_run", {"rules": counts})
    session.commit()
    return {"findings": sum(counts.values()), "rules": counts}


@router.post("/api/analyze", status_code=201)
def analyze() -> dict:
    """Deterministic findings rebuild (05-01-PLAN.md Task 5.1). Idempotent:
    wipes and regenerates every finding. Every emitted finding passes the
    NFR-02 provenance gate; anything that can't is never inserted."""
    with SessionLocal() as session:
        return _run_findings(session)


@router.get("/api/findings")
def list_findings() -> list:
    with SessionLocal() as session:
        rows = session.execute(
            select(Finding).order_by(Finding.confidence.desc(), Finding.id)
        ).scalars().all()
        return [_finding_to_dict(f) for f in rows]


# ---------------------------------------------------------------------------
# POST /api/summaries — Gemini case summary with verified citations (EXP-02)
# ---------------------------------------------------------------------------

def _gemini_generate(prompt: str, api_key: str) -> str:
    """Call the pinned model with 429/503 retry. Raises on hard failure so the
    caller can degrade gracefully."""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={api_key}"
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1024},
    }).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(4):  # initial try + 3 retries
        try:
            req = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in (429, 503) and attempt < 3:
                time.sleep(2 ** attempt)  # 1s, 2s, 4s backoff
                continue
            raise
        except (urllib.error.URLError, TimeoutError, KeyError, IndexError) as exc:
            last_error = exc
            raise
    assert last_error is not None
    raise last_error


def _verify_citations(text: str, valid_ids: set[int]) -> tuple[str, int]:
    """Drop sentences whose [artifact:N] citations don't resolve to real
    artifacts. Returns (cleaned text, dropped sentence count)."""
    dropped = 0
    kept: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        cited = {int(n) for n in CITATION_RE.findall(sentence)}
        if cited and not cited.issubset(valid_ids):
            dropped += 1
            continue
        kept.append(sentence)
    return " ".join(kept).strip(), dropped


def _build_summary_prompt(findings: list[Finding], artifacts: list[Artifact]) -> str:
    lines = [
        "You are a digital forensics assistant writing a case summary for an investigator.",
        "RULES:",
        "- Every factual claim must cite its source as [artifact:<id>] using ONLY the artifact ids listed below.",
        "- Never invent artifact ids. Never state anything as fact without a citation.",
        "- Be concise: key entities, timeline anchors, and what the findings establish.",
        "",
        "ARTIFACTS:",
    ]
    for a in artifacts:
        lines.append(
            f"- [artifact:{a.id}] {a.source_type} \"{a.filename}\" "
            f"(sha256 {a.sha256[:16]}...)"
        )
    lines.append("")
    lines.append("FINDINGS:")
    for f in findings:
        lines.append(
            f"- {f.rule_or_model} (confidence {f.confidence:.2f}): {f.title}. "
            f"{f.snippet} [artifacts {f.artifact_ids_json}]"
        )
    lines.append("")
    lines.append("Write the case summary now.")
    return "\n".join(lines)


def _template_summary(findings: list[Finding]) -> str:
    """Deterministic offline summary — clearly labeled, never LLM output."""
    if not findings:
        return ("Offline template summary: no findings have been generated yet. "
                "Run the findings engine first.")
    top = findings[:5]
    parts = [
        f"Offline template summary (not AI-generated): {len(findings)} finding(s).",
    ]
    for f in top:
        ids = ", ".join(f"artifact:{i}" for i in json.loads(f.artifact_ids_json))
        parts.append(f"- {f.title} [{ids}] (confidence {f.confidence:.2f})")
    return " ".join(parts)


@router.post("/api/summaries", status_code=201)
def create_summary() -> dict:
    """Generate a cited case summary. Offline / no API key -> graceful
    degradation to a labeled template summary; findings always render."""
    with SessionLocal() as session:
        findings = session.execute(
            select(Finding).order_by(Finding.confidence.desc(), Finding.id)
        ).scalars().all()
        artifacts = session.execute(
            select(Artifact).order_by(Artifact.id)).scalars().all()
        valid_ids = {a.id for a in artifacts}

        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            _audit(session, "summary", {"mode": "template-offline",
                                       "reason": "GEMINI_API_KEY not set"})
            session.commit()
            return {
                "summary": _template_summary(findings),
                "degraded": True,
                "reason": "GEMINI_API_KEY not set — template summary",
                "model": None,
            }

        prompt = _build_summary_prompt(findings, artifacts)
        try:
            raw = _gemini_generate(prompt, api_key)
        except Exception as exc:  # network failure, bad key, 4xx/5xx
            _audit(session, "summary", {"mode": "template-offline",
                                       "reason": f"gemini call failed: {type(exc).__name__}"})
            session.commit()
            return {
                "summary": _template_summary(findings),
                "degraded": True,
                "reason": f"summary unavailable offline ({type(exc).__name__})",
                "model": None,
            }

        cleaned, dropped = _verify_citations(raw, valid_ids)
        _audit(session, "summary", {
            "mode": "gemini", "model": GEMINI_MODEL,
            "citations_dropped": dropped,
        })
        session.commit()
        return {
            "summary": cleaned,
            "degraded": False,
            "model": GEMINI_MODEL,
            "citations_dropped": dropped,
        }


# ---------------------------------------------------------------------------
# GET /api/audit — append-only audit trail (EXP-03)
# ---------------------------------------------------------------------------

@router.get("/api/audit")
def list_audit() -> list:
    with SessionLocal() as session:
        rows = session.execute(
            select(AuditLog).order_by(AuditLog.id)
        ).scalars().all()
        return [
            {
                "id": r.id,
                "ts": r.ts,
                "actor": r.actor,
                "action": r.action,
                "detail": json.loads(r.detail_json or "{}"),
            }
            for r in rows
        ]

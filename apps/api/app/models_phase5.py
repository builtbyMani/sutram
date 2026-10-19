"""Phase 5 tables: findings, audit_log, media_signals, anomalies (05-CONTEXT.md).

Additive-only — never redesigns the Phase 1/2 tables. Imported once (for its
side effect of registering on Base) by main.py, so these tables land in
Base.metadata before db.py's create_all() runs.
"""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class Finding(Base):
    """A system conclusion. Every row must carry full provenance (NFR-02):
    non-empty artifact_ids_json, rule_or_model, and snippet — enforced by the
    API before insert and by the web UI before render."""

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rule_or_model: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    artifact_ids_json: Mapped[str] = mapped_column(Text, nullable=False)  # JSON list[int]
    snippet: Mapped[str] = mapped_column(Text, nullable=False)
    created_ts: Mapped[str] = mapped_column(String(32), nullable=False)  # UTC ISO-8601


class AuditLog(Base):
    """Append-only system-action log (EXP-03). Insert-only by convention:
    no code path may UPDATE or DELETE audit_log rows."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(32), nullable=False)  # UTC ISO-8601
    actor: Mapped[str] = mapped_column(String(64), nullable=False, default="investigator")
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    detail_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class MediaSignal(Base):
    """Forensic signals for one image/video artifact (FRD-01/02/03)."""

    __tablename__ = "media_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    artifact_id: Mapped[int] = mapped_column(
        ForeignKey("artifacts.id"), nullable=False, unique=True, index=True
    )
    ela_score: Mapped[float | None] = mapped_column(nullable=True)
    ela_heatmap_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    exif_flags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    deepfake_score: Mapped[float | None] = mapped_column(nullable=True)
    deepfake_model: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # FRD-03 pulse-liveness (pulse.py)
    pulse_bpm: Mapped[float | None] = mapped_column(nullable=True)
    pulse_snr: Mapped[float | None] = mapped_column(nullable=True)
    pulse_verdict: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # FRD-03 methodological provenance: how the face ROI was obtained
    # ("mediapipe-facemesh" or "center-frame-fallback"); disclosed in findings.
    pulse_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_ts: Mapped[str] = mapped_column(String(32), nullable=False)  # UTC ISO-8601


class Anomaly(Base):
    """One IsolationForest-flagged log session (ANO-01)."""

    __tablename__ = "anomalies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    artifact_id: Mapped[int] = mapped_column(
        ForeignKey("artifacts.id"), nullable=False, index=True
    )
    feature_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    score: Mapped[float] = mapped_column(nullable=False)  # higher = more anomalous
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_ts: Mapped[str] = mapped_column(String(32), nullable=False)  # UTC ISO-8601

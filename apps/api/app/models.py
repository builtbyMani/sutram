"""Unified evidence schema (locked in 01-CONTEXT.md D-03).

Later phases extend these tables (new columns/tables) but never redesign them.
"""

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    ingest_ts: Mapped[str] = mapped_column(String(32), nullable=False)  # UTC ISO-8601
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # Phase 2 additions (additive only): OCR/plain text and EXIF JSON.
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    exif_json: Mapped[str | None] = mapped_column(Text, nullable=True, default="{}")


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    artifact_id: Mapped[int] = mapped_column(ForeignKey("artifacts.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(String(1024), nullable=False)
    span_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class CustodyLog(Base):
    """Append-only chain-of-custody log (INT-02). Rows are never updated/deleted."""

    __tablename__ = "custody_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    artifact_id: Mapped[int] = mapped_column(ForeignKey("artifacts.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)  # ingest|view|extract|analyze
    actor: Mapped[str] = mapped_column(String(64), nullable=False, default="investigator")
    ts: Mapped[str] = mapped_column(String(32), nullable=False)  # UTC ISO-8601
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")

# Phase 3/4 tables: importing these submodules registers identities, relations
# and events on Base.metadata, so db.py's create_all() (which runs at import)
# sees them no matter which module imports app.db first.
from . import models_phase3  # noqa: F401
from . import models_phase4  # noqa: F401
from . import models_phase5  # noqa: F401

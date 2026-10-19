"""Phase 3 tables: identities + relations (03-CONTEXT.md, additive only).

These tables hold the output of the correlation engine
(services/correlation.py). The 1-line integration edit in app/models.py
(`from . import models_phase3`) registers them on Base.metadata so that
app/db.py's create_all() creates them on startup. See INTEGRATION-3.md.
"""

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class Identity(Base):
    """A canonical entity resolved from one or more raw entity mentions."""

    __tablename__ = "identities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_value: Mapped[str] = mapped_column(String(1024), nullable=False)
    # JSON list of entity ids (= resolver's member_entity_ids)
    merged_entity_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")


class Relation(Base):
    """An edge between two identities: same_identifier | co_occurrence."""

    __tablename__ = "relations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    identity_a_id: Mapped[int] = mapped_column(
        ForeignKey("identities.id"), nullable=False, index=True
    )
    identity_b_id: Mapped[int] = mapped_column(
        ForeignKey("identities.id"), nullable=False, index=True
    )
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # JSON of the resolver's evidence dict
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

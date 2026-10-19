"""Phase 4 (timeline): `events` table — additive only.

Columns exactly per TIMELINE-NOTE.md / 04-01-PLAN.md Task 4.1.
Import this module (or `app.models_phase4`) before `app.db` is first imported
so `Base.metadata.create_all()` includes this table. See INTEGRATION-4.md.
"""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    artifact_id: Mapped[int] = mapped_column(
        ForeignKey("artifacts.id"), nullable=False, index=True
    )
    event_ts_utc: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )  # UTC ISO-8601, ends "+00:00"
    label: Mapped[str | None] = mapped_column(String(512), nullable=True)
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)

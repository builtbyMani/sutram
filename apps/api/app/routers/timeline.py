"""Phase 4 (timeline) endpoints — mounted by the integrator via include_router.

Routes (all under /api, no /v1 prefix):
  POST /api/timeline/extract?artifact_id=N  — (re-)extract events for one artifact
  POST /api/timeline/extract-all            — (re-)extract events for all artifacts
  GET  /api/timeline                         — events ordered by event_ts_utc ASC
"""

import json

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, select

from ..db import SessionLocal
from ..models import Artifact
from ..models_phase4 import Event
from ..services.custody import log_custody
from ..services.timeline import extract_events

router = APIRouter(tags=["timeline"])


def _persist_events(session, artifact: Artifact) -> int:
    """Delete-then-reinsert events for one artifact (idempotent re-runs)."""
    events = extract_events(
        {
            "id": artifact.id,
            "source_type": artifact.source_type,
            "text": artifact.extracted_text,
            "exif_json": artifact.exif_json,
            "metadata_json": artifact.metadata_json,
        }
    )
    session.execute(delete(Event).where(Event.artifact_id == artifact.id))
    for e in events:
        session.add(
            Event(
                artifact_id=e["artifact_id"],
                event_ts_utc=e["event_ts_utc"],
                label=e.get("label"),
                detail_json=json.dumps(e.get("detail_json") or {}),
            )
        )
    log_custody(session, artifact.id, "extract",
                f"timeline events extracted ({len(events)} events)")
    return len(events)


@router.post("/api/timeline/extract")
def extract_timeline(artifact_id: int) -> dict:
    """Extract + persist timeline events for one artifact."""
    with SessionLocal() as session:
        artifact = session.get(Artifact, artifact_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        count = _persist_events(session, artifact)
        session.commit()
        return {"artifact_id": artifact_id, "events": count}


@router.post("/api/timeline/extract-all")
def extract_timeline_all() -> dict:
    """Extract + persist timeline events for every artifact."""
    with SessionLocal() as session:
        artifacts = session.execute(select(Artifact)).scalars().all()
        total = sum(_persist_events(session, a) for a in artifacts)
        session.commit()
        return {"artifacts": len(artifacts), "events": total}


@router.get("/api/timeline")
def get_timeline() -> list:
    """All events ordered by event_ts_utc ascending."""
    with SessionLocal() as session:
        rows = session.execute(
            select(Event, Artifact.source_type)
            .join(Artifact, Event.artifact_id == Artifact.id)
            .order_by(Event.event_ts_utc.asc(), Event.id.asc())
        ).all()
        return [
            {
                "id": ev.id,
                "event_ts_utc": ev.event_ts_utc,
                "label": ev.label,
                "source_type": source_type,
                "artifact_id": ev.artifact_id,
            }
            for ev, source_type in rows
        ]

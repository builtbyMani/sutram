"""Phase 3 API wiring: correlate endpoint + graph API (03-01-PLAN.md Tasks 3.1/3.4).

Registered in app/main.py via:
    from app.routers.correlation import router as correlation_router
    app.include_router(correlation_router)
See INTEGRATION-3.md for the exact edit.
"""

import json
import struct

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, select

from ..db import SessionLocal
from ..models import Artifact, Entity
from ..models_phase3 import Identity, Relation
from ..services.correlation import build_graph_data, resolve_identities

router = APIRouter()


def _load_entities(session) -> list[dict]:
    """Read all entities as the resolver's dicts, reusing ingest-time
    embeddings when the entities.embedding column exists (Phase 2's
    additive column; tolerate its absence so this router works before
    and after that migration)."""
    use_embedding = hasattr(Entity, "embedding")
    cols = [Entity.id, Entity.artifact_id, Entity.kind, Entity.value]
    if use_embedding:
        cols.append(Entity.embedding)
    rows = session.execute(select(*cols)).all()
    entities = []
    for r in rows:
        d = {"id": r[0], "artifact_id": r[1], "kind": r[2], "value": r[3]}
        if use_embedding and r[4] is not None:
            d["embedding"] = list(struct.unpack("384f", bytes(r[4])))
        entities.append(d)
    return entities


def _identity_rows_to_dicts(
    identities: list[Identity], relations: list[Relation], member_artifacts: dict[int, list[int]]
) -> tuple[list[dict], list[dict]]:
    idents = [
        {
            "id": row.id,
            "kind": row.kind,
            "canonical_value": row.canonical_value,
            "member_entity_ids": json.loads(row.merged_entity_ids_json),
            "artifact_ids": member_artifacts.get(row.id, []),
            "confidence": 1.0,  # provenance per-merge lives in the resolver; DB keeps the merged shape
        }
        for row in identities
    ]
    rels = [
        {
            "id": r.id,
            "a": r.identity_a_id,
            "b": r.identity_b_id,
            "relation_type": r.relation_type,
            "evidence": json.loads(r.evidence_json),
            "confidence": r.confidence,
        }
        for r in relations
    ]
    return idents, rels


def _artifact_ids_for_identities(session, identities: list[Identity]) -> dict[int, list[int]]:
    """member identity id -> sorted distinct artifact ids (recomputed from
    entities; artifact_ids are not a DB column — see CORRELATION-NOTE.md §3)."""
    member_ids = {i.id: json.loads(i.merged_entity_ids_json) for i in identities}
    all_entity_ids = sorted({eid for ids in member_ids.values() for eid in ids})
    ent_to_art: dict[int, int] = {}
    if all_entity_ids:
        rows = session.execute(
            select(Entity.id, Entity.artifact_id).where(Entity.id.in_(all_entity_ids))
        ).all()
        ent_to_art = {r[0]: r[1] for r in rows}
    return {
        iid: sorted({ent_to_art[eid] for eid in ids if eid in ent_to_art})
        for iid, ids in member_ids.items()
    }


@router.post("/api/correlate")
def correlate() -> dict:
    """Idempotent rebuild: clear identities/relations and re-resolve from
    current entities. Deterministic resolver output makes this safe to
    re-run (COR-01)."""
    with SessionLocal() as session:
        entities = _load_entities(session)
        identities, relations = resolve_identities(entities)

        session.execute(delete(Relation))
        session.execute(delete(Identity))

        # Resolver ids (gid) are 1-based and deterministic; map to DB rows.
        gid_to_row: dict[int, Identity] = {}
        for ident in identities:
            row = Identity(
                kind=ident["kind"],
                canonical_value=ident["canonical_value"],
                merged_entity_ids_json=json.dumps(ident["member_entity_ids"]),
            )
            session.add(row)
            session.flush()  # assign row.id for relation mapping
            gid_to_row[ident["id"]] = row

        for rel in relations:
            session.add(
                Relation(
                    identity_a_id=gid_to_row[rel["a"]].id,
                    identity_b_id=gid_to_row[rel["b"]].id,
                    relation_type=rel["relation_type"],
                    evidence_json=json.dumps(rel["evidence"]),
                    confidence=rel["confidence"],
                )
            )
        session.commit()
        return {"identities": len(identities), "relations": len(relations)}


@router.get("/api/graph")
def get_graph() -> dict:
    """Evidence graph in build_graph_data() shape:
    {nodes: [{id, kind, canonical_value, artifact_count}],
     edges: [{a, b, relation_type, confidence}]} (COR-02)."""
    with SessionLocal() as session:
        identities = session.execute(select(Identity).order_by(Identity.id)).scalars().all()
        relations = session.execute(select(Relation).order_by(Relation.id)).scalars().all()
        member_artifacts = _artifact_ids_for_identities(session, identities)
        idents, rels = _identity_rows_to_dicts(identities, relations, member_artifacts)
        return build_graph_data(idents, rels)


@router.get("/api/identities/{identity_id}/artifacts")
def identity_artifacts(identity_id: int) -> dict:
    """Every artifact mentioning an identity (COR-03 drill-down)."""
    with SessionLocal() as session:
        ident = session.get(Identity, identity_id)
        if ident is None:
            raise HTTPException(status_code=404, detail="identity not found")
        member_ids = json.loads(ident.merged_entity_ids_json)
        artifacts = []
        if member_ids:
            artifact_ids = (
                session.execute(
                    select(Entity.artifact_id)
                    .where(Entity.id.in_(member_ids))
                    .distinct()
                )
                .scalars()
                .all()
            )
            if artifact_ids:
                artifacts = (
                    session.execute(
                        select(Artifact)
                        .where(Artifact.id.in_(artifact_ids))
                        .order_by(Artifact.id)
                    )
                    .scalars()
                    .all()
                )
        return {
            "identity": {
                "id": ident.id,
                "kind": ident.kind,
                "canonical_value": ident.canonical_value,
                "member_entity_ids": member_ids,
            },
            "artifacts": [
                {
                    "id": a.id,
                    "filename": a.filename,
                    "source_type": a.source_type,
                    "sha256": a.sha256,
                }
                for a in artifacts
            ],
        }

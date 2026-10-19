"""SUTRAM Forensics API — Phase 2: extraction pipeline + integrity layer.

Endpoints: GET /health, POST /api/artifacts, GET /api/artifacts,
GET /api/artifacts/{id} (with entities).
Python owns all forensics work; the Next.js frontend proxies /api/* here (D-02).
"""

import hashlib
import json
from datetime import datetime, timezone

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select

from .db import DATA_DIR, SessionLocal
from .models import Artifact, CustodyLog, Entity
from .services.custody import log_custody
from .services.extraction import extract_exif, extract_ocr, extract_text_artifact
from .services.osint import OsintFetchError, fetch_url, search_news, slug_filename, utc_now_iso
from .routers.correlation import router as correlation_router
from .routers.timeline import router as timeline_router, _persist_events as persist_timeline_events
from .routers import fraud

app = FastAPI(title="SUTRAM Forensics API", version="0.2.0")

app.include_router(correlation_router)
app.include_router(timeline_router)
app.include_router(fraud.router)

# Defense-in-depth only: the browser goes through the Next.js same-origin
# rewrite proxy, so CORS should never fire in practice (STACK.md section 2).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Source types whose bytes are decoded as text and run through entity extraction.
TEXT_SOURCE_TYPES = {"document", "chat", "chat_export", "log", "osint"}

# Extension allowlist per source type (ING-03). "other" is the escape hatch
# with no restriction. osint artifacts are never uploaded (see /api/osint/fetch).
ALLOWED_EXTENSIONS = {
    "document": {".txt", ".md", ".docx", ".pdf"},
    "chat": {".txt", ".json", ".csv", ".md"},
    "chat_export": {".txt", ".json", ".csv", ".md"},
    "log": {".log", ".txt"},
    "image": {".jpg", ".jpeg", ".png", ".webp"},
    "video": {".mp4", ".mov"},
    "pcap": {".pcap", ".pcapng", ".txt"},  # .txt: tshark/tcpdump text summaries
}


def _extension_of(filename: str) -> str:
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def artifact_to_dict(a: Artifact, entities: list | None = None) -> dict:
    return {
        "id": a.id,
        "source_type": a.source_type,
        "filename": a.filename,
        "sha256": a.sha256,
        "ingest_ts": a.ingest_ts,
        "metadata": json.loads(a.metadata_json),
        "extracted_text": a.extracted_text,
        "exif": json.loads(a.exif_json or "{}"),
        "entities": (
            [
                {
                    "id": e.id,
                    "kind": e.kind,
                    "value": e.value,
                    "span": json.loads(e.span_json),
                }
                for e in entities
            ]
            if entities is not None
            else None
        ),
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/artifacts", status_code=201)
def create_artifact(
    file: UploadFile = File(...),
    source_type: str = Form("document"),
) -> dict:
    data = file.file.read()
    filename = file.filename or "unnamed"

    # ING-03: extension allowlist per source type, enforced before anything
    # is persisted. "other" has no restriction (escape hatch).
    ext = _extension_of(filename)
    allowed = ALLOWED_EXTENSIONS.get(source_type)
    if allowed is not None and ext not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"file type {ext or '(no extension)'} not allowed "
                   f"for source '{source_type}'",
        )

    digest = hashlib.sha256(data).hexdigest()

    # Content-addressed storage: data/<first-2-hex-chars>/<sha256>
    blob_dir = DATA_DIR / digest[:2]
    blob_dir.mkdir(parents=True, exist_ok=True)
    blob_path = blob_dir / digest
    blob_created = not blob_path.exists()

    try:
        if blob_created:
            blob_path.write_bytes(data)

        ingest_ts = datetime.now(timezone.utc).isoformat()
        metadata = {
            "size": len(data),
            "content_type": file.content_type,
            "stored_path": str(blob_path.relative_to(DATA_DIR)),
        }

        with SessionLocal() as session:
            return _persist_uploaded_artifact(session, data, filename, source_type,
                                              digest, ingest_ts, metadata)
    except HTTPException:
        raise
    except Exception as exc:
        # Graceful failure: a corrupt/unparseable file must not leave a
        # partial row or orphaned blob behind (INT-04). Server-internal
        # paths are scrubbed from the client-facing message.
        if blob_created and blob_path.exists():
            blob_path.unlink()
        safe_msg = str(exc).replace(str(DATA_DIR), "<data-dir>")
        raise HTTPException(
            status_code=422,
            detail=f"could not process file as '{source_type}': {safe_msg}",
        )


def _persist_uploaded_artifact(session, data: bytes, filename: str, source_type: str,
                               digest: str, ingest_ts: str, metadata: dict) -> dict:
    """DB half of the upload: row + extraction + custody in one transaction."""
    existing = session.execute(
        select(Artifact).where(Artifact.sha256 == digest)
    ).scalar_one_or_none()
    if existing is not None:
        # Idempotent re-upload: same bytes, same artifact (no re-extraction).
        return artifact_to_dict(existing)
    artifact = Artifact(
        source_type=source_type,
        filename=filename,
        sha256=digest,
        ingest_ts=ingest_ts,
        metadata_json=json.dumps(metadata),
    )
    session.add(artifact)
    session.flush()  # assign artifact.id without committing yet

    # Phase 2: synchronous extraction inside the upload request (02-CONTEXT.md).
    # Single transaction: if extraction fails, the whole upload rolls back so
    # an artifact can never exist without its entities (silent data loss is
    # worse than a loud 500 for a forensics tool).
    extract_detail = ""
    if source_type in TEXT_SOURCE_TYPES:
        if b"\x00" in data:
            raise ValueError("file contains binary data, not text")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("file is not valid UTF-8 text")
        entities = extract_text_artifact(text, artifact.id)
        session.add_all(entities)
        artifact.extracted_text = text
        extract_detail = f"{len(entities)} entities extracted"
    elif source_type == "image":
        blob_abs = DATA_DIR / metadata["stored_path"]
        artifact.extracted_text = extract_ocr(str(blob_abs))
        artifact.exif_json = json.dumps(extract_exif(str(blob_abs)))
        extract_detail = "ocr + exif extracted"

    log_custody(session, artifact.id, "ingest",
                f"uploaded {filename} as {source_type}")
    if extract_detail:
        log_custody(session, artifact.id, "extract", extract_detail)

    # Phase 4: timeline events are derived data — extract synchronously so the
    # timeline is populated the moment the upload completes (the demo seeder
    # and UI both expect GET /api/timeline to work right after ingest).
    persist_timeline_events(session, artifact)

    session.commit()
    return artifact_to_dict(artifact)


@app.get("/api/artifacts")
def list_artifacts() -> list:
    with SessionLocal() as session:
        rows = session.execute(
            select(Artifact).order_by(Artifact.id.desc())
        ).scalars().all()
        return [artifact_to_dict(a) for a in rows]


@app.get("/api/artifacts/{artifact_id}")
def get_artifact(artifact_id: int) -> dict:
    """Artifact detail: stored fields plus its extracted entities."""
    with SessionLocal() as session:
        artifact = session.get(Artifact, artifact_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        entities = session.execute(
            select(Entity)
            .where(Entity.artifact_id == artifact_id)
            .order_by(Entity.id)
        ).scalars().all()
        log_custody(session, artifact_id, "view", "artifact detail viewed")
        session.commit()
        return artifact_to_dict(artifact, entities)


@app.get("/api/artifacts/{artifact_id}/custody")
def get_custody(artifact_id: int) -> list:
    """Chain-of-custody entries for an artifact, newest first."""
    with SessionLocal() as session:
        if session.get(Artifact, artifact_id) is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        rows = session.execute(
            select(CustodyLog)
            .where(CustodyLog.artifact_id == artifact_id)
            .order_by(CustodyLog.id.desc())
        ).scalars().all()
        return [
            {
                "id": r.id,
                "action": r.action,
                "actor": r.actor,
                "ts": r.ts,
                "detail": r.detail,
            }
            for r in rows
        ]


class OsintFetchRequest(BaseModel):
    url: str | None = None
    keyword: str | None = None


def _store_osint_page(session, markdown: str, final_url: str) -> Artifact:
    """Persist one fetched page as an osint artifact (idempotent on content)."""
    data = markdown.encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    existing = session.execute(
        select(Artifact).where(Artifact.sha256 == digest)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    blob_dir = DATA_DIR / digest[:2]
    blob_dir.mkdir(parents=True, exist_ok=True)
    blob_path = blob_dir / digest
    if not blob_path.exists():
        blob_path.write_bytes(data)
    artifact = Artifact(
        source_type="osint",
        filename=slug_filename(final_url),
        sha256=digest,
        ingest_ts=utc_now_iso(),
        extracted_text=markdown,
        metadata_json=json.dumps({
            "url": final_url,
            "fetched_at_utc": utc_now_iso(),
            "fetcher": "scrapling-http",
            "size": len(data),
            "content_type": "text/markdown",
            "stored_path": str(blob_path.relative_to(DATA_DIR)),
        }),
    )
    session.add(artifact)
    session.flush()
    entities = extract_text_artifact(markdown, artifact.id)
    session.add_all(entities)
    log_custody(session, artifact.id, "ingest", f"fetched {final_url}")
    log_custody(session, artifact.id, "extract", f"{len(entities)} entities extracted")
    persist_timeline_events(session, artifact)
    return artifact


@app.post("/api/osint/fetch", status_code=201)
def osint_fetch(req: OsintFetchRequest) -> dict:
    """Fetch web page(s) as osint evidence: {url} for one page, or {keyword}
    for a Google News RSS search whose top results are each fetched."""
    if bool(req.url) == bool(req.keyword):
        raise HTTPException(
            status_code=400, detail="provide exactly one of 'url' or 'keyword'"
        )
    if req.keyword:
        try:
            targets = search_news(req.keyword.strip())
        except OsintFetchError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    else:
        targets = [req.url.strip()]

    created: list[dict] = []
    failures: list[dict] = []
    with SessionLocal() as session:
        for target in targets:
            try:
                page = fetch_url(target)
                artifact = _store_osint_page(session, page["markdown"], page["final_url"])
                session.commit()
                created.append(artifact_to_dict(artifact))
            except OsintFetchError as exc:
                session.rollback()
                failures.append({"url": target, "reason": str(exc)})
            except Exception:
                session.rollback()
                raise
    if not created:
        reasons = "; ".join(f["reason"] for f in failures) or "no pages fetched"
        raise HTTPException(status_code=422, detail=reasons)
    return {"artifacts": created, "failures": failures}

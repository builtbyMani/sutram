# 01-CONTEXT.md — Phase 1: walking-skeleton

**Phase goal:** Monorepo scaffold (Next.js + FastAPI) with the evidence data model, an ingest API, a minimal upload UI, and one real end-to-end flow (upload → store → list).

## Locked decisions

- **D-01** — Monorepo layout: `apps/web` (Next.js App Router + Tailwind), `apps/api` (FastAPI), `packages/` for shared types if needed. One repo, one `docker-compose.yml` at root.
- **D-02** — Next.js talks to FastAPI over HTTP; no Next.js API routes for forensics work (Python owns all of it). CORS locked to the web origin in dev; same-origin via compose networking for the demo.
- **D-03** — Evidence schema (unified, from day one — later phases only add columns/tables, never redesign):
  `artifacts(id, source_type, filename, sha256, ingest_ts, metadata_json)` and
  `entities(id, artifact_id, kind, value, span_json)`. SQLite via SQLAlchemy.
- **D-04** — Tracer slice for this phase: upload a file in the UI → FastAPI stores it + computes SHA-256 → UI lists it with its hash. The tracer must be verified working before any expansion task.
- **D-05** — Docker Compose runs both services for the demo; local dev may run them directly. Compose is the source of truth for "it works".
- **D-06** — No auth in v0.1 (single-investigator local tool). Noted as a deliberate scope cut, not an oversight.

## Scope fences

- IN: scaffold, schema + migrations, ingest endpoint, upload UI, artifact list UI, compose setup, README with run instructions.
- OUT: extraction NLP (Phase 2), graph/timeline UI (Phases 3–4), findings/summaries (Phase 5). The list UI shows stored fields only — no analysis yet.

## Deferred ideas

- Postgres migration path; S3-style object storage for large media; case management (multi-case support).

## Items left to researcher/planner discretion

- Exact Next.js + Tailwind versions and scaffold method; SQLAlchemy sync vs async; file storage layout on disk (by hash prefix recommended).

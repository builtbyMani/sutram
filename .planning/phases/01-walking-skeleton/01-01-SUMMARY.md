# 01-01-SUMMARY.md — Phase 1 wave-1 tracer (execution record)

**Phase:** 01-walking-skeleton · **Plan:** 01-01 (tracer slice) · **Date:** 2026-10-19
**Commit:** `958a69b` — "Phase 1 wave-1 tracer: Next.js + FastAPI evidence-intake scaffold (upload -> SHA-256 -> store -> list)"

## What was built

Monorepo at `~/workspace/sutram-forensics/`:

- `apps/web/` — Next.js 16.4.2 (App Router, TypeScript, Tailwind v4, `src/` layout) via `create-next-app@latest`. `next.config.ts`: `cacheComponents: false` + env-driven rewrites `/api/:path*` → `${API_URL}/api/:path*` (`API_URL` server-only, defaults to `http://localhost:8000`). `src/app/page.tsx`: upload form (file + source-type select) and artifact list (filename, source type, truncated sha256, ingest time, size). No analysis UI — stored fields only.
- `apps/api/` — FastAPI 0.148.0 + SQLAlchemy 2.1.5 (sync) + SQLite in WAL mode. Models exactly per D-03 (`artifacts`, `entities`). Endpoints: `GET /health`, `POST /api/artifacts` (multipart → SHA-256 → content-addressed blob at `data/<2-hex>/<sha256>` → DB row; idempotent on re-upload of identical bytes), `GET /api/artifacts` (newest first). `CORSMiddleware` locked to `http://localhost:3000` as backup. `requirements.txt` pinned.
- `docker-compose.yml` + Dockerfiles (`python:3.12-slim`, `node:22-alpine`); `web` gets `API_URL=http://api:8000`, `depends_on` api healthy; api healthcheck via stdlib urllib (slim image has no curl).
- `README.md` (compose + local-dev instructions), `.gitignore` (data/, venv, node_modules, .next).

## Deviations from CONTEXT.md / STACK.md

1. **`--no-cache-components` CLI flag does not exist** in this `create-next-app` version (scaffold emitted `cacheComponents: true`). Equivalent achieved via `cacheComponents: false` in `next.config.ts`, per the installed Next.js 16.4 docs (`node_modules/next/dist/docs/.../cacheComponents.md`). `partialPrefetching` omitted (docs: unset behaves like `false`; no warning when Cache Components is off).
2. **Rewrite destination bug caught by the tracer:** first wrote `destination: ${API_URL}/:path*`, which proxied `/api/artifacts` → `http://localhost:8000/artifacts` (404 from uvicorn — `:path*` captures only the part after `/api/`). Fixed to `${API_URL}/api/:path*`. This is exactly the failure class the tracer slice exists to catch.
3. **Docker not available in this environment** — verification ran both services directly (uvicorn + `next dev`) instead of `docker compose up --build`. Compose file was YAML-validated and its env/depends_on/healthcheck values asserted programmatically, but a real `compose up` cold-start was NOT exercised here.

## Acceptance self-check (all with evidence)

- [x] **Tracer: upload → store → list end-to-end.** `curl -F` POST to `http://localhost:3000/api/artifacts` (through the Next.js rewrite) → 201 with artifact JSON; `GET /api/artifacts` lists it. Page at `http://localhost:3000/` renders "SUTRAM Forensics Workbench" (200).
- [x] **ING-01** — multipart upload of multiple types accepted (tested `.txt` as `chat_export` and `document`).
- [x] **ING-02** — every artifact got id, source-type label, ingest timestamp (UTC ISO-8601): rows `1 evidence-sample.txt chat_export`, `2 evidence-sample2.txt document`, newest first.
- [x] **EXT-03 (schema only)** — `artifacts(id, source_type, filename, sha256, ingest_ts, metadata_json)` and `entities(id, artifact_id, kind, value, span_json)` created exactly; no redesign will be needed.
- [x] **SHA-256 integrity** — `sha256sum` of the source file matched the API-returned hash for both uploads (`e5217609…`, `c21d3366…`); stored blob re-hashed on disk matches.
- [x] **WAL mode** — `PRAGMA journal_mode` → `wal`.
- [x] **TypeScript** — `npx tsc --noEmit` clean.
- [x] **One atomic commit** — `958a69b`, 45 files.

## Notes for the next wave

- The Next.js dev server picks up `next.config.ts` rewrite changes without restart (verified: fix applied live).
- `apps/api/data/` is runtime state (gitignored); the demo seed case (Phase 6) will populate it via the API, not via fixtures.
- Open: real `docker compose up --build` cold-start verification needs a Docker host (unavailable here).

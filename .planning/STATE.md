# STATE.md — SUTRAM Forensics Workbench

**Status:** executing
**Milestone:** v0.1 "PoC"
**Current phase:** 2 — extraction-integrity (executor dispatched)
**Last update:** 2026-10-19 — Phase 1 tracer VERIFIED by parent (independent live check: /health ok, upload → 201, sha256 matched independent sha256sum, listing newest-first, on-disk blob re-hash matched, WAL confirmed). Contract alignment: plans' /api/v1/* routes rewritten to the built /api/* routes; GET /api/artifacts/{id} added to Phase 2 Task 2.1 (didn't exist). Phase 2 executor dispatched per amended 02-01-PLAN.md.

## Position

- [x] GSD skill installed and adapted to this environment
- [x] PROJECT.md / REQUIREMENTS.md / ROADMAP.md written
- [x] Phase 1 discuss complete (decisions D-01…D-07 locked)
- [ ] Phase 1 research (researcher subagent)
- [ ] Phase 1+ plan (planner subagent → PLAN.md files)
- [x] Phase 1 tracer build dispatched (executor subagent, from 01-CONTEXT.md directly per user's "start building")
- [ ] Verify tracer end-to-end, then present plan + continue phase 2–6 execution

## Accumulated decisions

- Frontend: Next.js (App Router) + Tailwind (user-locked 2026-10-19; supersedes earlier React/Vite mapping)
- Backend: FastAPI (Python) for the ML/forensics stack
- DB: SQLite; correlation: NetworkX + sentence-transformers (no Neo4j)
- Explainability: per-finding provenance + Gemini Flash cited summaries + append-only audit log
- Tracer-first planning; Docker Compose for the finale demo

## Open questions for the user (do not block planning)

1. Solo build or team of 2–4? (affects how phases parallelize)
2. SUTRAM registration + idea PPT status — rulebook deadline (5 Oct) has passed; verify on the IVP portal
3. Deepfake detection: pretrained HF model vs heuristics-only (8 GB RAM, no GPU)

## Session notes

- 2026-10-19: User asked for GSD install + full planning with Next.js frontend, plan presented before execution. npx installer has no runtime for this environment → installed GSD as an adapted custom skill instead. If the user wants /gsd-* inside Antigravity IDE, they can run `npx @opengsd/gsd-core@latest --antigravity --global` there themselves.

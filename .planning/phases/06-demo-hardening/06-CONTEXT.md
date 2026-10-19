# 06-CONTEXT.md — Phase 6: demo-hardening

**Phase goal:** Seed the full cyber-fraud demo case, harden the Docker Compose one-command startup, and produce the demo runbook.

## Locked decisions

- Inherited: full schema contract from 01–05 CONTEXT.md; no schema changes in this phase (seed data only).
- **[PROPOSED]** Demo case "Operation Ledger" (cyber-financial fraud): ~50 artifacts across 5 sources — 12 WhatsApp-style chat exports (`.txt`), 10 screenshots (Pillow-generated images with overlaid text), 8 bank-statement images, 12 auth log files, 5 pcap summaries (packet-count + time-range metadata), 3 deliberately tampered images (one edited amount → ELA flag, one stripped EXIF, one AI-face candidate for the deepfake path). Generator script: `apps/api/app/seeds/generate_demo_case.py` (deterministic, seeded RNG).
- **[PROPOSED]** Seeding: `docker compose exec api python -m app.seeds.seed_demo` ingests all fixtures through the real upload path (no direct DB writes — the demo exercises the production pipeline).
- **[PROPOSED]** Models baked into the API Docker image at build time (STACK.md pitfall #3): `en_core_web_sm` via `python -m spacy download`, `all-MiniLM-L6-v2` pre-downloaded via `sentence-transformers` cache priming, `tesseract-ocr` via apt. Deepfake model: Dockerfile attempts the HF download but tolerates failure (`|| true`); runtime lazy-loads from local path if present, else heuristics (per 05-CONTEXT.md).
- **[PROPOSED]** One-command startup: `docker compose up --build -d` → healthchecks + `depends_on` → seed → demo ready. Cold-start budget: **under 5 minutes** end-to-end on the MacBook Air (DEM-01/DEM-02).
- **[PROPOSED]** Demo runbook at `docs/DEMO-RUNBOOK.md`: timed presenter script (upload → graph → timeline → findings → summary), fallback lines for offline mode, and a pre-flight checklist.
- **[PROPOSED]** NFR-01 validation: the runbook is executable by a non-technical reader using only the UI — verified by a dry-run walkthrough against the checklist.

## Scope fences

- IN: fixture generator, seed path, Dockerfile/compose hardening, build-time model baking verification, runbook, cold-start timing test, dry-run.
- OUT: new product features. No changes to application code except compose/Dockerfile/seed scripts (fix only what the timing test proves broken).

## Deferred ideas

- Hosted demo URL; recorded backup demo video; multi-case demo datasets.

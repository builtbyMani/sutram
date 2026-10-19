# ROADMAP.md — SUTRAM Forensics Workbench

## Milestone v0.1 — "PoC" (finale-ready prototype)

**Goal:** A working investigator's workbench that demos end-to-end on a seeded cyber-fraud case. Judging weights drive phase priority: explainability 25%, correlation 20%, timeline 20%, demo 20%.

| # | Phase | Goal (one sentence) | Requirement IDs | Success criteria |
|---|---|---|---|---|
| 1 | walking-skeleton | Monorepo scaffold (Next.js + FastAPI) with the evidence data model, an ingest API, a minimal upload UI, and one real end-to-end flow (upload → store → list). | ING-01, ING-02, EXT-03 (schema only) | `docker compose up` serves the UI; uploading a file stores it in SQLite and lists it back. |
| 2 | extraction-integrity | Wire the extraction pipeline (entity extraction, OCR, metadata), the integrity layer (SHA-256 at ingest, chain-of-custody log), and OSINT web collection. | ING-03, ING-04, EXT-01, EXT-02, EXT-03, INT-01, INT-02 | Uploading a chat export + an image yields entities, OCR text, EXIF, hashes, and custody entries — all visible via API; a fetched web page appears as an `osint` artifact with entities extracted. |
| 3 | correlation-engine | Build the entity-resolution + evidence-graph engine and its interactive UI visualization. | COR-01, COR-02, COR-03 | Two sources mentioning the same person by different name forms resolve to one node; the graph renders and node-click lists artifacts. |
| 4 | timeline | Normalize timestamps to UTC and ship the unified chronological timeline view. | TML-01, TML-02 | Timeline renders all case events in order; event-click opens the source artifact. |
| 5 | explainability-fraud | Ship findings with full provenance, the audit trail, AI case summaries with citations, plus media-tamper signals, pulse-liveness deepfake check, and log anomaly scoring. | EXP-01, EXP-02, EXP-03, FRD-01, FRD-02, FRD-03, ANO-01, NFR-02 | Every rendered finding shows its artifacts, rule, confidence, and snippet; summary cites artifact ids; tampered image is flagged; video with a real face scores strong pulse SNR while synthetic/no-pulse video is flagged with provenance; anomalous logins are scored with reasons. |
| 6 | demo-hardening | Seed the full cyber-fraud demo case, harden the Docker Compose one-command startup, and produce the demo runbook. | DEM-01, DEM-02, NFR-01 | Cold start → full demo narrative in < 5 min on a fresh machine; a non-technical user can follow the runbook. |

**Phase ordering rationale:** skeleton first (tracer proves the architecture), then data pipeline, then the two heaviest judging criteria (correlation, timeline), then explainability + fraud (needs all upstream data), then demo hardening last when everything exists to seed.

**Deferred (not in v0.1):** raw disk-image parsing, Neo4j, mobile app, multi-user cases, live forensics.

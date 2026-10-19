# SUTRAM 2026 — Idea Submission PPT Content

Markdown source for the idea deck. Follows the official `SUTRAM_2026_Idea_Submission_Template.pptx` section order exactly (slides 1–7 content; slide 8 is the instructions slide — delete it before exporting to PDF). Max 10 slides: this deck uses 7.

> Team names are marked **[TEAM TBD]** throughout — fill in before submitting.

---

## Slide 1 — Title

- **Idea title:** SUTRAM Forensics Workbench — an AI-powered digital forensics investigation framework
- **Problem statement:** "Building an AI-Powered Indigenous Digital Forensics Investigation Framework" (the SUTRAM 2026 problem statement)
- **Theme:** AI-Powered Digital Investigation, Incident Response & Cyber Forensics Technologies
- **Team:** [TEAM TBD]

*Speaker note: one line that frames the whole pitch — "an investigator's workbench that turns a pile of multi-source evidence into an explainable case."*

---

## Slide 2 — Team Details

| # | Role | Name | Branch / Year | Email | Phone |
|---|------|------|---------------|-------|-------|
| 01 | Team Leader | [TEAM TBD] | [TEAM TBD] | [TEAM TBD] | [TEAM TBD] |
| 02 | Member | [TEAM TBD] | [TEAM TBD] | [TEAM TBD] | [TEAM TBD] |
| 03 | Member (if applicable) | [TEAM TBD] | [TEAM TBD] | [TEAM TBD] | [TEAM TBD] |
| 04 | Member (if applicable) | [TEAM TBD] | [TEAM TBD] | [TEAM TBD] | [TEAM TBD] |

*(Template says: fill only the cards you need, delete the rest.)*

---

## Slide 3 — Idea Title / Proposed Solution

**The problem**
- Investigators drown in multi-source evidence — chats, logs, images, video, pcaps, web pages — stitched together manually, case by case
- Deepfake and AI-generated fraud are surging; existing tools are single-source and give black-box answers a court cannot trust
- No indigenous, end-to-end framework covers the full lifecycle: collect → authenticate → correlate → reconstruct → explain

**Proposed solution — SUTRAM Forensics Workbench**
- A web-based investigator's workbench: upload evidence (or paste a URL / keyword for OSINT collection) → the framework extracts, authenticates, correlates, and reconstructs the case
- Every artifact is SHA-256 hashed at ingest with an append-only chain-of-custody log
- Entities resolve across sources into one interactive evidence graph ("M. Sharma" + same phone number in two chats → one identity)
- All events land on a unified UTC crime timeline; every finding carries its provenance — artifact ids, the rule/model, confidence, evidence snippet

**Innovation / uniqueness**
- **Explainability-by-design:** a hard gate — no finding is ever rendered without provenance (the 25%-weighted judging criterion, built into the architecture)
- **Pulse-liveness deepfake signal:** remote photoplethysmography (skin green-channel → detrend → 0.7–4 Hz → FFT) — a real face shows a strong periodic pulse, a synthetic face shows none; calibrated SNR thresholds, always reported as a supporting signal, never as proof
- **OSINT collection built in:** Scrapling-powered web fetching (robots.txt obeyed) so open-source evidence is never missed
- Indigenous stack, runs on commodity CPU-only hardware — no foreign black-box dependency

*Speaker note: land the one-liner — "black-box tools say *what*; ours shows *why*, with every claim traceable to its source artifact."*

---

## Slide 4 — Technical Approach

**Architecture**
- Frontend: Next.js (App Router) + Tailwind CSS — investigator dashboard (upload, evidence graph, timeline, findings)
- Backend: FastAPI (Python) — all forensics/AI work lives here; frontend proxies same-origin (no CORS failure modes)
- Store: SQLite evidence DB (artifacts, entities, identities, relations, events, findings, audit log) — zero-infra, portable
- Demo packaging: Docker Compose — one command starts the full stack with all models baked in

**Pipeline (with AI components mapped to judging criteria)**
1. **Collect** — file upload (documents, chats, logs, images, video, pcaps) + OSINT URL/keyword fetch → *Evidence extraction 15%*
2. **Extract** — spaCy NER (people, phones, emails, IPs, URLs) + Tesseract OCR + EXIF metadata, one unified schema
3. **Authenticate** — SHA-256 at ingest (immutable), append-only chain-of-custody + audit log
4. **Correlate** — sentence-transformers embeddings for fuzzy entity resolution + NetworkX evidence graph, interactive UI → *Cross-source correlation 20%*
5. **Reconstruct** — timestamps normalized to UTC, unified chronological timeline (event-click → source artifact) → *Timeline reconstruction 20%*
6. **Detect fraud** — ELA + EXIF tamper flags, deepfake model score (lazy-load, heuristic fallback), rPPG pulse-liveness, IsolationForest log anomalies → *Multimedia/fraud analysis 10%*
7. **Explain** — findings with full provenance, Gemini case summaries with inline `[artifact:id]` citations, append-only audit trail → *Accuracy/traceability/explainability 25%*
- UI-only workflow for a non-technical investigator; seeded cyber-fraud demo case runs end-to-end in < 5 minutes → *Performance/usability 10%, Presentation/demo 20%*

**Methodology**
- 6-phase build plan (skeleton → extraction → correlation → timeline → explainability → demo hardening), tracer-first: each phase proves a thin end-to-end slice before expanding
- Offline-capable by design: models baked into the Docker image, graceful degradation with no network

*Speaker note: if showing the pipeline, walk it left-to-right on the demo case — "a chat, a bank screenshot, and a video walk in; a cited case summary walks out."*

---

## Slide 5 — Feasibility and Viability

**Why it is feasible**
- Every library is validated and version-pinned: spaCy, sentence-transformers (all-MiniLM-L6-v2, ~90 MB), scikit-learn, Tesseract, Scrapling, Next.js 16, FastAPI
- Runs on CPU-only commodity hardware (8 GB RAM, no GPU) — small models or API-based LLM, nothing exotic
- Walking-skeleton tracer already built and verified: upload → hash → store → list works end-to-end

**Risks and mitigations**
- *Unreliable venue network* → offline-first design: all models baked into the Docker image; demo uses a pre-seeded case; AI summaries degrade gracefully
- *Heavy deepfake model* → lazy-load with timeout; ELA + EXIF heuristics always available; scores are never fabricated
- *Scraping defensibility* → robots.txt obeyed, fetch provenance (URL, timestamp, fetcher) stored per artifact
- *Short build window* → phased plan with per-phase acceptance criteria; explicit cut list (raw disk imaging, Neo4j, mobile app deferred)

**Roadmap to the finale**
- Now → walking skeleton (built, verified)
- Early Nov → extraction pipeline + correlation engine
- Mid Nov → timeline + explainability/fraud modules; prototype + PPT submission (20 Nov)
- Dec → top-25 selection (5 Dec); finale 26–27 Dec with a timed <5-minute demo runbook

*Speaker note: feasibility is the "why should the jury believe you" slide — anchor on the verified tracer and the baked-model offline demo.*

---

## Slide 6 — Impact and Benefits

- **Investigators:** hours of manual evidence-stitching collapse to minutes; every conclusion traceable to source artifacts — reasoning a court can follow
- **Agencies:** an indigenous framework under the ISEA vision — no dependence on foreign black-box forensic tools; runs on hardware they already have
- **Society:** faster resolution of cyber-financial fraud and deepfake-enabled crime; deterrence through better attribution
- **Economics:** near-zero infra cost (SQLite, CPU-only models, open-source stack); the framework pattern generalizes to incident response beyond forensics

*Speaker note: close on the citizen — "every week a deepfake scam goes unsolved for lack of tooling; this is tooling built for that week."*

---

## Slide 7 — Research and References

- SUTRAM 2026 rulebook & evaluation criteria — sutram2026.com (problem statement, judging weights)
- Scrapling (D4Vinci/Scrapling, BSD-3-Clause) — Python web-scraping framework for the OSINT collection module
- spaCy (industrial-strength NLP) — named-entity extraction; sentence-transformers `all-MiniLM-L6-v2` — entity embeddings
- scikit-learn `IsolationForest` — log anomaly detection
- react-force-graph-2d, vis-timeline — evidence graph and timeline UI
- Remote photoplethysmography (rPPG): green-channel skin-signal method (Verkruysse et al. baseline); CHROM / POS noted as future work — our calibrated SNR thresholds (≥12 real / 6–12 inconclusive / <6 synthetic) measured on prototype self-tests
- Error Level Analysis (ELA) — standard image-tampering forensic technique
- Next.js 16 + FastAPI + SQLite + Docker Compose — application stack (versions pinned per project research)

---

*Slide 8 of the template is the instructions slide — delete it before exporting to PDF per the template's own note.*

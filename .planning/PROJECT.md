# PROJECT.md — SUTRAM Forensics Workbench

## Identity

**Working title:** SUTRAM Forensics Workbench (product name TBD)
**What:** An AI-powered digital forensics investigation framework — an investigator's workbench web app that collects, analyses, authenticates, and correlates digital evidence from multiple sources.
**Why:** Built for SUTRAM Hackathon 2026 (IGDTUW Delhi, under MeitY ISEA Phase-III). Theme: AI-Powered Digital Investigation, Incident Response & Cyber Forensics Technologies.
**Who it's for:** Cyber-crime investigators and forensic analysts who today stitch together evidence manually across disk images, logs, chats, pcaps, and media.

## Core value

Turn a pile of multi-source evidence into an explainable case: every artifact hashed and traceable, entities correlated across sources into one evidence graph, a unified crime timeline, and AI-generated findings where every claim cites its source artifacts. The 25%-weighted judging criterion is **accuracy, traceability, and explainability** — the product is designed around it.

## Problem statement (verbatim, sutram2026.com)

> Develop an AI-powered digital forensics investigation framework capable of collecting, analysing, authenticating, and correlating digital evidence from multiple sources. The framework should assist investigators in efficiently handling complex digital evidence, identifying patterns and anomalies, verifying evidence integrity and origin, detecting fraud and manipulation, and reconstructing incidents from correlated evidence.

## Constraints

- **Hackathon rules:** all ideas and work must be original; plagiarism = disqualification. AI tools only as permitted — the core idea and technical work must be the team's own. Jury decision is final.
- **Timeline:** Round 1 results 25 Oct 2026 → prototype/PPT submission 20 Nov 2026 → top 25 selected 5 Dec 2026 → finale 26–27 Dec 2026 (IGDTUW, Delhi). Registration + idea PPT deadline was 5 Oct 2026 (verify registration status on the IVP portal — assumed registered).
- **Demo reality:** the finale demo must run end-to-end in under ~5 minutes on hardware we control. Everything must work offline-ish (no reliance on flaky venue network beyond a local stack).
- **Build machine:** MacBook Air 2020, Intel i3, 8 GB RAM — no GPU. Heavy models must be small or API-based.

## Key decisions (locked)

- D-01: Frontend is **Next.js (App Router) + Tailwind CSS** (user decision, 2026-10-19).
- D-02: Backend is **FastAPI (Python)** — the ML/forensics stack (spaCy, NetworkX, scikit-learn) requires Python; Next.js talks to it over HTTP.
- D-03: **SQLite** for the evidence store — zero-infra, portable finale demo. Postgres only if scale demands it.
- D-04: Correlation via **NetworkX + sentence-transformers**; no Neo4j (deployment pain buys no judging marks).
- D-05: Explainability via **per-finding provenance** (artifact ids, rule/model, confidence, evidence snippet) + **Gemini Flash** case summaries with inline citations + append-only audit log.
- D-06: **Tracer-first** planning — every phase leads with a thin end-to-end slice before expansion.
- D-07: Finale demo ships as **Docker Compose** (Next.js + FastAPI + seeded case data).

## Non-goals (for the PoC)

- Raw disk-image acquisition/parsing (accept extracted file sets instead).
- A mobile app; multi-user/case collaboration; production hardening.
- Real-time live forensics on running systems.

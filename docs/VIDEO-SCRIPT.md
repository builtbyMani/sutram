# SUTRAM 2026 — Submission Video Script (~2.5 min)

Narration + exact screen actions. Record at 1080p, app at full-window.
Seeded "Operation Ledger" case is already loaded (49 artifacts).

---

## 0:00–0:20 — The problem (face camera or title card)

**Say:**
"Every cyber-fraud case dumps the same mess on an investigator's desk —
dozens of chat exports, bank screenshots, login logs, a suspicious video.
Today that gets stitched together by hand, and the new wave of AI-generated
fakes makes it worse. Existing tools look at one source at a time, and give
black-box answers no court can trust."

**Show:** title card — "SUTRAM Forensics Workbench".

## 0:20–0:40 — The idea (app home page)

**Say:**
"We built the SUTRAM Forensics Workbench — an AI-powered investigation
framework. Upload evidence, or pull it from the web — and it extracts,
authenticates, correlates, and reconstructs the case, with every single
conclusion traceable to its source."

**Show:** home page. Upload one chat file; point at the SHA-256 hash —
"every artifact is hashed at ingest, with an append-only chain-of-custody log."

## 0:40–1:10 — Correlation (graph page)

**Say:**
"Forty-nine artifacts from a simulated fraud case are already in. The engine
extracts people, phones, emails, IPs — then resolves identities across
sources. 'M. Sharma' in one chat and 'Manish Sharma' in another, sharing a
phone number, become one identity. Thirty-one identities, sixty-five
relations — one interactive evidence graph."

**Show:** /graph. Zoom to the merged identity node; click it — drill-down
lists every artifact mentioning that person.

## 1:10–1:35 — Timeline (timeline page)

**Say:**
"Every timestamp — chat messages, log lines, photo metadata — is normalized
to UTC on one chronological timeline. One hundred forty events. Click any
event and you're back at the source artifact it came from."

**Show:** /timeline lanes; click an event → artifact detail page.

## 1:35–2:10 — Fraud findings (findings page)

**Say:**
"Then the fraud modules. Error-level analysis flags the edited bank
statement. Our pulse-liveness check — remote photoplethysmography, the same
principle as my published prototype — reads a real heartbeat, 71.5 BPM,
from the suspect video; a synthetic face shows none. The anomaly detector
catches the 3 AM brute-force logins. Eighteen findings, four types — and
here's the point: no finding renders without provenance. Artifact IDs, the
rule or model, confidence, the evidence snippet. That's the 25%-weighted
explainability criterion, built into the architecture."

**Show:** /findings. Expand one finding of each type; point at the
provenance block.

## 2:10–2:30 — Close (face camera or title card)

**Say:**
"It's an indigenous stack — open source, CPU-only, runs offline with all
models baked in. Black-box tools tell you *what*. Ours shows you *why*,
with every claim traceable to its source. That's the SUTRAM Forensics
Workbench."

---

## Recording notes

- Do the full run-through once before recording (seeded DB persists in
  /tmp/sutram_demo — re-seed if you wipe it: `python -m app.seeds.seed_demo`).
- Keep the cursor slow on the graph and timeline pages.
- If anything lags, the fallback line: "this runs fully offline — let me
  show the findings directly."
- Export ≤ 100 MB for Drive upload; hand the file to Muse to upload +
  generate the shareable link.

# REQUIREMENTS.md — SUTRAM Forensics Workbench

Numbered acceptance criteria. Each maps to roadmap phases in `ROADMAP.md`. Mark complete as phases ship.

## Ingestion (ING)

- **ING-01** — Investigator can upload evidence files of multiple types (documents, images, video, chat exports, logs, pcaps) through the web UI.
- **ING-02** — Every uploaded artifact gets a unique artifact id, a source-type label, and an ingest timestamp.
- **ING-03** — Upload of an unsupported/corrupt file fails gracefully with a clear message; the case remains usable.
- **ING-04** — Investigator can submit a webpage URL (or a keyword query) for OSINT collection: the system fetches the page with Scrapling's HTTP Fetcher (robots.txt obeyed), stores its cleaned text as an `osint` artifact carrying the source URL, fetch timestamp, and fetcher identity in `metadata_json`, and runs the standard extraction pipeline over it.

## Extraction (EXT)

- **EXT-01** — Text-bearing artifacts (documents, chat exports, logs) yield extracted entities: people, phone numbers, emails, IPs, URLs.
- **EXT-02** — Images yield OCR text and EXIF metadata where present.
- **EXT-03** — Every artifact's extracted data is stored against a single unified evidence schema (artifact id, source, timestamp, entities, hash).

## Integrity & chain of custody (INT)

- **INT-01** — SHA-256 hash is computed at ingest for every artifact and stored immutably.
- **INT-02** — An append-only chain-of-custody log records every touch of an artifact (ingest, view, analysis run).

## Correlation (COR)

- **COR-01** — Entities are resolved across sources into canonical identities (fuzzy matching: e.g. "M. Sharma" + same phone number in two chat exports → one identity).
- **COR-02** — An evidence graph links entities via shared identifiers and co-occurrence, rendered as an interactive graph in the UI.
- **COR-03** — Clicking a graph node shows every artifact that mentions the entity.

## Timeline (TML)

- **TML-01** — All artifact timestamps are normalized to UTC at ingest.
- **TML-02** — A unified chronological timeline view shows case events; clicking an event opens the source artifact.

## Explainability (EXP)

- **EXP-01** — Every finding records: artifact ids behind it, the rule/model that fired, a confidence score, and the exact evidence snippet.
- **EXP-02** — A generated case summary cites artifact ids inline for each claim it makes.
- **EXP-03** — An audit trail lists all system actions on the case in chronological order.

## Fraud & multimedia analysis (FRD)

- **FRD-01** — Images get tamper signals: error-level analysis (ELA) heat indication + EXIF/metadata inconsistency flags.
- **FRD-02** — Faces/media get an AI-manipulation (deepfake) score where a model is available; otherwise heuristic flags only — never a fabricated score.
- **FRD-03** — Video evidence containing faces gets a pulse-liveness signal via remote photoplethysmography (face skin ROIs → green-channel mean → detrend → 0.7–4 Hz bandpass → FFT → BPM + pulse SNR), implemented from the existing prototype at `~/workspace/pulse-detector/pulse_detector.py`. Calibrated thresholds: SNR ≥ 12 supports "real face", 6–12 inconclusive, < 6 supports "possibly synthetic". Always surfaced as a finding with provenance and confidence per NFR-02 — never as proof.

## Anomaly detection (ANO)

- **ANO-01** — Log-derived activity (login times, failed attempts, transfer volumes) is scored for anomalies, shown with the contributing features.

## Demo & packaging (DEM)

- **DEM-01** — A seeded end-to-end demo case (cyber-financial fraud, ~50 artifacts across 4–5 sources) runs ingest → correlate → timeline → findings in under 5 minutes.
- **DEM-02** — The full stack (frontend + backend + seeded data) starts with one command (Docker Compose) on a fresh machine.

## Non-functional (NFR)

- **NFR-01** — An investigator with no CLI experience can go from upload to findings using only the UI.
- **NFR-02** — No finding is ever presented without provenance (hard gate: EXP-01 data must exist before a finding renders).

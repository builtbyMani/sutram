# 02-CONTEXT.md — Phase 2: extraction-integrity

**Phase goal:** Wire the extraction pipeline (entity extraction, OCR, metadata) and integrity layer (SHA-256 at ingest, chain-of-custody log).

## Locked decisions

- Inherited (user-locked, PROJECT.md D-01…D-03): Next.js + FastAPI + SQLite; schema from 01-CONTEXT.md D-03 is the shared contract — this phase only **adds** columns/tables, never redesigns.
- **[PROPOSED]** Extraction runs **synchronously inside the upload request** (single-investigator local tool; no job queue in v0.1).
- **[PROPOSED]** Schema additions: new table `custody_log(id INTEGER PK, artifact_id INTEGER FK → artifacts.id, action TEXT, actor TEXT, ts TEXT /* UTC ISO */, detail TEXT)`; `artifacts` gains `extracted_text TEXT NULL`, `exif_json TEXT NULL`.
- **[PROPOSED]** NER: `spaCy 3.8.16 + en_core_web_sm` for PERSON/ORG; regex extractors for PHONE / EMAIL / IP / URL (STACK.md §5).
- **[PROPOSED]** OCR: Tesseract 5.x via `pytesseract==0.3.13` with preprocessing (grayscale → 2x upscale → Otsu threshold) for `image` source types (STACK.md §7).
- **[PROPOSED]** EXIF/metadata: Pillow for JPEG/PNG EXIF, `exifread==3.5.1` as fallback; stored as JSON in `artifacts.exif_json` (STACK.md table §10).
- **[PROPOSED]** Source-type detection: uploader picks from a dropdown (`document | chat | log | image | video | pcap`) in the upload UI, defaulting to an extension guess map (`.txt/.md/.docx/.pdf`→document, `.json/.csv` chat exports→chat, `.log`→log, `.jpg/.jpeg/.png/.webp`→image, `.mp4/.mov`→video, `.pcap/.pcapng`→pcap).
- **[PROPOSED]** SHA-256 computed streaming during file write at ingest, stored once, never updated (INT-01 immutability).
- **[PROPOSED]** Custody action vocabulary: `ingest | view | extract | analyze`; `actor` = `"investigator"` (no auth per 01-CONTEXT.md D-06).
- **[PROPOSED]** Unsupported/corrupt files: extension allowlist + parse try/except → HTTP 422 with a clear message; nothing is persisted for rejected uploads (ING-03).
- **OSINT collection (user-locked 2026-10-19):** new source type `osint` via `POST /api/v1/osint/fetch` accepting `{url}` or `{keyword}`. URL path: Scrapling HTTP `Fetcher` (no browser engine in v0.1 — deferred for Docker image weight), `robots_txt_obey=True`, 15 s timeout; cleaned Markdown stored as the artifact text; `metadata_json = {url, fetched_at_utc, fetcher: "scrapling-http"}`. Keyword path: Google News RSS search → top 5 URLs → same fetch pipeline. Fetch failures (DNS/timeout/HTTP ≥400/robots disallow) → 422 with reason, nothing persisted. Fetched pages flow through the standard text extraction pipeline (entities, timestamps). Demo seeds use pre-fetched cached pages (offline-safe); live fetch works when network is available.

## Scope fences

- IN: extraction service module, OCR, EXIF, custody log + its API, graceful upload failure, artifact detail API/UI showing extracted fields, OSINT web collection (URL + keyword), fixture-based verification.
- OUT: entity resolution / identities (Phase 3); graph and timeline UI (Phases 3–4); findings and summaries (Phase 5). Video frame extraction and pcap deep-parsing are out — pcaps get packet-count + time-range metadata only.

## Deferred ideas

- Async background extraction queue; raw disk-image parsing; video frame OCR; audio transcription.

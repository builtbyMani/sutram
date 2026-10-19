# 03-CONTEXT.md — Phase 3: correlation-engine

**Phase goal:** Build the entity-resolution + evidence-graph engine and its interactive UI visualization.

## Locked decisions

- Inherited: schema contract from 01-CONTEXT.md + 02-CONTEXT.md (`artifacts`, `entities`, `custody_log`). This phase only adds tables/columns.
- **[PROPOSED]** Schema additions: `entities` gains `embedding BLOB NULL` (384-dim float32, L2-normalized, written at ingest by the extraction service); new tables `identities(id INTEGER PK, kind TEXT, canonical_value TEXT, merged_entity_ids_json TEXT NOT NULL)` and `relations(id INTEGER PK, identity_a_id INTEGER FK, identity_b_id INTEGER FK, relation_type TEXT, evidence_json TEXT, confidence REAL)`.
- **[PROPOSED]** Resolution rules (STACK.md §6): deterministic merge on exact normalized PHONE/EMAIL/IP match (confidence 1.0); fuzzy merge on PERSON/ORG when cosine similarity ≥ **0.85** (confidence = cosine). Embeddings from `sentence-transformers==6.1.0` + `all-MiniLM-L6-v2` (torch CPU-only).
- **[PROPOSED]** Relation types: `same_identifier` (two identities share a phone/email/IP) and `co_occurrence` (member entities appear in the same artifact).
- **[PROPOSED]** `POST /api/v1/correlate` is **idempotent**: it clears and rebuilds `identities`/`relations` from current entities.
- **[PROPOSED]** Graph API: `GET /api/v1/graph` returns `{nodes: [...identities...], edges: [...relations...]}`; `GET /api/v1/identities/{id}/artifacts` returns every artifact mentioning the identity (COR-03).
- **[PROPOSED]** Graph UI: `react-force-graph-2d@1.29.2` in a `"use client"` wrapper loaded via `next/dynamic(..., { ssr: false })` (STACK.md §3). Node click → artifact list panel.
- **[PROPOSED]** Canonical value for a merged identity: the longest observed mention (deterministic, explainable).

## Scope fences

- IN: embedding at ingest, correlate endpoint + engine, graph API, interactive graph UI, node→artifacts drill-down, fixture verification of the "M. Sharma / Manish Sharma + same phone" case.
- OUT: timeline (Phase 4), findings (Phase 5). No graph persistence beyond SQLite tables; no Neo4j (PROJECT.md D-04).

## Deferred ideas

- Cross-case identity linking; relation types beyond the two locked ones; ONNX embedding path (STACK.md §6 escape hatch).

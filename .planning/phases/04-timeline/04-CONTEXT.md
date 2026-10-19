# 04-CONTEXT.md — Phase 4: timeline

**Phase goal:** Normalize timestamps to UTC and ship the unified chronological timeline view.

## Locked decisions

- Inherited: schema contract from 01/02/03-CONTEXT.md. This phase only adds tables/columns.
- **[PROPOSED]** Schema addition: `events(id INTEGER PK, artifact_id INTEGER FK → artifacts.id, event_ts_utc TEXT NOT NULL /* UTC ISO */, label TEXT, detail_json TEXT)`. Artifact-level `ingest_ts` (UTC, from Phase 1) is separate from event time.
- **[PROPOSED]** Timestamp extractors per source type: chat line timestamps (`[dd/mm/yyyy, hh:mm]` / `yyyy-mm-dd hh:mm:ss` patterns), EXIF `DateTimeOriginal`, leading ISO timestamps on log lines, pcap time-range endpoints. Artifacts with no extractable event time produce no `events` row (never fabricated).
- **[PROPOSED]** Normalization rule: naive timestamps are assumed **Asia/Kolkata** (demo case is India-context) and converted to UTC; timestamps with explicit offsets are honored. (TML-01)
- **[PROPOSED]** Timeline API: `GET /api/v1/timeline` returns events ordered by `event_ts_utc` with `{id, event_ts_utc, label, source_type, artifact_id}`.
- **[PROPOSED]** Timeline UI: `vis-timeline@8.5.4` + `react-vis-timeline-2@2.1.6`, client-only via `next/dynamic(..., { ssr: false })`, one group lane per `source_type`, click event → opens the artifact detail view (TML-02) (STACK.md §4).
- **[PROPOSED]** This phase also ships the **artifact detail page** (`/artifacts/[id]`): metadata, SHA-256, extracted text, EXIF, entities, custody entries — required as the click target for timeline events and graph node drill-downs.

## Scope fences

- IN: timestamp extraction + UTC normalization, events table, timeline API + UI, artifact detail page, fixture verification of ordering.
- OUT: findings/summaries (Phase 5). No editing of events; timeline is read-only derived data.

## Deferred ideas

- Timezone inference from content; event clustering/deduplication; timeline export (PDF).

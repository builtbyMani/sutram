# TIMELINE-NOTE.md — wiring instructions for `services/timeline.py`

Module built and self-tested (run: `.venv/bin/python -m app.services.test_timeline`
— 6/6 pass). Pure functions, no DB/app imports. This note tells the wiring
agent exactly what to persist and where to call it.

## Function signatures

```python
from app.services.timeline import extract_events

extract_events(artifact: dict) -> list[dict]
# artifact: {"id": int, "source_type": str, "text": str|None,
#            "exif_json": dict|str|None, "metadata_json": dict|str|None}
# returns:  [{"artifact_id": int,
#             "event_ts_utc": str,   # ISO-8601, always UTC, ends "+00:00"
#             "label": str,          # e.g. "Chat — Ravi: transferred 50000…"
#             "detail_json": dict},   # {"kind","line","raw_ts",...} — YOU serialize
#            ...]  # sorted ascending by event_ts_utc; [] if nothing extractable
```

Behavior contract:
- Supported per source type: `chat`/`document`/`log`/`osint` → line timestamps
  (WhatsApp `[dd/mm/yyyy, hh:mm]`, `yyyy-mm-dd hh:mm:ss`, leading ISO on logs);
  `image`/`video` → EXIF `DateTimeOriginal`; `pcap` → time-range endpoints from
  `metadata_json` (`time_range.{start,end}` or `capture_start`/`capture_end`
  or `time_range_start`/`time_range_end`).
- Naive timestamps are assumed **Asia/Kolkata** → UTC; explicit offsets honored.
- **Never fabricates**: no extractable time → no event. One event per line max.
- Invalid dates (Feb 30), garbage lines, and bare dates without a time are skipped.

## `events` table (wiring phase must create — additive only)

Per 04-01-PLAN.md Task 4.1 / 04-CONTEXT.md, add exactly:

```sql
CREATE TABLE events (
    id            INTEGER PRIMARY KEY,
    artifact_id   INTEGER NOT NULL REFERENCES artifacts(id),
    event_ts_utc  TEXT NOT NULL,   -- UTC ISO, e.g. 2026-10-19T03:35:00+00:00
    label         TEXT,
    detail_json   TEXT             -- json.dumps of the detail dict
);
CREATE INDEX ix_events_ts ON events(event_ts_utc);
CREATE INDEX ix_events_artifact ON events(artifact_id);
```

(SQLAlchemy model equivalent is fine; columns must match these names/types.)

## Integration steps

1. **Upload flow** (`POST /api/artifacts`, and `POST /api/osint/fetch`):
   after the Phase-2 extraction step, call
   ```python
   events = extract_events({
       "id": artifact.id,
       "source_type": artifact.source_type,
       "text": artifact.extracted_text,          # may be None
       "exif_json": artifact.exif_json,          # dict, JSON str, or None
       "metadata_json": artifact.metadata_json,  # dict, JSON str, or None
   })
   ```
   then bulk-insert rows with `detail_json=json.dumps(e["detail_json"])`.
   Log a `custody_log` `extract`/`timeline` action as Phase 2 does.
2. **Timeline API**: add `GET /api/timeline` returning events ordered by
   `event_ts_utc` ASC, each as `{id, event_ts_utc, label, source_type, artifact_id}`
   (join `artifacts` for `source_type`).
   > Route note: the parent aligned all plans to `/api/*` (no `/v1` prefix) to
   > match the built Phase-1 routes — use `/api/timeline`, not `/api/v1/timeline`
   > as 04-CONTEXT.md originally said.
3. **Idempotency**: if re-running extraction on an artifact, delete its existing
   `events` rows first (or upsert) so re-uploads don't duplicate.
4. Do NOT edit `timeline.py`'s extractor behavior from the wiring side; file
   bugs against the module instead.

## Verification for the wiring agent (Task 4.1 acceptance)

- Upload the chat + EXIF + log fixtures from the plan; `GET /api/timeline`
  returns ≥5 events sorted ascending, every `event_ts_utc` UTC, chat messages
  in true chronological order (not file order) — the module's self-test
  already proves the extractor half; the wiring half must prove persistence
  and ordering through the API.

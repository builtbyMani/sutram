# INTEGRATION-4.md — Phase 4 wiring: what the integrator must add

Everything in this phase is written and verified in isolation. The integrator
(Phase 2 executor or a dedicated wiring pass) must add the following lines.
Do NOT modify the files below — copy these snippets verbatim.

## 1. `apps/api/app/main.py` — register the events table + timeline router

**CRITICAL ORDERING:** `app.db` runs `Base.metadata.create_all(engine)` at
import time, so `models_phase4` must be imported BEFORE `from .db import ...`.

At the top of `main.py`, insert (order matters):

```python
from . import models_phase4  # noqa: F401  -- must precede .db import so create_all sees the events table
from .db import DATA_DIR, SessionLocal
from .models import Artifact, CustodyLog, Entity
```

After the existing imports, add:

```python
from .routers.timeline import router as timeline_router
```

After `app = FastAPI(...)` (near the other `app.add_middleware` / route setup):

```python
app.include_router(timeline_router)
```

Routes exposed (all `/api`, no `/v1`):
- `POST /api/timeline/extract?artifact_id=N` — (re-)extract events for one artifact
- `POST /api/timeline/extract-all` — (re-)extract events for all artifacts
- `GET /api/timeline` — `{id, event_ts_utc, label, source_type, artifact_id}`,
  ordered by `event_ts_utc` ASC

## 2. Upload flow (in `POST /api/artifacts` and `POST /api/osint/fetch`)

Per TIMELINE-NOTE.md, after the Phase-2 extraction step call
`extract_events({...})` and bulk-insert `Event` rows (the router's
`_persist_events` already implements delete-then-reinsert + custody log —
the upload flow should call it or replicate it). Alternatively, leave
extraction out of the upload path and rely on `POST /api/timeline/extract-all`
(the Timeline UI has an "Extract events (all)" button for the demo).

## Files created by this phase (do not edit; already verified)

| File | What it is | Verification |
|---|---|---|
| `apps/api/app/models_phase4.py` | `Event` model on the shared `Base` (columns: id, artifact_id FK, event_ts_utc, label, detail_json) | columns match TIMELINE-NOTE.md exactly; imports clean |
| `apps/api/app/routers/__init__.py` | package marker | — |
| `apps/api/app/routers/timeline.py` | 3 endpoints; delete-then-reinsert idempotency; custody `extract` log | imports cleanly; routes list correctly |
| `apps/web/src/components/CaseTimeline.tsx` | vis-timeline wrapper, one group lane per source_type, `select` → onSelect(artifactId) | tsc clean, `npm run build` passes |
| `apps/web/src/components/TimelineView.tsx` | data fetch, extract-all button, keyboard/AT fallback table | tsc clean, `npm run build` passes |
| `apps/web/src/components/TimelineLoader.tsx` | "use client" loader holding the `ssr:false` dynamic boundary (Next 16 rejects `ssr:false` in Server Components) | tsc clean, `npm run build` passes |
| `apps/web/src/app/timeline/page.tsx` | server component; `dynamic(..., { ssr: false })` | tsc clean |
| `apps/web/src/app/artifacts/[id]/page.tsx` | artifact detail: metadata, SHA-256, extracted text, EXIF, entities, this artifact's events, custody; clean 404 state | tsc clean |

## Dependencies added

- Python: **none** (timeline.py is stdlib-only).
- npm: `vis-timeline@8.5.4` only (installed; in package.json).

## Deliberate deviation from 04-01-PLAN.md Task 4.3

The plan specified `react-vis-timeline-2@2.1.6` as the React wrapper. Its npm
peer range is `react@^0.14 || ^15.0 || ^16.0` — incompatible with this app's
React 19 (npm refuses to resolve; `--legacy-peer-deps` would install an
unmaintained wrapper against a React it was never built for). Instead,
`CaseTimeline.tsx` drives `vis-timeline@8.5.4` directly (same DataSet API,
same groups, same `select` events, same CSS) inside a `"use client"` component
loaded via `next/dynamic(..., { ssr: false })`. The functional acceptance
criteria (groups per source type, click → artifact detail, SSR-crash gate)
are unchanged and unaffected.

## Full acceptance test (run after step 1+2 are applied)

1. Start the API, upload the 3 fixtures from the plan (out-of-order chat,
   EXIF image, ISO-timestamped log).
2. `POST /api/timeline/extract-all` → events > 0.
3. `GET /api/timeline` → ≥5 events, strictly ascending, every `event_ts_utc`
   ending `+00:00`, chat messages in true chronological order.
4. Re-run extract-all → same event count (idempotent, no duplicates).
5. `cd apps/web && npm run build` → exit 0 (SSR-crash gate for vis-timeline).
6. In dev: /timeline renders lanes; click an event → /artifacts/{id} with
   matching id; /artifacts/999999 shows the not-found state.

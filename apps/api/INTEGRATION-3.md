# INTEGRATION-3.md — Phase 3 wiring integration steps

Phase 3 is built and verified. The router and tables live in their own
files (boundaries: `main.py`, `models.py`, `db.py` untouched). One agent —
ideally the Phase 2 executor, since it already owns `main.py`/`models.py` —
must apply the edits below.

## 1. `apps/api/app/models.py` — 1-line edit (bottom of file)

```python
from . import models_phase3  # noqa: F401 — registers identities + relations on Base
```

Why: `app/db.py` runs `Base.metadata.create_all(engine)` at import; the
`identities`/`relations` tables must be registered on `Base` by then.
(`models_phase3.py` imports `Base` from `app.models`, so the bottom-of-file
import is not circular — verified in the smoke test.)

## 2. `apps/api/app/main.py` — 3-line edit

Add near the other imports:

```python
from app.routers.correlation import router as correlation_router
```

Add after `app = FastAPI(...)` (before or after the CORS middleware — either works):

```python
app.include_router(correlation_router)
```

Routes served: `POST /api/correlate`, `GET /api/graph`,
`GET /api/identities/{id}/artifacts`.

## 3. `requirements.txt` — pip deps (verified versions)

Install **torch CPU first**, or pip pulls the CUDA build:

```
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install sentence-transformers==6.1.0
```

Verified working: `torch 2.14.1+cpu` + `sentence-transformers 6.1.0`.
(Both are already installed in `apps/api/.venv` from module testing.)

## 4. Dockerfile — prime the HF model cache at build time

No runtime download is allowed: `services/correlation.py` raises
`RuntimeError` if `all-MiniLM-L6-v2` cannot load. Add to the API image build:

```dockerfile
RUN env -u no_proxy -u NO_PROXY python -c \
  "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

The `env -u` wrapper is load-bearing in this sandbox (and possibly at the
venue): the `no_proxy`/`NO_PROXY` vars here contain bracketed IPv6 literals
(`[::1]`) which crash this httpx version with `InvalidURL: Invalid port: ':1]'`
when huggingface_hub builds its client. Runtime API is unaffected once the
model is baked in.

## 5. Web

- `npm i -S react-force-graph-2d@1.29.2` — already installed in `apps/web`.
- `/graph` page added (`apps/web/src/app/graph/page.tsx` + `EvidenceGraph.tsx`
  + `EvidenceGraphLoader.tsx`).
- **Next 16 gotcha (fixed here):** `next/dynamic(..., { ssr: false })` is
  rejected in Server Components on Next 16. The working pattern is:
  Server-Component page → imports a `"use client"` loader → loader holds the
  `ssr: false` dynamic boundary. **The Phase 4 `/timeline` page has the same
  bug** (`src/app/timeline/page.tsx` still fails `npm run build` with this
  error) — its owner must apply the same loader pattern.

## Verified state (2026-10-19)

- Router imports clean; routes: `POST /api/correlate`, `GET /api/graph`,
  `GET /api/identities/{id}/artifacts`.
- `models_phase3` registers `identities` + `relations` on `Base.metadata`.
- `npx tsc --noEmit`: zero errors in Phase 3 files.
- `npm run build`: `/graph` route builds (only `/timeline` — Phase 4's file —
  still errors).
- End-to-end smoke (`/tmp/p3_smoke.py`, throwaway DB): fixture pair
  ("M. Sharma" + "Manish Sharma", same phone 9876543201) → `POST /api/correlate`
  yields 2 identities (1 merged PERSON + 1 PHONE) + 1 relation; `GET /api/graph`
  shows one PERSON node with `artifact_count: 2`; second correlate run is
  identical (idempotent); drill-down returns both artifacts; unknown identity
  → 404. All passed.

## Notes for the demo

- `POST /api/correlate` is safe to re-run any time (clear-and-rebuild,
  deterministic resolver output).
- Tolerates the `entities.embedding` column being absent (Phase 2's additive
  column): falls back to re-encoding at correlate time. If the column exists,
  stored ingest-time embeddings are reused via the resolver's `embedding` key.
- The fixture merge above completed in ~2 s with no model load — deterministic
  identifier-linked merges never touch MiniLM.

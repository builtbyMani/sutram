# SUTRAM Forensics Workbench

AI-powered digital forensics investigation framework — **SUTRAM Hackathon 2026**
(IGDTUW Delhi, under MeitY ISEA Phase-III).

**Problem:** "Building an AI-Powered Indigenous Digital Forensics Investigation Framework"
— collect, analyse, authenticate and correlate multi-source digital evidence;
detect fraud and manipulation; reconstruct incidents.

**What it does:** upload evidence (documents, chat exports, logs, pcaps, images,
video) or fetch web sources via built-in OSINT collection → the framework extracts
entities (spaCy NER + OCR + EXIF), resolves identities across sources into an
interactive evidence graph, normalizes every timestamp to UTC on one chronological
timeline, and runs fraud modules (ELA + EXIF tamper flags, deepfake scoring,
**rPPG pulse-liveness**, IsolationForest log anomalies). Every finding carries full
provenance — artifact IDs, the rule/model, confidence, evidence snippet — and an
append-only audit log records the chain of custody.

## Stack

- **Frontend:** Next.js 16 (App Router) + Tailwind v4 — `apps/web`
- **Backend:** FastAPI + SQLAlchemy 2 (sync) + SQLite (WAL) — `apps/api`
- **AI/ML:** spaCy (`en_core_web_sm`), sentence-transformers (`all-MiniLM-L6-v2`),
  scikit-learn (IsolationForest), Tesseract OCR, Pillow (ELA), OpenCV + MediaPipe
  (rPPG pulse), Scrapling (OSINT fetch), Gemini Flash (cited case summaries)
- The browser talks same-origin to Next.js only; `/api/*` is proxied to FastAPI
  via env-driven rewrites (`API_URL`, server-only).

## Run everything (recommended)

```bash
docker compose up --build
```

- UI: http://localhost:3000
- API: http://localhost:8000 (`/health`, `/api/artifacts`, …)

Models are baked into the API image at build time (MiniLM primed, spaCy model
downloaded); the demo runs fully offline.

## Local dev (no Docker)

Terminal 1 — API:

```bash
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt            # torch CPU first, see requirements.txt
# CPU-only torch (do this BEFORE the rest, or pip pulls CUDA):
pip install torch --index-url https://download.pytorch.org/whl/cpu
python -m spacy download en_core_web_sm
sudo apt-get install tesseract-ocr tesseract-ocr-eng   # OCR binary
uvicorn app.main:app --reload --port 8000
```

Terminal 2 — web:

```bash
cd apps/web
npm install
npm run dev
```

Open http://localhost:3000.

## Seeded demo case ("Operation Ledger")

A deterministic 49-artifact cyber-fraud case lives in
`apps/api/seeds/operation-ledger/` (+ `manifest.json`). Seed it through the API:

```bash
cd apps/api
python -m app.seeds.seed_demo --api-url http://localhost:8000
```

This uploads all artifacts, runs extract → correlate → timeline → media/pulse/
anomaly analysis, and asserts all four finding types
(`shared-identifier-link`, `tampered-media`, `pulse-liveness`, `login-anomaly`).

## API surface

| Method & path | What |
|---|---|
| `GET /health` | liveness |
| `POST /api/artifacts` | upload evidence (multipart; SHA-256 content-addressed, idempotent) |
| `GET /api/artifacts`, `GET /api/artifacts/{id}` | list / detail (+ entities, custody) |
| `POST /api/osint/fetch` | `{url}` or `{keyword}` → web page as `osint` artifact (robots.txt obeyed) |
| `POST /api/correlate` | entity resolution → identities + relations |
| `GET /api/graph` | evidence-graph nodes/edges |
| `POST /api/timeline/extract-all`, `GET /api/timeline` | UTC-normalized event timeline |
| `POST /api/media/{id}/analyze` | ELA + EXIF + deepfake signals |
| `POST /api/media/{id}/pulse` | rPPG pulse-liveness (BPM, SNR, verdict) |
| `POST /api/logs/{id}/anomalies` | IsolationForest over auth sessions |
| `POST /api/analyze`, `GET /api/findings` | findings rebuild / list (provenance-gated) |
| `POST /api/summaries` | Gemini case summary with `[artifact:N]` citations (degrades offline) |
| `GET /api/audit` | append-only audit trail |

## Project layout

```
apps/web/                 Next.js frontend (upload, graph, timeline, findings pages)
apps/api/                 FastAPI backend (app/main.py, routers/, services/, models*.py)
apps/api/seeds/           deterministic demo-case generator + manifest
docs/                     idea-PPT content, demo runbook, video script
.planning/                GSD planning artifacts (phases, requirements, research)
docker-compose.yml        one-command demo stack
```

## Docs

- `docs/idea-ppt-content.md` — Round-1 idea submission deck content (7 slides)
- `docs/DEMO-RUNBOOK.md` — timed <5-minute demo script
- `docs/VIDEO-SCRIPT.md` — submission video narration + screen actions

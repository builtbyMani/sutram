# STACK.md — Technology validation for SUTRAM Forensics Workbench

**Research date:** 2026-10-19
**Method:** versions verified live via `npm view` and `pip index versions` (package registries, checked today), plus web search for current best practices. Training-data memory was not used for any version number.
**Context:** Next.js (App Router) frontend + FastAPI backend + SQLite, single-investigator local tool, build/demo machine is an 8 GB RAM Intel MacBook Air with no GPU, finale demo must cold-start and run end-to-end in < 5 minutes via Docker Compose.

---

## 1. Next.js (App Router) + Tailwind CSS

**Verified versions (2026-10-19):**
- **Next.js 16.4.1** is the latest stable (16.4.0 released 6 Oct 2026; 16.4.1 is an out-of-band security patch from 14 Oct 2026). Ships **React 19.3**. Next.js 15 reaches end-of-life 21 Oct 2026 — do not build on it.
- **Tailwind CSS v4** (v4.3.3 verified in the wild Sept 2026; current patch is 4.3.x — exact latest patch [UNVERIFIED], pin `^4` and let the lockfile hold it). v4 is the default for all new projects; the v3 setup flow (`tailwindcss init -p`, `@tailwind base;` directives) is dead and will silently produce no styles.
- Node requirement: **Node 20.9+** minimum for Next.js 16. Use **Node 22 LTS** in Docker.

**Recommended scaffold:** run `create-next-app@latest` with flags `--typescript --tailwind --app --src-dir --use-npm --eslint` (plus `--no-cache-components`, see pitfalls). This is the current official CLI surface (verified against nextjs.org docs, Oct 2026). The `--tailwind` flag wires Tailwind v4 automatically. Turbopack is the default bundler in Next 16 — no flag needed.

**Tailwind v4 + Next.js mechanics:** install `tailwindcss` + `@tailwindcss/postcss`, set `postcss.config.mjs` to load the `@tailwindcss/postcss` plugin, and put a single `@import "tailwindcss";` line in `app/globals.css`. No `tailwind.config.js`, no `content` array. Theme customization is done in CSS with `@theme`.

**Locked recommendation:** Next.js **16.4.x** (App Router, TypeScript, Tailwind v4 via the `--tailwind` scaffold flag, `src/` layout, Node 22) — because it is the current Active LTS, React 19.3 is bundled, and Turbopack gives fast dev iteration on a slow laptop.

---

## 2. Next.js frontend ↔ FastAPI backend integration

**Pattern (current best practice):** do NOT have the browser call FastAPI directly. Use **Next.js rewrites** so the browser always talks same-origin to Next.js, and the Next.js server proxies `/api/*` to FastAPI. This eliminates CORS as a demo-day failure mode entirely.

- **Local dev:** rewrite destination `http://localhost:8000/:path*` (FastAPI on 8000, Next.js on 3000).
- **Docker Compose:** the browser still hits the Next.js container, but the rewrite destination must be the compose service name — `http://api:8000/:path*`. Drive this with a server-only env var (e.g. `API_URL`) read in `next.config.ts`: compose sets `API_URL=http://api:8000`, local dev defaults to `http://localhost:8000`. Env must NOT be `NEXT_PUBLIC_`-prefixed (that would leak it to the browser and bake the wrong host into client bundles).
- **CORS:** still add FastAPI's `CORSMiddleware` locked to the web origin (`http://localhost:3000` in dev) as defense-in-depth, in case any future client call bypasses the proxy. Never use `allow_origins=["*"]` with credentials.
- **Health:** FastAPI exposes `/health`; compose uses `depends_on` so the web service waits for the API. No Next.js API routes for forensics work — Python owns all of it (locked in CONTEXT.md D-02).

**Locked recommendation:** same-origin via **env-driven Next.js rewrites** (`API_URL` server-side only), CORSMiddleware locked to the web origin as backup, `/health` endpoint + compose `depends_on` — because the demo must survive venue networks where direct browser→API calls and CORS misconfigurations are the classic failure.

---

## 3. react-force-graph-2d inside Next.js App Router

**Verified:** `react-force-graph-2d@1.29.2` (latest, via npm registry today).

**The SSR problem:** the library (and its three.js/force-graph internals) touches `window`/`document` at import time. In App Router, `"use client"` alone does NOT fix this — client components are still pre-rendered on the server. An unguarded import crashes the build or the page with `ReferenceError: window is not defined`.

**Correct pattern (verified current):** isolate the graph in its own wrapper component marked `"use client"`, and load that wrapper from the page with `next/dynamic(() => import('./EvidenceGraph'), { ssr: false })` plus a loading fallback. This is the documented, still-current fix.

**Bundle note:** react-force-graph-2d pulls in three.js (large, several hundred KB). The `ssr: false` dynamic import keeps it out of the initial page bundle, so first paint stays fast and the graph chunk loads only when the investigator opens the graph view.

**Locked recommendation:** `react-force-graph-2d@1.29.2`, always behind a `"use client"` wrapper loaded via `next/dynamic` with `ssr: false` — because it is the only supported way to run this library in App Router, and the dynamic import also solves the three.js bundle-weight problem.

---

## 4. Timeline UI options for React

**Verified:** `vis-timeline@8.5.4` (standalone library, latest) and `react-vis-timeline-2@2.1.6` (TypeScript React wrapper, latest) — both checked on npm today.

| Library | Type | Scale | License | Fit for a forensics event timeline |
|---|---|---|---|---|
| **vis-timeline** (+ react-vis-timeline-2 wrapper) | Generic interactive event timeline | Few thousand items (DOM) | Apache/MIT | Exact match: chronological log/activity events, groups, selection events |
| react-calendar-timeline | Resource-row scheduler | Few thousand | MIT | Built for scheduling rows, not incident narratives — wrong category |
| TimelineJS3 | Storytelling/media timeline | ~200 items | MPL 2.0 | Editorial use; too small and wrong interaction model |
| ApexCharts timeline | Chart-style | ~2k | MIT | Chart, not an interactive investigation surface |
| D3.js DIY | Anything | Depends | ISC | Full custom build — time we don't have before 20 Nov |

**Pick: vis-timeline 8.5.4 via the react-vis-timeline-2 2.1.6 wrapper.** Rationale: it is the 2026 consensus pick for "free generic interactive timeline" (the exact category a crime timeline falls in), it handles far more items than our ~50-artifact demo case, it supports groups (one lane per evidence source) and selection events — clicking an event can open the source artifact, which is literally requirement TML-02. The wrapper avoids the old `react-vis-timeline` re-render performance bug and exposes the native DataSet API. Same `dynamic(..., { ssr: false })` treatment as the graph, plus the `vis-timeline` CSS import inside the client component.

**Locked recommendation:** `vis-timeline@8.5.4` + `react-vis-timeline-2@2.1.6`, client-only via dynamic import — because it maps 1:1 onto TML-01/TML-02, and every alternative is either the wrong timeline category or a custom build we can't afford.

---

## 5. spaCy: en_core_web_sm vs en_core_web_md

**Verified:** `spacy@3.8.16` (latest, via pip today). Model facts (stable across sources):

| Model | Download size | Word vectors | NER accuracy | Loaded RAM (approx) |
|---|---|---|---|---|
| `en_core_web_sm` | ~12 MB | No | ~85.9% | ~50–100 MB |
| `en_core_web_md` | ~40–48 MB | Yes (20k keys) | ~86.2% | ~150–250 MB |

**Analysis:** the NER accuracy gap is ~0.3 percentage points — negligible. The `md` model's real advantage is word vectors for semantic similarity, which we don't need from spaCy (sentence-transformers covers similarity). Phones, emails, IPs, and URLs — a large share of forensics entities — are handled by regex extractors, not the NER model. spaCy is only needed for PERSON/ORG-type entities. On an 8 GB laptop that also hosts MiniLM and possibly a ViT detector, the ~100–150 MB saved matters.

**Locked recommendation:** `spacy==3.8.16` + **`en_core_web_sm`** (installed in the Docker build via `python -m spacy download en_core_web_sm`) — because NER quality is effectively identical to `md` for our entity types, and it is 4x smaller on disk and ~2x lighter in RAM.

---

## 6. sentence-transformers for entity fuzzy matching

**Verified:** `sentence-transformers@6.1.0` (latest, via pip today). Model: `sentence-transformers/all-MiniLM-L6-v2`.

| Property | Value |
|---|---|
| Parameters | ~22.7M |
| Weights on disk | ~80–90 MB |
| Embedding dim | 384 (L2-normalized — cosine = dot product) |
| Max input | 256 tokens (truncate longer strings) |
| Loaded RAM (model + runtime) | ~140 MB total |
| License | Apache 2.0 |

**Analysis:** at ~140 MB RAM and <10 ms per encoding on CPU, this is comfortably inside the 8 GB budget and is the standard "tiny but good" choice. The one cost is its torch dependency (CPU-only torch wheel is ~200 MB; the full wheel is much larger — pin the CPU-only index in requirements to keep the Docker image sane). Encode each entity mention once at ingest, store the 384-dim vector, and do cosine matching at correlation time.

**Escape hatch (noted, not locked):** if Docker image size becomes a problem, `onnxruntime@1.31.0` (verified latest today) with an ONNX export of MiniLM removes torch entirely. The exact `onnx-community` model id for all-MiniLM-L6-v2 was [UNVERIFIED] — verify before committing to this path. A non-ML fallback (rapidfuzz token-sort ratios + deterministic identifier matching) exists but D-04 locks sentence-transformers, so treat this as contingency only.

**Locked recommendation:** `sentence-transformers==6.1.0` + `all-MiniLM-L6-v2` (torch CPU-only) — because it is the lightest model that is still genuinely good at semantic matching, at ~90 MB weights and ~140 MB RAM, Apache-2.0 licensed.

---

## 7. Tesseract vs EasyOCR

**Verified:** `pytesseract@0.3.13` (latest, via pip today); Tesseract engine is 5.x (system package); EasyOCR is at 1.7.2.

| | Tesseract 5.x (via pytesseract) | EasyOCR 1.7.2 |
|---|---|---|
| Install footprint | ~10 MB models + system binary | ~500 MB models + torch |
| Speed (CPU) | 0.1–1 s/page | 2.5–3 s/page (2–3x slower) |
| Clean printed text / screenshots | Excellent (best in class for clean input) | ~95% char accuracy — slightly below Tesseract on clean input |
| Rotated / noisy / distorted | Weak (needs deskewing preprocessing) | Clearly better (82% vs 52% on curved/rotated in benchmarks) |
| Handwriting | Poor | Better (62%) but still not reliable |
| GPU needed | No — CPU-only by design | Recommended, not required |

**Analysis:** forensics evidence images in our demo case are predominantly screenshots (chat apps, bank statements, documents) — clean pixel-rendered text, exactly where Tesseract wins on both accuracy and speed. EasyOCR's strengths (distorted photos, handwriting) don't match the primary evidence type, and its 500 MB models + torch dependency duplicate weight we're already spending carefully. Tesseract's weakness (rotation/noise) is mitigated with cheap preprocessing: grayscale → 2x upscale → Otsu threshold via Pillow/OpenCV before OCR.

**Locked recommendation:** **Tesseract 5.x via `pytesseract==0.3.13`** with a preprocessing step — because our evidence is screenshots/documents where it is fastest and most accurate, it is CPU-only and ~10 MB, and it keeps the backend torch-free if embeddings go the ONNX route. (EasyOCR is the documented fallback if distorted-photo evidence dominates later.)

---

## 8. SQLite + SQLAlchemy: sync vs async

**Verified:** `SQLAlchemy@2.1.5` (latest, via pip today); 2.0.x line is mature. **Pin the 2.0.x series** (e.g. `SQLAlchemy==2.0.55`) — 2.1.x is very new and buys nothing for this project.

**Recommendation: synchronous SQLAlchemy.** Reasoning:
- This is a single-investigator local tool, not a high-concurrency API. Async only pays off at hundreds of concurrent requests; here it adds `MissingGreenlet` failure modes, `aiosqlite` thread-wrapper complexity, and harder debugging for zero demo benefit.
- With FastAPI, **sync `def` endpoints run in a threadpool** — the event loop stays free. The dangerous pattern is `async def` endpoints calling sync DB code (blocks the loop); we simply won't do that.
- All ML work (spaCy, embeddings, OCR) is CPU-bound and synchronous anyway.

**Concurrency gotchas (SQLite-specific):**
- SQLite allows **one writer at a time** — concurrent uploads can raise `database is locked`. Mitigations (all cheap): enable **WAL mode** (`PRAGMA journal_mode=WAL`), set a **busy timeout** (`PRAGMA busy_timeout=5000`), and use `check_same_thread=False` with a per-request session. For a single-user demo this is fully sufficient.
- Keep transactions short; never hold a write transaction across an ML inference call.

**Locked recommendation:** **sync SQLAlchemy 2.0.x**, `def` (not `async def`) endpoints, SQLite in WAL mode with busy timeout — because it is the simplest correct architecture for a single-user demo, and async would add failure modes with no upside.

---

## 9. HuggingFace deepfake / face-manipulation detectors on CPU + 8 GB RAM

**Viability verdict: feasible with caveats.** A ViT-base classifier is ~86M params / ~330 MB weights — it fits in 8 GB RAM for CPU inference (a few seconds per image), but it needs torch + transformers in the image (~1 GB+ Docker layer) and a ~330 MB model download.

**Concrete candidates (all verified to exist on the Hub; real-world forensic accuracy is [UNVERIFIED] for every community model):**
- `dima806/deepfake_vs_real_image_detection` — ViT-based real-vs-deepfake image classifier; used in a published FastAPI + HF Transformers reference build.
- `prithivMLmods/Deep-Fake-Detector-v2-Model` — ViT-base (`google/vit-base-patch16-224`), binary Realism/Deepfake; an **ONNX export exists** (`onnx-community/Deep-Fake-Detector-v2-Model-ONNX`), which would let us run it on `onnxruntime` without torch.
- `SadraCoding/SDXL-Deepfake-Detector` — ViT, MIT license, but trained specifically on SDXL-generated images (narrower than general deepfakes).
- `king1oo1/deepfake-model` — reported ~78.5% accuracy; weaker, not recommended as primary.

**Honesty constraint (from REQUIREMENTS.md FRD-02):** these are community models with no validated accuracy on forensic data. Scores must be presented as *model signals with provenance* ("ViT classifier, 0.83 fake-probability"), never as ground truth — and the ELA + EXIF heuristic path must always be available.

**Locked recommendation:** ship **`dima806/deepfake_vs_real_image_detection`** (or the Deep-Fake-Detector-v2 ONNX variant if the torch-free path is chosen) **lazy-loaded on first use with graceful fallback to ELA + EXIF/metadata heuristics** — because a real model reference strengthens the "AI-powered" judging story, but the demo must never depend on a 330 MB download succeeding at the venue. Heuristics are the guaranteed path; the model is the deep-scan upgrade.

---

## 10. Gemini API for case summaries

**Verified (Oct 2026):** the current GA Flash-tier model is **`gemini-3.8-flash`** (GA since 2 Sept 2026; older `3.5`/`3.7` Flash IDs were deprecated 8 Oct 2026 and now auto-route to newer models). A free tier exists, which is ideal for a hackathon budget.

**Locked recommendation:** pin **`gemini-3.8-flash`** as the exact model ID (do NOT use the `gemini-flash-latest` alias — Google swaps the model behind aliases, which would make judging behavior non-reproducible). Keep the 429/503 failover pattern already proven in the ParkAgent project, and design summaries to degrade gracefully offline: findings with provenance are local and always render; the LLM summary is an enhancement layer, never a hard dependency (finale network is untrusted).

---

## 11. PITFALLS — top integration gotchas that would break the finale demo

1. **Next.js 16.4 enables Cache Components by default.** A demo app with live investigator data will serve stale/cached pages in confusing ways. Scaffold with `--no-cache-components` (or remove `cacheComponents` from `next.config.ts`). This is the #1 "mysterious behavior" trap in current Next.js.
2. **Forgetting `ssr: false` on the graph or timeline** crashes the page at build or runtime (`window is not defined`). Both libraries must live behind `"use client"` wrappers loaded with `next/dynamic(..., { ssr: false })`. Add this to the phase-3/4 plan acceptance criteria.
3. **Runtime model downloads will kill the 5-minute demo budget.** spaCy model (~12 MB), MiniLM (~90 MB), deepfake ViT (~330 MB) must be **baked into the Docker image at build time**, never downloaded on container start. Venue network is untrusted.
4. **Torch bloats the Docker image.** Use the CPU-only torch index for the API image; evaluate the `onnxruntime` path for embeddings + deepfake detector if the image gets unwieldy. Never install CUDA torch on this project.
5. **Tesseract is a system binary, not just a pip package.** `pytesseract` alone does nothing — the API Dockerfile must `apt-get install tesseract-ocr` (and `tesseract-ocr-eng` data). Missing this produces a confusing "not installed" error at demo time.
6. **SQLite `database is locked`.** One writer at a time: use WAL mode + `busy_timeout`, keep write transactions short, never hold a transaction across ML inference.
7. **Rewrite target differs between dev and compose.** Hardcoding `localhost:8000` in rewrites breaks Docker; hardcoding `http://api:8000` breaks local dev. The env-driven `API_URL` pattern (Section 2) exists specifically for this.
8. **Gemini needs network; the demo must not.** If the venue Wi-Fi dies, findings/provenance/graph/timeline (all local) must still demo fully. The AI summary shows a graceful "unavailable offline" state.
9. **spaCy model ↔ library version coupling.** `en_core_web_sm` must be the build compatible with `spacy==3.8.16` — always install it via `python -m spacy download` in the Docker build, never vendor a stale wheel.
10. **Python version pin.** Use `python:3.12-slim` for the API image. Python 3.13 exists but third-party wheel lag (spaCy, onnxruntime, torch) is a real risk; 3.12 is the safe, fully-supported pin.

---

## Locked stack summary

| Layer | Choice | Version (verified 2026-10-19) |
|---|---|---|
| Frontend | Next.js App Router + React + TypeScript | Next 16.4.x / React 19.3 / Node 22 |
| Styling | Tailwind CSS v4 (`@tailwindcss/postcss`) | 4.3.x |
| Backend | FastAPI + uvicorn | 0.148.0 / 0.54.0 |
| ORM | SQLAlchemy (sync) | 2.0.x |
| DB | SQLite (WAL mode) | stdlib sqlite3 |
| Graph engine | NetworkX | 3.7 |
| NER | spaCy `en_core_web_sm` | 3.8.16 |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` | 6.1.0 (torch CPU-only) |
| OCR | Tesseract via pytesseract (+ Pillow preprocessing) | engine 5.x / 0.3.13 / Pillow 13.0.0 |
| Metadata | Pillow EXIF (+ exifread 3.5.1 optional) | — |
| Graph UI | react-force-graph-2d (`ssr: false`) | 1.29.2 |
| Timeline UI | vis-timeline + react-vis-timeline-2 (`ssr: false`) | 8.5.4 / 2.1.6 |
| Deepfake signal | HF ViT classifier, lazy-loaded, heuristics fallback | `dima806/deepfake_vs_real_image_detection` (candidate) |
| Anomaly detection | scikit-learn IsolationForest | 1.9.1 |
| Case summaries | Gemini Flash (pinned ID, offline-degrading) | `gemini-3.8-flash` |
| Packaging | Docker Compose (`web` + `api`, one command) | python:3.12-slim / node:22-slim |

**Items marked [UNVERIFIED] in this doc:** exact latest Tailwind 4.3.x patch number; availability of an `onnx-community` ONNX id for all-MiniLM-L6-v2; real-world forensic accuracy of every community deepfake model listed.

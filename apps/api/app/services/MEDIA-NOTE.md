# MEDIA-NOTE.md — services/media.py integration guide (for the wiring phase)

Pure-Python media forensics module. No DB access, no app imports beyond
itself. FRD-01 (ELA + EXIF) and FRD-02 (deepfake score) per plan Tasks 5.4/5.5.

## Function signatures

```python
ela_score(image_path, heatmap_dir=None) -> tuple[float, str]
```
- Recompresses the image at JPEG quality 90 (Pillow), computes the
  per-pixel max-channel absolute difference vs the original.
- **Score** = 99th percentile of that difference, normalized to [0, 1].
  Higher = stronger *localized* recompression error.
- Returns `(score, heatmap_path)`; heatmap is a brightness-amplified
  difference PNG saved to `apps/api/storage/ela/<sha256-of-file>.png`
  (or `heatmap_dir/<sha256>.png` when given).
- Deterministic: same bytes → same score.

```python
exif_flags(exif: dict | None, file_mtime: float | None = None) -> list[str]
```
- `exif`: tag-name → value dict as produced by the extraction service
  (parse the artifact's `exif_json` TEXT with `json.loads` first).
- `file_mtime`: `os.path.getmtime` of the stored blob (for the mismatch check).
- Returns any of: `exif-stripped` (no EXIF at all), `datetime-mismatch`
  (`DateTimeOriginal`/`CreateDate` more than 24 h from `file_mtime`),
  `editor-software` (`Software` tag matches a known editor keyword list).

```python
deepfake_score(image_path, timeout_s=60) -> tuple[float | None, str | None]
```
- First call lazily loads `dima806/deepfake_vs_real_image_detection` via
  `transformers.pipeline("image-classification")` in a daemon worker thread;
  the 60 s timeout can never hang a request.
- Returns `(P(fake) in [0,1], "dima806/deepfake_vs_real_image_detection")`,
  or `(None, None)` on **any** failure (missing deps, download timeout,
  inference error, uninterpretable labels). Never raises, never fabricates.
- A failed load is sticky for the process lifetime (no retry storms).

## `media_signals` columns to create (per 05-CONTEXT.md + FRD-03)

```sql
media_signals(
  id INTEGER PRIMARY KEY,
  artifact_id INTEGER UNIQUE REFERENCES artifacts(id),
  ela_score REAL NULL,
  ela_heatmap_path TEXT NULL,
  exif_flags_json TEXT,            -- JSON list, e.g. '["exif-stripped"]'
  deepfake_score REAL NULL,
  deepfake_model TEXT NULL,
  pulse_bpm REAL NULL,             -- FRD-03 (pulse.py, separate module)
  pulse_snr REAL NULL,             -- FRD-03
  pulse_verdict TEXT NULL,         -- FRD-03
  created_ts TEXT                   -- UTC ISO
)
```

## New pip dependencies

- **Pillow==13.0.0** — already in `requirements.txt` (Phase 2). No change.
- **transformers + torch (CPU)** — OPTIONAL, only for the deepfake model.
  `pip install transformers torch --index-url https://download.pytorch.org/whl/cpu`.
  If absent, `deepfake_score` returns `(None, None)` and the pipeline runs
  ELA + EXIF heuristics only. Docker note: torch adds significant image
  weight; Phase 6 decides whether to bake it or ship heuristics-only.
- The module itself needs nothing else (test uses numpy for fixtures only).

## Integration: `POST /api/media/{id}/analyze`

Suggested flow (images only; 422 for non-image artifacts):
1. Load the artifact (404 if missing); resolve the blob via
   `metadata_json.stored_path` under the storage dir.
2. `score, heatmap = ela_score(blob_path)` — heatmap lands in
   `apps/api/storage/ela/` automatically.
3. `flags = exif_flags(json.loads(artifact.exif_json or "{}"), os.path.getmtime(blob_path))`.
4. `df_score, df_model = deepfake_score(blob_path)` → `(None, None)` offline.
5. Upsert the `media_signals` row (`artifact_id` UNIQUE); write a custody-log
   entry with `action="analyze"`.
6. Findings rule `tampered-media` (in `findings.py`): fires when
   `ela_score >= PROPOSED_ELA_THRESHOLD` (import from `services.media`) or
   `exif_flags` non-empty. Snippet must include the heatmap path and flags;
   confidence mapping is the wiring phase's call — suggestion: 0.75 when only
   flags fire, scaling with the ELA score otherwise.
7. Serve heatmaps to the UI (static mount or dedicated endpoint) so the
   investigator can see the amplified regions.

## Calibration data (measured 2026-10-19, synthetic fixtures)

| Fixture | ELA score (p99) |
|---|---|
| clean bank-statement image (JPEG q95) | 0.00392 |
| realistic splice: q70-history textured patch pasted, composite q95 | 0.01176 |
| second splice variant (q65 history, other location) | 0.01569 |

- `PROPOSED_ELA_THRESHOLD = 0.007` separates these fixtures. **Recalibrate
  on real evidence before the finale** — synthetic fixtures understate
  real-world variance.
- **Deliberate deviation:** the plan suggested the *global mean* absolute
  difference, but fixtures proved the mean cannot robustly order
  edited > clean for localized edits (it inverted to 0.9x on a flat paste,
  because the paste removed edge texture the mean was measuring). The p99
  statistic separates realistic splices 3–4x and never inverted. The plan's
  binding acceptance criterion is the ordering; the 0.35 threshold was
  [PROPOSED] and is superseded by the measurement above.

## Open verification items for the wiring phase

- **[UNVERIFIED]** The deepfake label→P(fake) mapping
  (`_fake_probability` in `media.py`) is a best-effort heuristic:
  transformers/torch are not installed in this environment. Once the model
  is available, run one known-real and one known-fake image through
  `deepfake_score` and confirm the label vocabulary; adjust the mapping if
  the labels differ (e.g. `LABEL_0`/`LABEL_1`).
- The 60 s load timeout was verified by code path (fast-fail on missing
  transformers), not against a real stalled download.

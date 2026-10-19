# PULSE-NOTE.md — FRD-03 pulse-liveness integration guide

Module: `apps/api/app/services/pulse.py` (built & verified 2026-10-19; no wiring done)

## Exact public signatures

```python
analyze_video(path, face_detector=None, frame_stride=3) -> dict
# {bpm: float|None, snr: float, verdict: str, confidence: float,
#  face_seconds: float, frames_used: int, frames_with_face: int, path: str}
# Raises ValueError if the video cannot be opened.

analyze_series(times, greens, frames_with_face=0) -> dict
# Pure DSP + verdict on an already-extracted series (test seam / reuse).

extract_green_series(path, face_detector=None, frame_stride=3)
# -> (times, greens, stats); stats = {frames_processed, frames_with_face, fps_video}

verdict_for_snr(snr) -> "real-face-supported" | "inconclusive" | "possibly-synthetic"
confidence_for(snr, verdict) -> float   # clip(snr/20, .05, .95); 0.5 if inconclusive
```

`face_detector` seam: callable taking an RGB frame, returning a
`(x0, y0, x1, y1)` box or None. Default = mediapipe FaceMesh detector
(prototype-identical). Inject a fake in tests.

## Verdict vocabulary (calibrated)

| SNR | verdict | confidence |
|---|---|---|
| ≥ 12 | `real-face-supported` | clip(snr/20, .05, .95) |
| 6–12 | `inconclusive` | 0.5 |
| < 6 | `possibly-synthetic` | clip(snr/20, .05, .95) |
| no face in any frame | `no-face` | 0.05 |
| < 5 s face-tracked | `insufficient-signal` | 0.05 |

## DB columns the wiring phase must create

On `media_signals` (new table per 05-CONTEXT.md, else ALTER TABLE):
`pulse_bpm REAL NULL, pulse_snr REAL NULL, pulse_verdict TEXT NULL`

## Wiring checklist

1. `POST /api/media/{id}/pulse`: load artifact; **422 if not a video**
   (`source_type != "video"`). Call `analyze_video(artifact_abs_path)`;
   map `ValueError` (unopenable) → 422.
2. Upsert the `media_signals` row for the artifact with the three pulse
   columns; add a custody-log `analyze` entry (vocabulary per 02-CONTEXT.md).
3. Findings rule `pulse-liveness`: emit a finding **only** for directional
   verdicts (`real-face-supported`, `possibly-synthetic`) with
   `rule_or_model="rPPG remote photoplethysmography"`,
   `confidence` from the module, `artifact_ids_json=[id]`, and a snippet
   containing the SNR — plus the literal caveat
   "supporting signal, not proof" in the description (NFR-02: all four
   provenance fields required or the API must 422).
   `inconclusive` / `no-face` / `insufficient-signal` → stored, **no finding**.
4. New pip deps (CPU-only): `opencv-python`, `mediapipe==0.10.14`
   (the `solutions` API the prototype uses; mediapipe 1.x removed it —
   do NOT install 1.x), `numpy`, `scipy`.

## Measured verification numbers (2026-10-19)

- DSP self-test: 60/72/90/120 BPM recovered ±0.4, SNR 39–43; flat noise SNR 8.0
  (never misread as real) — matches the prototype's calibration.
- Synthetic 72 BPM video through mp4v: **71.5 BPM, SNR 31.0** →
  `real-face-supported`, conf 0.95.
- Synthetic flat video: SNR **11.2** → `inconclusive` (compression artifacts
  add weak periodic noise — this is exactly why the ≥12 bar exists; the
  module stayed honest instead of crying "real").
- 2 s clip → `insufficient-signal`; synthetic video through the REAL
  mediapipe detector → `no-face` (no detectable face, as expected).

## Known limits (do not over-claim)

- Heavy compression, bad light, or motion can push a real face into
  `inconclusive` — the verdict is a supporting signal, never proof.
- The video-path test used an injected box detector; only the no-face path
  was exercised against real mediapipe (correctly returned `no-face`).
- `estimate_bpm` needs ≥ 5 s of samples internally too; the module gates on
  face_seconds ≥ 5 s first, so the two requirements coincide.

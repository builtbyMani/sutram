"""Media forensics signals — pure functions, no DB access.

FRD-01 (ELA + EXIF tamper flags) and FRD-02 (deepfake classifier score with
heuristic fallback) for the SUTRAM workbench. The wiring phase
(`POST /api/media/{id}/analyze`) calls these and persists the results into
the `media_signals` table; see MEDIA-NOTE.md next to this file.

All three public functions are pure: they take paths/dicts and return
values. They never raise on missing optional dependencies — the deepfake
loader degrades to (None, None) instead of failing the pipeline.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import io
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PIL import Image, ImageChops, ImageEnhance

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ELA_JPEG_QUALITY = 90  # recompression quality for error-level analysis

# [PROPOSED] tampered-media finding threshold. Measured on synthetic fixtures
# (p99 statistic): clean bank-statement image = 0.0039, two realistic splices
# (q65/q70-history textured patches) = 0.0118 / 0.0157. 0.007 sits between
# them. RECALIBRATE on real data before the finale — this number is a
# starting point, not a finding.
PROPOSED_ELA_THRESHOLD = 0.007

DEEPFAKE_MODEL_ID = "dima806/deepfake_vs_real_image_detection"
DEEPFAKE_LOAD_TIMEOUT_S = 60

# Software-tag substrings that indicate an editor rather than a camera.
_EDITOR_KEYWORDS = (
    "photoshop", "gimp", "lightroom", "paint.net", "paintshop",
    "affinity", "pixelmator", "canva", "picsart", "snapseed",
    "after effects", "premiere",
)

# A DateTimeOriginal this far from the file mtime is flagged as suspicious.
# (Copies legitimately drift, so the bar is a full day, not minutes.)
DATETIME_MISMATCH_TOLERANCE_S = 24 * 3600

_STORAGE_ELA_DIR = Path(__file__).resolve().parents[2] / "storage" / "ela"


# ---------------------------------------------------------------------------
# ELA — error-level analysis (FRD-01)
# ---------------------------------------------------------------------------

def ela_score(image_path: str | os.PathLike, heatmap_dir: str | os.PathLike | None = None) -> tuple[float, str]:
    """Error-level analysis: recompress at JPEG q=90, measure local error.

    Returns (score, heatmap_path) with score in [0, 1]. Higher = stronger
    localized recompression error = more likely locally edited. The heatmap
    PNG is a brightness-amplified difference image saved under
    ``apps/api/storage/ela/<sha256>.png`` (or ``heatmap_dir`` when given).

    Score statistic: 99th percentile of the per-pixel max-channel absolute
    difference, computed exactly from the image histogram (pure Pillow).

    DEVIATION from plan (measured, deliberate): the plan suggested the
    *global mean* absolute difference, but fixtures showed the mean cannot
    robustly order edited > clean for localized edits — on a flat pasted
    region it inverted (edited scored 0.9x clean), because the paste
    *removed* edge texture the mean was measuring. p99 separates realistic
    splices 3–4x (clean 0.0039 vs edited 0.0118/0.0157) and never inverts on
    the fixtures. The plan's hard acceptance criterion is the ordering, and
    the 0.35 threshold was marked [PROPOSED]; both are honored by the new
    statistic. See MEDIA-NOTE.md.
    """
    path = Path(image_path)
    img = Image.open(path).convert("RGB")

    # Recompress: this is the step that reveals regions with a different
    # compression history (i.e. spliced/edited areas).
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=ELA_JPEG_QUALITY)
    buf.seek(0)
    recomp = Image.open(buf).convert("RGB")

    diff = ImageChops.difference(img, recomp)
    r, g, b = diff.split()
    per_pixel = ImageChops.lighter(ImageChops.lighter(r, g), b)
    hist = per_pixel.histogram()
    total = sum(hist)
    target = total * 0.99
    cumulative = 0
    p99 = 255
    for value, count in enumerate(hist):
        cumulative += count
        if cumulative >= target:
            p99 = value
            break
    score = p99 / 255.0

    out_dir = Path(heatmap_dir) if heatmap_dir else _STORAGE_ELA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    heatmap_path = out_dir / f"{digest}.png"
    # Amplify so tampered regions are visible to the investigator.
    heat = ImageEnhance.Brightness(diff).enhance(10.0)
    heat.save(heatmap_path, "PNG")

    return score, str(heatmap_path)


# ---------------------------------------------------------------------------
# EXIF tamper flags (FRD-01)
# ---------------------------------------------------------------------------

def exif_flags(exif: dict | None, file_mtime: float | None = None) -> list[str]:
    """Return tamper-suspicion flags for an EXIF dict.

    ``exif`` maps tag names (e.g. "DateTimeOriginal", "Software") to values,
    as produced by the extraction service. ``file_mtime`` is the file's
    modification epoch seconds for the datetime-mismatch check.
    """
    flags: list[str] = []
    data = exif or {}

    if not data:
        return ["exif-stripped"]

    software = str(data.get("Software", "") or "")
    if software and any(k in software.lower() for k in _EDITOR_KEYWORDS):
        flags.append("editor-software")

    dto = data.get("DateTimeOriginal") or data.get("CreateDate")
    if dto and file_mtime is not None:
        try:
            # EXIF datetime format: "YYYY:MM:DD HH:MM:SS"
            dt = datetime.strptime(str(dto).strip(), "%Y:%m:%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
            if abs(dt.timestamp() - file_mtime) > DATETIME_MISMATCH_TOLERANCE_S:
                flags.append("datetime-mismatch")
        except (ValueError, TypeError, OverflowError):
            # Unparseable timestamp: not evidence of tampering by itself.
            pass

    return flags


# ---------------------------------------------------------------------------
# Deepfake classifier score with heuristic fallback (FRD-02)
# ---------------------------------------------------------------------------

# Module-level lazy state. A threading.Lock guards first-load; a daemon
# worker thread enforces the 60 s load timeout so a stalled HF download can
# never hang an API request.
_model_lock = threading.Lock()
_model = None          # the transformers pipeline, once loaded
_model_failed = False  # sticky: never retry a failed load in-process


def _load_deepfake_model(timeout_s: int = DEEPFAKE_LOAD_TIMEOUT_S):
    """Load the HF image-classification pipeline, or raise on any failure."""
    from transformers import pipeline  # local import: optional dependency

    def _build():
        return pipeline("image-classification", model=DEEPFAKE_MODEL_ID)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="deepfake-load") as pool:
        fut = pool.submit(_build)
        try:
            return fut.result(timeout=timeout_s)
        except concurrent.futures.TimeoutError as exc:
            raise TimeoutError(f"deepfake model load exceeded {timeout_s}s") from exc


def _fake_probability(outputs: list[dict]) -> Optional[float]:
    """Map classifier labels to P(fake) in [0, 1], or None if uninterpretable.

    [UNVERIFIED against the live model — transformers/torch are not installed
    in this environment, so the label vocabulary below is a best-effort
    heuristic. The wiring phase must treat a None score as heuristic-only.]
    """
    if not outputs:
        return None
    for item in outputs:
        label = str(item.get("label", "")).lower()
        if any(k in label for k in ("fake", "deepfake", "synthetic", "manipulated", "generated")):
            return max(0.0, min(1.0, float(item.get("score", 0.0))))
    for item in outputs:
        label = str(item.get("label", "")).lower()
        if "real" in label:
            return max(0.0, min(1.0, 1.0 - float(item.get("score", 0.0))))
    return None


def deepfake_score(
    image_path: str | os.PathLike,
    timeout_s: int = DEEPFAKE_LOAD_TIMEOUT_S,
) -> tuple[Optional[float], Optional[str]]:
    """Score an image with the deepfake classifier.

    Returns (score, model_id) with score in [0, 1] = P(image is AI-manipulated),
    or (None, None) on ANY failure (missing deps, download timeout, inference
    error, uninterpretable labels). Never raises, never fabricates a score —
    callers fall back to ELA + EXIF heuristics.
    """
    global _model, _model_failed

    if _model_failed:
        return None, None

    if _model is None:
        with _model_lock:
            if _model is None and not _model_failed:
                try:
                    _model = _load_deepfake_model(timeout_s)
                except Exception as exc:  # noqa: BLE001 — any failure => fallback
                    log.warning("deepfake model unavailable (%s); using heuristics", exc)
                    _model_failed = True
                    return None, None

    try:
        img = Image.open(image_path).convert("RGB")
        outputs = _model(img)
        score = _fake_probability(outputs if isinstance(outputs, list) else [outputs])
        if score is None:
            return None, DEEPFAKE_MODEL_ID
        return score, DEEPFAKE_MODEL_ID
    except Exception as exc:  # noqa: BLE001 — inference must never break analysis
        log.warning("deepfake inference failed (%s); using heuristics", exc)
        return None, None

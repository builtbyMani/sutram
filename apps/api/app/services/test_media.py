"""Self-test for services/media.py — no app DB, no network, no torch needed.

Generates fixtures with Pillow in a temp dir:
  clean.jpg    bank-statement-style image, saved JPEG q=95, unedited
  edited.jpg   same base, but the amount region is replaced by a patch with
               JPEG q=70 compression history + different content (the classic
               ELA scenario: spliced content recompresses differently)
Asserts (per plan 5.4/5.5 acceptance):
  - edited ela_score > clean ela_score   (ordering, not absolute values)
  - exif_flags({}) -> ['exif-stripped']
  - EXIF dict with old DateTimeOriginal + Photoshop Software ->
      ['datetime-mismatch', 'editor-software'] (order-insensitive)
  - matching DateTimeOriginal -> no flags
  - deepfake_score(...) -> (None, None) quickly here (no transformers/torch
    installed) and never raises.

Also prints where the measured scores fall against PROPOSED_ELA_THRESHOLD
(calibration info only — the threshold is tunable, not a pass/fail gate).

Run:  python3 apps/api/app/services/test_media.py
Exit 0 = all green.
"""

import io
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # apps/api

from PIL import Image, ImageDraw  # noqa: E402

from app.services.media import PROPOSED_ELA_THRESHOLD, deepfake_score, ela_score, exif_flags  # noqa: E402


def _statement_base() -> Image.Image:
    """White bank-statement-style page with dark text-like lines."""
    img = Image.new("RGB", (800, 600), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([40, 30, 760, 90], fill=(235, 235, 235))          # header band
    y = 130
    for _ in range(8):                                            # text lines
        d.rectangle([60, y, 620, y + 14], fill=(60, 60, 60))
        y += 42
    d.rectangle([60, 500, 300, 540], fill=(240, 240, 240))        # amount box
    d.rectangle([70, 508, 200, 532], fill=(30, 30, 30))           # amount text
    return img


def _spliced_amount_patch() -> Image.Image:
    """Amount-region patch with its own (q=70) compression history."""
    patch = Image.new("RGB", (240, 40), (240, 240, 240))
    ImageDraw.Draw(patch).rectangle([10, 8, 140, 32], fill=(30, 30, 30))
    rng = np.random.default_rng(7)
    noisy = np.asarray(patch).astype(int) + rng.integers(-25, 26, (40, 240, 1))
    patch = Image.fromarray(np.clip(noisy, 0, 255).astype("uint8"))
    buf = io.BytesIO()
    patch.save(buf, "JPEG", quality=70)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        if not cond:
            failures.append(name)

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        heatdir = tmpdir / "heat"

        clean_p = tmpdir / "clean.jpg"
        edited_p = tmpdir / "edited.jpg"
        _statement_base().save(clean_p, "JPEG", quality=95)

        edited = _statement_base()
        edited.paste(_spliced_amount_patch(), (60, 500))  # q70-history splice
        edited.save(edited_p, "JPEG", quality=95)

        # --- ELA ---
        clean_score, clean_hm = ela_score(clean_p, heatmap_dir=heatdir)
        edited_score, edited_hm = ela_score(edited_p, heatmap_dir=heatdir)
        print(f"measured ELA: clean={clean_score:.5f} edited={edited_score:.5f} "
              f"(proposed threshold {PROPOSED_ELA_THRESHOLD})")
        check("ela scores in [0,1]", 0.0 <= clean_score <= 1.0 and 0.0 <= edited_score <= 1.0)
        check("edited ela > clean ela", edited_score > clean_score,
              f"{edited_score:.5f} > {clean_score:.5f} ({edited_score / max(clean_score, 1e-9):.1f}x)")
        check("heatmaps written", Path(clean_hm).exists() and Path(edited_hm).exists())
        check("ela deterministic", ela_score(clean_p, heatmap_dir=heatdir)[0] == clean_score)
        separates = clean_score < PROPOSED_ELA_THRESHOLD <= edited_score
        print(f"  [INFO] proposed threshold separates fixtures: {separates} "
              f"(tune on real data before the finale)")

        # --- EXIF flags ---
        check("stripped exif flagged", exif_flags({}) == ["exif-stripped"])
        check("none exif flagged", exif_flags(None) == ["exif-stripped"])
        now = datetime.now(timezone.utc).timestamp()
        tampered = exif_flags(
            {"DateTimeOriginal": "2020:01:01 12:00:00", "Software": "Adobe Photoshop 25.0"},
            file_mtime=now,
        )
        check("datetime-mismatch flagged", "datetime-mismatch" in tampered, str(tampered))
        check("editor-software flagged", "editor-software" in tampered, str(tampered))
        fresh_dto = datetime.fromtimestamp(now, timezone.utc).strftime("%Y:%m:%d %H:%M:%S")
        check("matching datetime clean", exif_flags({"DateTimeOriginal": fresh_dto}, file_mtime=now) == [])
        check("plain camera exif clean",
              exif_flags({"DateTimeOriginal": fresh_dto, "Make": "TestCam"}, file_mtime=now) == [])

        # --- deepfake fallback (no transformers/torch here) ---
        t0 = time.time()
        try:
            result = deepfake_score(clean_p)
            elapsed = time.time() - t0
            check("deepfake fallback (None, None)", result == (None, None), str(result))
            check("deepfake fallback fast (<30s, no 60s hang)", elapsed < 30, f"{elapsed:.1f}s")
        except Exception as exc:  # noqa: BLE001
            check("deepfake never raises", False, repr(exc))

    print(f"\n{len(failures)} failure(s)" if failures else "\nALL GREEN")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

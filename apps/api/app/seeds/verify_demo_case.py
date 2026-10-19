#!/usr/bin/env python3
"""Verify the Operation Ledger demo-case generator.

Checks:
  1. Determinism: two runs with the same seed -> byte-identical trees
  2. Artifact count: 49 expected (48-52 accepted)
  3. The 5 source-type group dirs exist and are non-empty
  4. Planted evidence:
     - shared coordinator phone in >=3 chat files
     - edited bank statement differs from its clean twin
     - brute-force bursts (>=40 failed logins) in >=3 auth logs
     - pulse video frames modulate at ~72 BPM in the face region
     - EXIF present on a statement scan, absent on the stripped photo
Usage: python3 verify_demo_case.py
Exit code 0 = all checks pass.
"""

from __future__ import annotations

import filecmp
import re
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_demo_case import build, SEED, SHARED_PHONE  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((PASS if ok else FAIL, name, detail))
    print(f"[{'OK' if ok else 'XX'}] {name}" + (f" — {detail}" if detail else ""))


def tree_files(d: Path) -> list[Path]:
    return sorted(p.relative_to(d) for p in d.rglob("*") if p.is_file())


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ledger_verify_"))
    try:
        out1, out2 = tmp / "run1", tmp / "run2"
        build(out1, SEED)
        build(out2, SEED)

        # 1. determinism
        f1, f2 = tree_files(out1), tree_files(out2)
        same_names = f1 == f2
        same_bytes = all(
            filecmp.cmp(out1 / f, out2 / f, shallow=False) for f in f1
        ) if same_names else False
        check("determinism (two runs byte-identical)", same_names and same_bytes,
              f"{len(f1)} files")

        arts = [f for f in f1 if f.name != "manifest.json"]
        # 2. count: 49 artifacts expected
        check("artifact count 48-52", 48 <= len(arts) <= 52, f"{len(arts)} artifacts")

        # 3. group dirs
        groups = ["chats", "images", "logs", "pcaps", "video"]
        for g in groups:
            files = [f for f in arts if str(f).startswith(g + "/")]
            check(f"group '{g}' non-empty", len(files) > 0, f"{len(files)} files")

        # 4a. shared phone in >=3 chats
        hits = [f for f in arts if str(f).startswith("chats/")
                and SHARED_PHONE in (out1 / f).read_text(encoding="utf-8")]
        check("shared phone in >=3 chats", len(hits) >= 3,
              f"{len(hits)} files: {', '.join(h.name for h in hits)}")

        # 4b. edited twin differs from clean twin
        clean = out1 / "images/statements/statement_07.jpg"
        edited = out1 / "images/statements/statement_08_edited.jpg"
        check("edited statement differs from clean twin",
              clean.exists() and edited.exists()
              and clean.read_bytes() != edited.read_bytes())

        # 4c. brute-force bursts
        bursty = [f for f in arts if str(f).startswith("logs/")
                  and (out1 / f).read_text(encoding="utf-8").count("Failed password") >= 40]
        check("brute-force bursts in >=3 auth logs", len(bursty) >= 3,
              f"{len(bursty)} files")

        # 4d. pulse video: face-region green channel modulates at ~72 BPM
        import cv2
        cap = cv2.VideoCapture(str(out1 / "video/pulse_face_72bpm.mp4"))
        fps = cap.get(cv2.CAP_PROP_FPS)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        yy, xx = np.mgrid[0:h, 0:w]
        face = ((xx - w / 2) / 70) ** 2 + ((yy - h / 2) / 90) ** 2 <= 0.64
        series = []
        while True:
            ok, fr = cap.read()
            if not ok:
                break
            series.append(float(fr[:, :, 1][face].mean()))
        cap.release()
        s = np.asarray(series)
        s = s - s.mean()
        spec = np.abs(np.fft.rfft(s))
        freqs = np.fft.rfftfreq(len(s), 1.0 / fps)
        band = (freqs >= 0.7) & (freqs <= 4.0)
        peak = freqs[band][int(np.argmax(spec[band]))]
        bpm = peak * 60.0
        check("pulse video modulates at 72 BPM (±3)", 69.0 <= bpm <= 75.0,
              f"measured {bpm:.1f} BPM over {len(series)} frames @ {fps:.0f}fps")

        # 4e. EXIF present on statement, absent on stripped photo
        from PIL import Image
        st = Image.open(out1 / "images/statements/statement_01.jpg")
        ph = Image.open(out1 / "images/stripped/photo_id_stripped.jpg")
        has_exif = bool(st.getexif())
        no_exif = not bool(ph.getexif())
        check("EXIF present on statement scan", has_exif)
        check("EXIF stripped on photo", no_exif)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [r for r in results if r[0] == FAIL]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Pulse-liveness (rPPG) for video faces — FRD-03.

A real face shows a periodic blood-volume pulse in the skin's green channel;
a synthetic face (or a still image passed off as video) does not. This module
scores that signal and maps it to a calibrated verdict.

The DSP core (detrend / bandpass / estimate_bpm) and the ROI approach are
ported VERBATIM from ~/workspace/pulse-detector/pulse_detector.py — a working,
self-tested prototype. Do not "improve" them here; they are calibrated.

Public API for the wiring phase:
    analyze_video(path, face_detector=None, frame_stride=3) -> dict
        {bpm, snr, verdict, confidence, face_seconds, frames_used,
         frames_with_face, path}

Verdicts (calibrated on the prototype's self-test):
    snr >= 12  -> "real-face-supported"
    6 <= snr < 12 -> "inconclusive"
    snr < 6    -> "possibly-synthetic"
    no face found in any frame -> "no-face"
    < 5 s of face-tracked signal -> "insufficient-signal" (no finding)

Confidence: clip(snr/20, 0.05, 0.95) for directional verdicts,
0.5 for "inconclusive", 0.05 for "no-face"/"insufficient-signal"
(there is no directional claim to be confident about).

Findings guidance: emit a `pulse-liveness` finding ONLY for the directional
verdicts ("real-face-supported", "possibly-synthetic"), always carrying the
"supporting signal, not proof" caveat. Everything else is stored on the
media_signals row but must not produce a finding.
"""

import numpy as np

__all__ = [
    "detrend",
    "bandpass",
    "estimate_bpm",
    "ROIS",
    "face_box",
    "roi_mean_green",
    "analyze_video",
    "analyze_series",
    "extract_green_series",
    "verdict_for_snr",
    "confidence_for",
    "MIN_FACE_SECONDS",
]

MIN_FACE_SECONDS = 5.0

# ----------------------------------------------------------------------------
# DSP core — VERBATIM port from ~/workspace/pulse-detector/pulse_detector.py.
# Do not modify: these functions are calibrated and self-tested.
# ----------------------------------------------------------------------------

def detrend(sig):
    """Remove slow drift (lighting changes, head motion) with a moving average."""
    sig = np.asarray(sig, dtype=float)
    w = max(1, len(sig) // 10)
    trend = np.convolve(sig, np.ones(w) / w, mode="same")
    return sig - trend


def bandpass(sig, fps, lo=0.7, hi=4.0, order=4):
    """Keep only plausible heart-rate frequencies: 0.7-4 Hz = 42-240 BPM."""
    from scipy.signal import butter, filtfilt
    nyq = fps / 2.0
    b, a = butter(order, [lo / nyq, hi / nyq], btype="band")
    return filtfilt(b, a, sig)


def estimate_bpm(green_sig, fps, pad_factor=4):
    """
    Return (bpm, snr). bpm is None when no usable peak exists.
    snr = peak power / median in-band power -- high means a clean pulse.
    Zero-padding sharpens the peak without needing a longer recording.
    """
    sig = bandpass(detrend(green_sig), fps)
    n = len(sig)
    if n < int(fps * 5):
        return None, 0.0
    m = 1
    while m < n * pad_factor:
        m *= 2
    power = np.abs(np.fft.rfft(sig, n=m)) ** 2
    freqs = np.fft.rfftfreq(m, 1.0 / fps)
    band = (freqs >= 0.7) & (freqs <= 4.0)
    if not np.any(band):
        return None, 0.0
    pb = power.copy()
    pb[~band] = 0.0
    i = int(np.argmax(pb))
    peak = pb[i]
    if peak <= 0:
        return None, 0.0
    snr = float(peak / (np.mean(pb[band]) + 1e-12))
    return float(freqs[i] * 60.0), snr


# ----------------------------------------------------------------------------
# Face tracking -> green-channel signal — ROI approach ported from the
# prototype (same fractional boxes, same green-mean math).
# ----------------------------------------------------------------------------

# ROIs as fractions of the face bounding box: (x0, y0, x1, y1)
ROIS = {
    "forehead":   (0.35, 0.05, 0.65, 0.22),
    "cheek_l":    (0.08, 0.45, 0.30, 0.62),
    "cheek_r":    (0.70, 0.45, 0.92, 0.62),
}


def face_box(landmarks, w, h):
    """Bounding box (x0, y0, x1, y1) from mediapipe normalized landmarks."""
    xs = [lm.x * w for lm in landmarks]
    ys = [lm.y * h for lm in landmarks]
    return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))


def roi_mean_green(frame, box, rel):
    """Mean green-channel value inside a relative ROI. frame is BGR."""
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    rx0 = max(0, x0 + int(rel[0] * bw))
    ry0 = max(0, y0 + int(rel[1] * bh))
    rx1 = min(frame.shape[1], x0 + int(rel[2] * bw))
    ry1 = min(frame.shape[0], y0 + int(rel[3] * bh))
    if rx1 <= rx0 or ry1 <= ry0:
        return None
    patch = frame[ry0:ry1, rx0:rx1]
    return float(np.mean(patch[:, :, 1]))  # channel 1 = green in BGR


def _default_face_detector():
    """mediapipe FaceMesh -> face box, prototype-identical settings.

    Requires mediapipe==0.10.x (the `solutions` API). The returned callable
    takes an RGB frame and returns a (x0, y0, x1, y1) box or None; it also
    carries a .close() method to release the model.
    """
    try:
        import mediapipe as mp
        face_mesh = mp.solutions.face_mesh
    except (ImportError, AttributeError) as e:
        raise RuntimeError(
            "pulse.py needs mediapipe==0.10.x for the solutions API "
            f"(installed mediapipe has no mp.solutions.face_mesh): {e}"
        )
    mesh = face_mesh.FaceMesh(
        static_image_mode=False, max_num_faces=1,
        refine_landmarks=False, min_detection_confidence=0.5,
    )

    def detect(rgb_frame):
        res = mesh.process(rgb_frame)
        if not res.multi_face_landmarks:
            return None
        lm = res.multi_face_landmarks[0].landmark
        h, w = rgb_frame.shape[:2]
        return face_box(lm, w, h)

    detect.close = mesh.close
    return detect


def extract_green_series(path, face_detector=None, frame_stride=3):
    """Video -> (times, greens, stats) via face ROIs.

    Reads every `frame_stride`-th frame, runs the face detector, and records
    the mean green-channel value over the forehead/cheek ROIs for frames
    where a face is found. `face_detector` is an injectable seam
    (callable: RGB frame -> box or None); the default is the mediapipe
    FaceMesh detector above. Returns (times, greens, stats) with
    stats = {"frames_processed", "frames_with_face", "fps_video"}.
    """
    import cv2

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"could not open video: {path}")
    fps_video = cap.get(cv2.CAP_PROP_FPS)
    if not fps_video or fps_video <= 0:
        fps_video = 30.0

    own_detector = face_detector is None
    if own_detector:
        face_detector = _default_face_detector()

    times, greens = [], []
    n_processed, n_face = 0, 0
    idx = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % frame_stride == 0:
                n_processed += 1
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                box = face_detector(rgb)
                if box is not None:
                    vals = [
                        v for v in
                        (roi_mean_green(frame, box, rel)
                         for rel in ROIS.values())
                        if v is not None
                    ]
                    if vals:
                        n_face += 1
                        times.append(idx / fps_video)
                        greens.append(float(sum(vals) / len(vals)))
            idx += 1
    finally:
        cap.release()
        if own_detector and hasattr(face_detector, "close"):
            face_detector.close()

    stats = {
        "frames_processed": n_processed,
        "frames_with_face": n_face,
        "fps_video": float(fps_video),
    }
    return times, greens, stats


def verdict_for_snr(snr):
    """Calibrated verdict vocabulary from a pulse SNR."""
    if snr >= 12:
        return "real-face-supported"
    if snr >= 6:
        return "inconclusive"
    return "possibly-synthetic"


def confidence_for(snr, verdict):
    """Confidence for a verdict: clip(snr/20, 0.05, 0.95), 0.5 if inconclusive."""
    if verdict == "inconclusive":
        return 0.5
    return float(min(0.95, max(0.05, snr / 20.0)))


def analyze_series(times, greens, frames_with_face=0):
    """Pure DSP + verdict mapping on an extracted green-channel series.

    `times`/`greens`: parallel lists from extract_green_series.
    `frames_with_face`: how many frames actually contained a face (0 and an
    empty series -> "no-face"; a non-empty but < 5 s series ->
    "insufficient-signal").
    """
    times = list(times)
    greens = list(greens)
    n = len(greens)
    face_seconds = (times[-1] - times[0]) if n > 1 else 0.0

    base = {
        "bpm": None,
        "snr": 0.0,
        "face_seconds": float(face_seconds),
        "frames_used": n,
        "frames_with_face": int(frames_with_face),
    }

    if n == 0:
        verdict = "no-face" if frames_with_face == 0 else "insufficient-signal"
        return {**base, "verdict": verdict, "confidence": 0.05}

    if face_seconds < MIN_FACE_SECONDS:
        return {**base, "verdict": "insufficient-signal", "confidence": 0.05}

    dt = float(np.median(np.diff(times))) if n > 1 else 0.1
    fps = 1.0 / dt if dt > 0 else 10.0
    bpm, snr = estimate_bpm(greens, fps)
    verdict = verdict_for_snr(snr)
    return {
        **base,
        "bpm": bpm,
        "snr": float(snr),
        "verdict": verdict,
        "confidence": confidence_for(snr, verdict),
        "fps_effective": float(fps),
    }


def analyze_video(path, face_detector=None, frame_stride=3):
    """Full pipeline: video file -> pulse verdict dict.

    Returns {bpm, snr, verdict, confidence, face_seconds, frames_used,
    frames_with_face, path}. Raises ValueError if the video cannot be opened.
    """
    times, greens, stats = extract_green_series(
        path, face_detector=face_detector, frame_stride=frame_stride)
    result = analyze_series(times, greens,
                            frames_with_face=stats["frames_with_face"])
    result["path"] = str(path)
    return result


# ----------------------------------------------------------------------------
# Self-test (no camera, no network)
# ----------------------------------------------------------------------------

def _synth_pulse_series(bpm=72, seconds=15, fps=10.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * fps)) / fps
    sig = (0.6 * np.sin(2 * np.pi * bpm / 60 * t)
           + 0.3 * np.sin(2 * np.pi * 0.15 * t)
           + 0.25 * rng.standard_normal(len(t)))
    return (t.tolist(), sig.tolist())


def self_test():
    """Replicates the prototype's self-test plus verdict-mapping checks."""
    ok = True

    # (a) DSP core: known BPMs recovered, flat never reads as real.
    for true_bpm in (60, 72, 90, 120):
        t, sig = _synth_pulse_series(true_bpm)
        bpm, snr = estimate_bpm(sig, 10.0)
        good = bpm is not None and abs(bpm - true_bpm) < 2.0
        ok &= good
        print(f"  DSP true {true_bpm:3d} BPM -> {bpm:6.1f} BPM, "
              f"SNR {snr:6.1f}  {'OK' if good else 'FAIL'}")
    rng = np.random.default_rng(0)
    flat = (rng.standard_normal(450) * 0.05).tolist()
    _, snr = estimate_bpm(flat, 30)
    good = snr < 12
    ok &= good
    print(f"  DSP flat signal -> SNR {snr:.1f} "
          f"({'OK, not misread as real' if good else 'FAIL'})")

    # (b) Verdict mapping on synthetic series.
    t, sig = _synth_pulse_series(72, seconds=15)
    r = analyze_series(t, sig, frames_with_face=len(sig))
    good = r["verdict"] == "real-face-supported" and abs(r["bpm"] - 72) < 3
    ok &= good
    print(f"  verdict strong pulse -> {r['verdict']} "
          f"(bpm {r['bpm']:.1f}, snr {r['snr']:.1f}, "
          f"conf {r['confidence']:.2f})  {'OK' if good else 'FAIL'}")

    t, sig = _synth_pulse_series(72, seconds=15)
    flat_sig = (np.random.default_rng(1).standard_normal(len(sig)) * 0.05).tolist()
    r = analyze_series(t, flat_sig, frames_with_face=len(sig))
    good = r["verdict"] != "real-face-supported"
    ok &= good
    print(f"  verdict flat 15 s -> {r['verdict']} (snr {r['snr']:.1f})  "
          f"{'OK' if good else 'FAIL: misread as real!'}")

    t2, sig2 = _synth_pulse_series(72, seconds=2)
    r = analyze_series(t2, sig2, frames_with_face=len(sig2))
    good = r["verdict"] == "insufficient-signal"
    ok &= good
    print(f"  verdict 2 s clip -> {r['verdict']}  {'OK' if good else 'FAIL'}")

    r = analyze_series([], [], frames_with_face=0)
    good = r["verdict"] == "no-face"
    ok &= good
    print(f"  verdict no face frames -> {r['verdict']}  {'OK' if good else 'FAIL'}")

    print("PULSE SELF-TEST", "PASSED" if ok else "FAILED")
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if self_test() else 1)

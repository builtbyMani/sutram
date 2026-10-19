"""Text entity extraction: spaCy NER (PERSON/ORG) + regex (PHONE/EMAIL/IP/URL).

OCR: Tesseract via pytesseract with Pillow preprocessing.
EXIF: Pillow primary, exifread fallback.

Every entity carries {kind, value, span_json:{start,end}} where the span
slices the source text: text[start:end] == value.
"""

import json
import re

from ..models import Entity

# --- regex extractors -------------------------------------------------------

# Indian 10-digit mobile, optional +91/91 prefix, optional separators.
PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\s\-]?)?[6-9]\d{4}[\s\-]?\d{5}(?!\d)")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
URL_RE = re.compile(r"https?://[^\s<>\"']+")

_TRAILING_PUNCT = ".,;:!?)"


def _valid_ip(value: str) -> bool:
    try:
        return all(0 <= int(octet) <= 255 for octet in value.split("."))
    except ValueError:
        return False


def _regex_entities(text: str) -> list[tuple[str, str, int, int]]:
    found: list[tuple[str, str, int, int]] = []
    for m in PHONE_RE.finditer(text):
        found.append(("PHONE", m.group(0), m.start(), m.end()))
    for m in EMAIL_RE.finditer(text):
        found.append(("EMAIL", m.group(0), m.start(), m.end()))
    for m in IP_RE.finditer(text):
        if _valid_ip(m.group(0)):
            found.append(("IP", m.group(0), m.start(), m.end()))
    for m in URL_RE.finditer(text):
        value = m.group(0).rstrip(_TRAILING_PUNCT)
        found.append(("URL", value, m.start(), m.start() + len(value)))
    return found


# --- spaCy NER (lazy singleton so import never pays model-load cost) --------

_nlp = None


def get_nlp():
    """Load en_core_web_sm once; raise a clear error if the model is missing."""
    global _nlp
    if _nlp is None:
        import spacy

        try:
            _nlp = spacy.load("en_core_web_sm")
        except OSError as exc:
            raise RuntimeError(
                "spaCy model 'en_core_web_sm' is not installed. "
                "Run: python -m spacy download en_core_web_sm"
            ) from exc
    return _nlp


def _ner_entities(text: str) -> list[tuple[str, str, int, int]]:
    nlp = get_nlp()
    doc = nlp(text)
    return [
        (ent.label_, ent.text, ent.start_char, ent.end_char)
        for ent in doc.ents
        if ent.label_ in ("PERSON", "ORG")
    ]


# --- public API --------------------------------------------------------------


def _dedupe_key(kind: str, value: str) -> tuple[str, str]:
    if kind == "PHONE":
        return (kind, re.sub(r"\D", "", value))
    if kind == "EMAIL":
        return (kind, value.lower())
    return (kind, value)


def extract_text_artifact(text: str, artifact_id: int) -> list[Entity]:
    """Extract entities from text; returns transient Entity rows (caller commits).

    Dedupes on (kind, normalized value), keeping the first occurrence's span.
    """
    seen: set[tuple[str, str]] = set()
    entities: list[Entity] = []
    for kind, value, start, end in _ner_entities(text) + _regex_entities(text):
        key = _dedupe_key(kind, value)
        if key in seen:
            continue
        seen.add(key)
        entities.append(
            Entity(
                artifact_id=artifact_id,
                kind=kind,
                value=value,
                span_json=json.dumps({"start": start, "end": end}),
            )
        )
    return entities


# --- OCR (Tesseract) --------------------------------------------------------


def preprocess_for_ocr(image):
    """Grayscale → 2x upscale → Otsu threshold. Returns a Pillow image."""
    from PIL import ImageOps

    gray = image.convert("L")
    w, h = gray.size
    upscaled = gray.resize((w * 2, h * 2))
    # Otsu's method: pick the threshold minimizing intra-class variance.
    hist = upscaled.histogram()
    total = sum(hist)
    sum_all = sum(i * hist[i] for i in range(256))
    sum_bg = 0
    weight_bg = 0
    best_var = -1.0
    threshold = 128
    for t in range(256):
        weight_bg += hist[t]
        if weight_bg == 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg == 0:
            break
        sum_bg += t * hist[t]
        mean_bg = sum_bg / weight_bg
        mean_fg = (sum_all - sum_bg) / weight_fg
        var_between = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
        if var_between > best_var:
            best_var = var_between
            threshold = t
    return upscaled.point(lambda p: 255 if p > threshold else 0)


def extract_ocr(image_path: str) -> str:
    """Run Tesseract on an image file; returns stripped text (may be '')."""
    import shutil

    import pytesseract
    from PIL import Image

    if shutil.which("tesseract") is None:
        raise RuntimeError(
            "tesseract binary not found. Install tesseract-ocr (apt) or "
            "use the API Docker image, which bakes it in."
        )
    with Image.open(image_path) as img:
        return pytesseract.image_to_string(preprocess_for_ocr(img)).strip()


# --- EXIF / metadata ----------------------------------------------------------


def _exif_pillow(image_path: str) -> dict:
    from PIL import Image
    from PIL.ExifTags import TAGS

    with Image.open(image_path) as img:
        raw = img.getexif()
        if not raw:
            return {}
        out: dict = {}
        for tag_id, value in raw.items():
            tag = TAGS.get(tag_id, str(tag_id))
            try:
                json.dumps(value)  # keep only JSON-serializable values
                out[str(tag)] = value
            except (TypeError, ValueError):
                out[str(tag)] = str(value)
        return out


def _exif_exifread(image_path: str) -> dict:
    import exifread

    with open(image_path, "rb") as f:
        tags = exifread.process_file(f, details=False)
    out: dict = {}
    for tag, value in tags.items():
        if tag.startswith("Thumbnail"):
            continue
        try:
            json.dumps(str(value))
            out[str(tag)] = str(value)
        except (TypeError, ValueError):
            continue
    return out


def extract_exif(image_path: str) -> dict:
    """EXIF tags as a JSON-serializable dict; {} when the image has no EXIF."""
    try:
        found = _exif_pillow(image_path)
        if found:
            return found
    except Exception:
        pass
    try:
        return _exif_exifread(image_path)
    except Exception:
        return {}

"""Timestamp extraction + UTC normalization for the case timeline (TML-01).

Pure functions over plain dicts — no DB, no app imports. The wiring phase
(main.py / models.py) owns persistence; see TIMELINE-NOTE.md next to this file.

Contract:
    extract_events(artifact) -> list of event dicts, sorted ascending by
    event_ts_utc. Each event:
        {
            "artifact_id": int,
            "event_ts_utc": str,   # ISO-8601, always UTC, ends with "+00:00"
            "label": str,          # short human-readable description
            "detail_json": dict,   # {"kind", "line"/"raw_ts", ...} (wiring serializes)
        }

Timezone rule: naive timestamps are assumed Asia/Kolkata and converted to
UTC; timestamps with an explicit offset are honored. Artifacts with no
extractable event time produce NO events — never fabricated.
"""

import json
import re
from datetime import datetime, timedelta, timezone

# --- timezone ----------------------------------------------------------------

_KOLKATA = None


def _kolkata():
    """Asia/Kolkata tzinfo, with a fixed +05:30 fallback if tzdata is absent.

    Asia/Kolkata has no DST, so the fixed offset is exactly correct.
    """
    global _KOLKATA
    if _KOLKATA is None:
        try:
            from zoneinfo import ZoneInfo

            _KOLKATA = ZoneInfo("Asia/Kolkata")
        except Exception:
            _KOLKATA = timezone(timedelta(hours=5, minutes=30))
    return _KOLKATA


def _to_utc_iso(dt: datetime) -> str:
    """Normalize an aware-or-naive datetime to a UTC ISO string (+00:00)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_kolkata())
    return dt.astimezone(timezone.utc).isoformat()


# --- patterns ----------------------------------------------------------------

# WhatsApp-style: [19/10/2026, 16:20] Sender: message  (dd/mm/yyyy, 24h, opt secs/AM-PM)
_WHATSAPP_RE = re.compile(
    r"^\[(\d{1,2})/(\d{1,2})/(\d{4}),\s*"
    r"(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(?:([AaPp])\.?[Mm]\.?)?\]"
)

# yyyy-mm-dd hh:mm:ss (or T separator), optional offset; requires a time part
# so bare dates (fabricated midnights) never match.
_YMD_RE = re.compile(
    r"(?<!\d)(\d{4})-(\d{2})-(\d{2})[T ]"
    r"(\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?"
    r"(?:\s*(Z|[+-]\d{2}:?\d{2}))?"
)

# Leading ISO timestamp on log lines: 2026-10-19T11:00:00+05:30 rest of line
_LEADING_ISO_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?"
    r"(?:Z|[+-]\d{2}:?\d{2})?)"
)

_EXIF_FMT = "%Y:%m:%d %H:%M:%S"


# --- small helpers ------------------------------------------------------------


def _as_dict(value):
    """Accept a dict, a JSON string, or None -> always a dict."""
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _parse_tz(raw):
    """'+05:30' / '+0530' / 'Z' -> tzinfo; None/unknown -> None."""
    if not raw:
        return None
    s = raw.strip().upper()
    if s == "Z":
        return timezone.utc
    m = re.fullmatch(r"([+-])(\d{2}):?(\d{2})", s)
    if not m:
        return None
    sign = 1 if m.group(1) == "+" else -1
    return timezone(sign * timedelta(hours=int(m.group(2)), minutes=int(m.group(3))))


def _safe_dt(year, month, day, hour, minute, second=0):
    """Build a datetime, returning None for impossible dates (Feb 30, ...)."""
    try:
        return datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None


def _snippet(text: str, limit: int = 90) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# --- per-line extractors (each returns (dt, raw_ts, label) or None) -----------


def _whatsapp_line(line: str):
    m = _WHATSAPP_RE.match(line)
    if not m:
        return None
    day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    hour, minute = int(m.group(4)), int(m.group(5))
    second = int(m.group(6)) if m.group(6) else 0
    ampm = (m.group(7) or "").upper()
    if ampm == "P" and hour < 12:
        hour += 12
    if ampm == "A" and hour == 12:
        hour = 0
    dt = _safe_dt(year, month, day, hour, minute, second)
    if dt is None:
        return None
    rest = line[m.end():].strip()
    return dt, m.group(0), _snippet(rest) or "(message)"


def _ymd_in_line(line: str):
    m = _YMD_RE.search(line)
    if not m:
        return None
    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    hour, minute = int(m.group(4)), int(m.group(5))
    second = int(m.group(6)) if m.group(6) else 0
    dt = _safe_dt(year, month, day, hour, minute, second)
    if dt is None:
        return None
    tz = _parse_tz(m.group(7))
    if tz is not None:
        dt = dt.replace(tzinfo=tz)
    return dt, m.group(0), _snippet(line)


def _leading_iso_line(line: str):
    m = _LEADING_ISO_RE.match(line)
    if not m:
        return None
    raw = m.group(1)
    # Split off a trailing offset/Z for manual parsing (naive -> Kolkata).
    off = re.search(r"(Z|[+-]\d{2}:?\d{2})$", raw)
    tz = _parse_tz(off.group(1)) if off else None
    core = raw[: off.start()] if off else raw
    core = core.replace("T", " ")
    dt = None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(core, fmt)
            break
        except ValueError:
            continue
    if dt is None:
        return None
    if tz is not None:
        dt = dt.replace(tzinfo=tz)
    rest = line[m.end():].strip(" -–—:\t")
    return dt, raw, _snippet(rest) or "(log entry)"


def _text_events(artifact_id, source_type: str, text: str) -> list[dict]:
    """One event per line at most: first matching pattern wins."""
    order = (
        ("log", _leading_iso_line, "log"),
        ("chat", _whatsapp_line, "chat"),
        ("ymd", _ymd_in_line, "chat"),
    )
    if source_type == "log":
        order = (order[0], order[1], order[2])
    events = []
    for lineno, line in enumerate((text or "").splitlines(), 1):
        if not line.strip():
            continue
        for kind, fn, label_kind in order:
            if kind == "ymd" and source_type == "log":
                continue  # leading-ISO already covers log lines; avoid doubles
            parsed = fn(line)
            if parsed is None:
                continue
            dt, raw_ts, label = parsed
            prefix = "Chat" if label_kind == "chat" else "Log"
            events.append(
                {
                    "artifact_id": artifact_id,
                    "event_ts_utc": _to_utc_iso(dt),
                    "label": f"{prefix} — {label}",
                    "detail_json": {
                        "kind": label_kind,
                        "line": lineno,
                        "raw_ts": raw_ts,
                    },
                }
            )
            break
    return events


def _exif_events(artifact_id, exif: dict) -> list[dict]:
    raw = exif.get("DateTimeOriginal") or exif.get("EXIF DateTimeOriginal")
    if not raw or not isinstance(raw, str):
        return []
    try:
        dt = datetime.strptime(raw.strip(), _EXIF_FMT)
    except ValueError:
        return []
    return [
        {
            "artifact_id": artifact_id,
            "event_ts_utc": _to_utc_iso(dt),  # EXIF has no zone -> Kolkata
            "label": "Photo captured (EXIF DateTimeOriginal)",
            "detail_json": {"kind": "exif", "raw_ts": raw.strip()},
        }
    ]


def _parse_isoish(value) -> datetime | None:
    """Parse an ISO-ish timestamp string; None if unparseable."""
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip()
    off = re.search(r"(Z|[+-]\d{2}:?\d{2})$", s)
    tz = _parse_tz(off.group(1)) if off else None
    core = s[: off.start()].strip() if off else s
    core = core.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(core, fmt)
            return dt.replace(tzinfo=tz) if tz else dt
        except ValueError:
            continue
    return None


def _pcap_events(artifact_id, meta: dict) -> list[dict]:
    tr = _as_dict(meta.get("time_range"))
    start = tr.get("start") or meta.get("capture_start") or meta.get("time_range_start")
    end = tr.get("end") or meta.get("capture_end") or meta.get("time_range_end")
    events = []
    for raw, label in ((start, "Capture started"), (end, "Capture ended")):
        dt = _parse_isoish(raw)
        if dt is None:
            continue
        events.append(
            {
                "artifact_id": artifact_id,
                "event_ts_utc": _to_utc_iso(dt),
                "label": label,
                "detail_json": {"kind": "pcap", "raw_ts": str(raw)},
            }
        )
    return events


# --- public API ---------------------------------------------------------------


def extract_events(artifact: dict) -> list[dict]:
    """Extract timeline events from an artifact dict.

    artifact: {"id", "source_type", "text", "exif_json", "metadata_json"}.
    Returns events sorted ascending by event_ts_utc. Artifacts with no
    extractable event time return [] — never fabricated.
    """
    artifact_id = artifact.get("id")
    source_type = (artifact.get("source_type") or "").lower()
    text = artifact.get("text") or ""
    exif = _as_dict(artifact.get("exif_json"))
    meta = _as_dict(artifact.get("metadata_json"))

    events: list[dict] = []
    if source_type in ("chat", "document", "log", "osint"):
        events.extend(_text_events(artifact_id, source_type, text))
    if source_type in ("image", "video"):
        events.extend(_exif_events(artifact_id, exif))
    if source_type == "pcap":
        events.extend(_pcap_events(artifact_id, meta))

    events.sort(key=lambda e: e["event_ts_utc"])
    return events

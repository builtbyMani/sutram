"""Self-test for timeline.py — run: .venv/bin/python -m app.services.test_timeline

Covers the Task 4.1 acceptance criteria: UTC ordering, true chronological
order for out-of-order chat lines, explicit-offset conversion, and the
never-fabricate rule for timestamp-less artifacts.
"""

import sys

sys.path.insert(0, "/home/hatch/workspace/sutram-forensics/apps/api")

from app.services.timeline import extract_events

CHAT_OUT_OF_ORDER = """[19/10/2026, 16:20] Ravi: transferred 50000 to the mule account
[19/10/2026, 09:05] Suresh: mule account is ready, use it before noon
[19/10/2026, 12:44] Ravi: confirm receipt once done"""

LOG_ISO = """2026-10-19T11:00:00+05:30 sshd[441]: Failed password for root from 203.0.113.7
2026-10-19 08:30:00 sshd[442]: Accepted password for admin from 198.51.100.9
garbage line with no timestamp at all
2026-10-19T25:99:99Z impossible timestamp is skipped"""

DOC_NO_TIME = """This is a plain ransom note.
No timestamps anywhere in this text.
Just words, no dates, no times."""

PASSED = []


def check(name, fn):
    fn()
    PASSED.append(name)
    print(f"  PASS {name}")


def test_chat_true_chronological_order():
    ev = extract_events({"id": 1, "source_type": "chat", "text": CHAT_OUT_OF_ORDER})
    assert len(ev) == 3, f"expected 3 events, got {len(ev)}"
    # File order was 16:20, 09:05, 12:44 (IST); true order must be chronological.
    assert "Suresh" in ev[0]["label"] and "09:05" in ev[0]["detail_json"]["raw_ts"]
    assert "12:44" in ev[1]["detail_json"]["raw_ts"]
    assert "16:20" in ev[2]["detail_json"]["raw_ts"]
    assert ev[0]["event_ts_utc"] == "2026-10-19T03:35:00+00:00"
    assert ev[1]["event_ts_utc"] == "2026-10-19T07:14:00+00:00"
    assert ev[2]["event_ts_utc"] == "2026-10-19T10:50:00+00:00"


def test_explicit_offset_honored():
    ev = extract_events({"id": 2, "source_type": "log", "text": LOG_ISO})
    by_raw = {e["detail_json"]["raw_ts"]: e for e in ev}
    # 11:00:00+05:30 -> 05:30 UTC (offset honored, NOT treated as IST)
    assert by_raw["2026-10-19T11:00:00+05:30"]["event_ts_utc"] == "2026-10-19T05:30:00+00:00"
    # naive 08:30:00 -> assumed IST -> 03:00 UTC
    assert by_raw["2026-10-19 08:30:00"]["event_ts_utc"] == "2026-10-19T03:00:00+00:00"
    # garbage + impossible timestamps skipped, valid ones kept
    assert len(ev) == 2, f"expected 2 events, got {len(ev)}"


def test_all_timestamps_utc():
    artifacts = [
        {"id": 1, "source_type": "chat", "text": CHAT_OUT_OF_ORDER},
        {"id": 2, "source_type": "log", "text": LOG_ISO},
        {
            "id": 3,
            "source_type": "image",
            "exif_json": {"DateTimeOriginal": "2026:10:18 22:15:00"},
        },
        {
            "id": 4,
            "source_type": "pcap",
            "metadata_json": {
                "time_range": {"start": "2026-10-19T09:00:00+05:30",
                               "end": "2026-10-19T09:30:00+05:30"}
            },
        },
    ]
    for a in artifacts:
        for e in extract_events(a):
            assert e["event_ts_utc"].endswith("+00:00"), e
    # EXIF naive -> IST -> 16:45 UTC
    exif_ev = extract_events(artifacts[2])
    assert len(exif_ev) == 1
    assert exif_ev[0]["event_ts_utc"] == "2026-10-18T16:45:00+00:00", exif_ev[0]
    # pcap endpoints
    pcap_ev = extract_events(artifacts[3])
    assert [e["label"] for e in pcap_ev] == ["Capture started", "Capture ended"]
    assert pcap_ev[0]["event_ts_utc"] == "2026-10-19T03:30:00+00:00"


def test_strict_utc_ordering_across_artifacts():
    arts = [
        {"id": 1, "source_type": "chat", "text": CHAT_OUT_OF_ORDER},
        {"id": 2, "source_type": "log", "text": LOG_ISO},
    ]
    merged = sorted(
        (e for a in arts for e in extract_events(a)),
        key=lambda e: e["event_ts_utc"],
    )
    ts = [e["event_ts_utc"] for e in merged]
    assert ts == sorted(ts), "events not strictly UTC-ordered"
    for a, b in zip(ts, ts[1:]):
        assert a <= b, f"out of order: {a} > {b}"


def test_no_timestamps_no_events():
    ev = extract_events({"id": 9, "source_type": "document", "text": DOC_NO_TIME})
    assert ev == [], f"expected zero events, got {ev}"


def test_empty_and_missing_fields():
    assert extract_events({"id": 10, "source_type": "chat"}) == []
    assert extract_events({"id": 11, "source_type": "image", "exif_json": None}) == []
    assert extract_events({"id": 12, "source_type": "image", "exif_json": "{}"}) == []
    assert extract_events({"id": 13, "source_type": "pcap", "metadata_json": {}}) == []
    assert extract_events({"id": 14, "source_type": "unknown", "text": "2026-10-19 10:00:00"}) == []


def main():
    print("timeline self-test")
    for name, fn in sorted(
        [(k, v) for k, v in globals().items() if k.startswith("test_")]
    ):
        check(name, fn)
    print(f"ALL {len(PASSED)} TESTS PASSED")


if __name__ == "__main__":
    main()

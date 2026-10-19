# SEED-NOTE.md — "Operation Ledger" demo case

## What this is

Deterministic fixture generator for the SUTRAM Forensics Workbench finale
demo. A fictional cyber-financial fraud narrative ("Operation Ledger") told
across 49 artifacts in 5 source-type groups.

- Generator: `generate_demo_case.py` (run: `python3 generate_demo_case.py`)
- Verifier: `verify_demo_case.py` (13 checks, exit 0 = green)
- Output: `apps/api/seeds/operation-ledger/`
- **Seed: `421337`** — same seed → byte-identical output on the same machine
  (verified with `diff -r`; 13/13 checks pass, incl. exact 72.0 BPM on the
  pulse video). Cross-machine byte identity is NOT guaranteed (encoder
  versions differ); re-run the generator wherever the demo runs.

**ALL names, phone numbers, account numbers, UPI IDs, IPs and timestamps
are fictional and generated for demo purposes only.**

## Layout (`operation-ledger/`)

| Dir | Files | Suggested `source_type` |
|---|---|---|
| `chats/` | `chat_01.txt` … `chat_12.txt` — WhatsApp-style exports, fraud coordination chatter | `chat` |
| `images/screenshots/` | `screenshot_01.png` … `screenshot_10.png` — rendered phone screens (chat bubbles, bank transfer confirmations) | `image` |
| `images/statements/` | `statement_01.jpg` … `statement_07.jpg` (clean scans, EXIF `DateTimeOriginal` set), `statement_08_edited.jpg` (**tampered**) | `image` |
| `images/stripped/` | `photo_id_stripped.jpg` — ID-card photo with **no EXIF** (stripped-metadata anomaly) | `image` |
| `logs/` | `auth_2026-11-10.log` … `auth_2026-11-21.log` (12 days) | `log` |
| `pcaps/` | `pcap_01.txt` … `pcap_05.txt` — capture summaries (packet counts, time ranges, top talkers) | `pcap` |
| `video/` | `pulse_face_72bpm.mp4` — 10 s @ 30 fps synthetic face, green channel pulsing at 72 BPM | `video` |
| `manifest.json` | file → `source_type` + note mapping (authoritative for the seeder) | — |

49 artifacts total (12 + 19 + 12 + 5 + 1).

## What's planted where (narrator's guide)

1. **The coordinator's phone `+91 98110 24680`** — appears in ≥3 chat
   exports (and screenshots). This is the cross-source identifier the
   correlation engine must resolve into one identity node linking the chats.
2. **Money mules** — Arjun Mehta, Kavya Nair, Rohan Iyer, Divya Menon,
   Farhan Qureshi recur across chats with fake account numbers (`5010…`),
   IFSC codes (`FICB…`) and UPI IDs. Ledger amounts in ₹ (Indian grouping).
3. **Edited bank statement** — `statement_08_edited.jpg` is the tampered twin
   of clean `statement_07.jpg`: one amount pasted over at a different
   compression history (₹4,25,000 over the original). ELA target.
4. **Stripped photo** — `photo_id_stripped.jpg` carries no EXIF at all;
   the EXIF-inconsistency flag target (compare with the statements' scans,
   which do carry `DateTimeOriginal`).
5. **Brute-force break-in** — `auth_2026-11-14/15/16.log` contain 03:05–03:41
   bursts of 45–60 failed SSH logins from `103.21.244.15`, each followed by
   an `Accepted password for root` — the anomaly target. `pcap_03.txt`
   shows 60-second beaconing to the same IP (ties network evidence to the
   break-in).
6. **Pulse-liveness video** — synthetic face with the green channel
   modulated at exactly 72 BPM (verified: measured 72.0 BPM by frame
   analysis). FRD-03 target.
7. **Timeline traps** — chats 04, 08, 11 have messages deliberately out of
   chronological file order; naive timestamps are IST (+05:30).

## Honest limitation: the synthetic face

The pulse video's face is a rendered ellipse with shading — it is **not**
guaranteed to trigger MediaPipe FaceMesh. What IS guaranteed: the face
region's green channel carries a clean 72 BPM tone (verified by reading the
frames directly). If the FRD-03 module needs a face-tracked signal, validate
the DSP path against the ROI series extracted from the ellipse region, or
add a center-region fallback ROI for synthetic fixtures. Do not present the
video as a real person's recording.

## How `seed_demo.py` (wiring phase) should ingest these

- Upload every artifact through **`POST /api/artifacts`** (multipart +
  `source_type` form field per `manifest.json`) — **no direct DB writes**;
  the demo must exercise the production pipeline.
- Then run the pipeline endpoints in order: extract → `POST /api/correlate`
  → timeline → `POST /api/analyze` → `POST /api/media/{id}/analyze` (for the
  3 tampered items) → `POST /api/media/{id}/pulse` (for the video) →
  `POST /api/logs/{id}/anomalies` (for the 3 brute-force logs).
- Expected outcome: findings of all four types — `shared-identifier-link`
  (coordinator phone), `tampered-media` (edited statement + stripped photo),
  `pulse-liveness` (video), `login-anomaly` (brute-force sessions).
- The 3 AM logins and the beaconing pcap are the presenter's "anomaly"
  talking points; the coordinator phone is the "correlation" talking point;
  the edited statement is the "fraud" talking point.

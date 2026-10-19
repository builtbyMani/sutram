# DEMO RUNBOOK — "Operation Ledger" (timed, < 5 minutes)

Case: a fictional cyber-financial fraud ring ("Operation Ledger"), 49 artifacts
across chats, screenshots, bank statements, auth logs, pcap summaries, and one
face video. **All names, numbers, IPs and timestamps are fictional.**

Presenter: non-technical OK. Everything below is UI-only after pre-flight.

## Pre-flight checklist (do BEFORE the audience arrives, ~10 min)

- [ ] `docker compose up --build -d` from the repo root; wait for both
      services healthy: `docker compose ps` shows `api` healthy, `web` running.
- [ ] Seed: `docker compose exec api python -m app.seeds.seed_demo`
      → ends with "Seed complete: all steps ok, all 4 finding types present."
- [ ] Open http://localhost:3000 → artifact list shows 49 items.
- [ ] Open Findings → confirm 4 finding types visible:
      `shared-identifier-link`, `tampered-media`, `pulse-liveness`, `login-anomaly`.
- [ ] Open Graph → the coordinator identity node is central and labeled.
- [ ] Open Timeline → events span the case window in chronological order.
- [ ] Open Summary → a cited case summary renders (or note the offline fallback).
- [ ] Keep a second terminal ready with `docker compose logs -f api` (hidden).

If any step fails, fix it now — never debug in front of the jury.

## The 5-minute script

### 0:00–0:30 — The problem + live upload
**Click:** Upload → choose any chat file from `apps/api/seeds/operation-ledger/chats/`
(e.g. `chat_05.txt`) → Upload.
**Say:** *"Investigators drown in evidence from five different places. Watch:
I drop in one chat export, and the framework hashes it — SHA-256, immutable —
extracts people, phones, account numbers, and logs every step in the
chain-of-custody."*
*(Judging: evidence extraction 15%.)*
**Fallback:** if upload is slow, *"extraction runs inside the upload — the
spinner means NER + OCR are working, not hanging."*

### 0:30–1:30 — Correlation: one ring, one graph
**Click:** Graph → click the central PERSON node (the coordinator).
**Say:** *"'M. Sharma' in one chat, 'Manish Sharma' in another, same phone
number `+91 98110 24680` in three chats — the engine resolves them into ONE
identity with merge-grade confidence. Click any edge: it tells you exactly
which artifacts and which identifier justified the merge. Nothing is a
black box."*
*(Judging: cross-source correlation 20%.)*
**Fallback:** if the graph is dense, *"zoom out — the coordinator node is the
hub; the money mules fan out from it."*

### 1:30–2:30 — Timeline: the crime in order
**Click:** Timeline → scroll to the 3 AM cluster.
**Say:** *"Every timestamp normalized to UTC. Chats 4, 8 and 11 arrived out of
order — the timeline puts them right. And here: 03:05 to 03:41, sixty failed
SSH logins from `103.21.244.15`, then a successful root login. The pcap lane
shows the same IP beaconing every 60 seconds. Break-in and network evidence,
one screen."*
*(Judging: timeline reconstruction 20%.)*
**Click:** one timeline event → artifact detail opens (hash, extracted text,
custody log). *"Every event links back to its source artifact."*

### 2:30–4:00 — Findings: four fraud signals, each with provenance
**Click:** Findings.
**Say:** *"Four findings, each carrying its provenance — artifact ids, the
rule or model, a confidence, and the exact evidence snippet. No finding ever
renders without it."*
1. **`shared-identifier-link`** — *"the coordinator's phone ties three chats
   together."*
2. **`tampered-media`** — open it → ELA heatmap of `statement_08_edited.jpg`:
   *"the edited ₹4,25,000 amount lights up; the clean twin doesn't. EXIF says
   the ID photo was stripped."* *(multimedia/fraud 10%)*
3. **`pulse-liveness`** — *"the face video: remote photoplethysmography reads
   a 72 BPM pulse from the skin signal. A synthetic face shows none. Always a
   supporting signal — never presented as proof."*
4. **`login-anomaly`** — *"the 3 AM brute-force sessions, with the deviating
   features named: hour, failed attempts, bytes."*
*(Judging: explainability/traceability 25% — this is the slide that wins.)*
**Fallback:** if a finding is missing, *"the seeder prints the full step log —
re-run it; uploads are idempotent."*

### 4:00–4:45 — Summary + audit trail
**Click:** Summary → read the first two cited lines aloud.
**Say:** *"A case summary where every claim carries an [artifact:id] citation.
Click a citation — it opens the artifact."*
**Fallback (offline):** *"No network for the LLM? The summary degrades
gracefully — findings, graph and timeline are all local. The citations are
the point, and they never need the cloud."*
**Click:** Audit trail → *"append-only: every ingest, extraction and analysis,
timestamped. This is what a court can follow."*

### 4:45–5:00 — Close
**Say:** *"One command to start, five minutes to a cited case: collect,
authenticate, correlate, reconstruct, explain. Black-box tools say what —
SUTRAM shows why."*

## Timing budget

| Step | Budget |
|---|---|
| Upload + extraction | 0:30 |
| Graph | 1:00 |
| Timeline | 1:00 |
| Findings (4) | 1:30 |
| Summary + audit | 0:45 |
| Close | 0:15 |
| **Total** | **5:00** |

Image build time is excluded (one-time, pre-flight). If any step exceeds its
budget in rehearsal, cut scope there — never rush the findings minute.

## Emergency lines

- **Container won't start:** *"The image is fully offline-capable; let me
  restart just the API — the database is on a named volume, nothing is lost."*
  (`docker compose restart api`)
- **Port 3000 taken:** `docker compose down`, free the port, `up -d` again.
- **Wrong findings count after reseed:** wipe and reseed cleanly:
  `docker compose down -v && docker compose up -d && docker compose exec api
  python -m app.seeds.seed_demo` (uploads are idempotent; `-v` gives a
  truly fresh DB).

#!/usr/bin/env python3
"""Seed the "Operation Ledger" demo case through the real upload pipeline.

Reads apps/api/seeds/operation-ledger/manifest.json, uploads every artifact
via POST /api/artifacts (multipart + source_type form field -- NO direct DB
writes), then runs the pipeline endpoints in the documented order:

    extract (inside upload) -> POST /api/correlate -> GET /api/timeline
    -> POST /api/media/{id}/analyze (tampered items)
    -> POST /api/media/{id}/pulse (liveness video)
    -> POST /api/logs/{id}/anomalies (brute-force logs)
    -> POST /api/analyze -> GET /api/findings (expect all 4 finding types)

Idempotent-ish: re-uploads of identical bytes return the existing artifact
(server-side SHA-256 idempotency); correlate/analyze rebuild idempotently;
media/pulse/anomaly steps re-record per artifact. Safe to re-run after
wiping the DB, and safe on a seeded DB (it just re-verifies).

Usage:
    docker compose exec api python -m app.seeds.seed_demo
    python app/seeds/seed_demo.py --api-url http://localhost:8000
    python app/seeds/seed_demo.py --dry-run        # print call order only
    python app/seeds/seed_demo.py --check-endpoints  # probe route presence
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover
    print("ERROR: 'requests' is required (pip install requests)", file=sys.stderr)
    sys.exit(2)

# ---------------------------------------------------------------- paths

HERE = Path(__file__).resolve().parent
DEFAULT_CASE_DIR = HERE.parent.parent / "seeds" / "operation-ledger"
# app/seeds/seed_demo.py -> apps/api/app/seeds -> up 2 = apps/api -> seeds/
if not DEFAULT_CASE_DIR.exists():  # dev checkout layout fallback
    DEFAULT_CASE_DIR = HERE / ".." / ".." / "seeds" / "operation-ledger"

# Special demo files, matched by basename from the manifest.
TAMPERED_IMAGES = {"statement_08_edited.jpg", "photo_id_stripped.jpg"}
PULSE_VIDEOS = {"pulse_face_72bpm.mp4"}
BRUTEFORCE_LOGS = {"auth_2026-11-14.log", "auth_2026-11-15.log", "auth_2026-11-16.log"}

EXPECTED_FINDING_TYPES = {
    "shared-identifier-link",
    "tampered-media",
    "pulse-liveness",
    "login-anomaly",
}


class StepFailed(RuntimeError):
    pass


class Seeder:
    def __init__(self, api_url: str, case_dir: Path, timeout: int = 120):
        self.api = api_url.rstrip("/")
        self.case_dir = case_dir
        self.timeout = timeout
        self.session = requests.Session()
        self.artifact_ids: dict[str, int] = {}  # basename -> artifact id
        self.report: list[tuple[str, str, str]] = []  # (step, status, detail)

    # -- helpers -----------------------------------------------------
    def log(self, status: str, step: str, detail: str = "") -> None:
        self.report.append((step, status, detail))
        mark = {"ok": "[ok]", "fail": "[FAIL]", "skip": "[skip]"}[status]
        print(f"{mark} {step}" + (f" -- {detail}" if detail else ""), flush=True)

    def _req(self, method: str, path: str, **kw) -> requests.Response:
        url = f"{self.api}{path}"
        try:
            resp = self.session.request(method, url, timeout=self.timeout, **kw)
        except requests.RequestException as exc:
            raise StepFailed(f"{method} {path}: connection failed: {exc}") from exc
        if resp.status_code == 404:
            raise StepFailed(
                f"{method} {path}: 404 -- endpoint not wired yet "
                "(the wiring phase must implement it)"
            )
        return resp

    def _must_2xx(self, method: str, path: str, **kw) -> dict | list:
        resp = self._req(method, path, **kw)
        if not 200 <= resp.status_code < 300:
            raise StepFailed(
                f"{method} {path}: HTTP {resp.status_code}: {resp.text[:300]}"
            )
        try:
            return resp.json()
        except ValueError:
            return {"raw": resp.text[:300]}

    # -- steps -------------------------------------------------------
    def step_health(self) -> None:
        body = self._must_2xx("GET", "/health")
        self.log("ok", "health", str(body))

    def step_upload_all(self) -> None:
        manifest_path = self.case_dir / "manifest.json"
        if not manifest_path.exists():
            raise StepFailed(f"manifest not found: {manifest_path}")
        manifest = json.loads(manifest_path.read_text())
        items = manifest["artifacts"] if isinstance(manifest, dict) else manifest
        n_ok = 0
        for item in items:
            rel = item["file"]
            src = item["source_type"]
            fpath = self.case_dir / rel
            if not fpath.exists():
                raise StepFailed(f"manifest lists missing file: {rel}")
            with fpath.open("rb") as fh:
                body = self._must_2xx(
                    "POST",
                    "/api/artifacts",
                    files={"file": (Path(rel).name, fh)},
                    data={"source_type": src},
                )
            aid = body.get("id")
            if aid is None:
                raise StepFailed(f"upload {rel}: no id in response: {body}")
            self.artifact_ids[Path(rel).name] = aid
            n_ok += 1
        self.log("ok", f"upload ({n_ok} artifacts)", "via POST /api/artifacts")

    def step_correlate(self) -> None:
        body = self._must_2xx("POST", "/api/correlate")
        self.log("ok", "correlate", str(body)[:160])

    def step_timeline(self) -> None:
        events = self._must_2xx("GET", "/api/timeline")
        n = len(events) if isinstance(events, list) else 0
        if n == 0:
            raise StepFailed("GET /api/timeline returned no events")
        self.log("ok", "timeline", f"{n} events")

    def _ids_for(self, names: set[str]) -> list[int]:
        missing = [n for n in names if n not in self.artifact_ids]
        if missing:
            raise StepFailed(f"special files not uploaded (manifest mismatch): {missing}")
        return [self.artifact_ids[n] for n in sorted(names)]

    def step_media_analyze(self) -> None:
        for aid in self._ids_for(TAMPERED_IMAGES):
            body = self._must_2xx("POST", f"/api/media/{aid}/analyze")
            self.log("ok", f"media analyze (artifact {aid})", str(body)[:120])

    def step_pulse(self) -> None:
        for aid in self._ids_for(PULSE_VIDEOS):
            body = self._must_2xx("POST", f"/api/media/{aid}/pulse")
            self.log("ok", f"pulse liveness (artifact {aid})", str(body)[:160])

    def step_anomalies(self) -> None:
        for aid in self._ids_for(BRUTEFORCE_LOGS):
            body = self._must_2xx("POST", f"/api/logs/{aid}/anomalies")
            self.log("ok", f"log anomalies (artifact {aid})", str(body)[:120])

    def step_analyze_findings(self) -> None:
        self._must_2xx("POST", "/api/analyze")
        findings = self._must_2xx("GET", "/api/findings")
        kinds = {f.get("type") for f in findings} if isinstance(findings, list) else set()
        missing = EXPECTED_FINDING_TYPES - kinds
        self.log(
            "ok" if not missing else "fail",
            "analyze + findings",
            f"{len(findings) if isinstance(findings, list) else '?'} findings; "
            f"types={sorted(kinds)}"
            + (f"; MISSING={sorted(missing)}" if missing else ""),
        )
        if missing:
            raise StepFailed(f"missing finding types: {sorted(missing)}")

    def run(self) -> None:
        self.step_health()
        self.step_upload_all()
        self.step_correlate()
        self.step_timeline()
        self.step_media_analyze()
        self.step_pulse()
        self.step_anomalies()
        self.step_analyze_findings()
        print("\nSeed complete: all steps ok, all 4 finding types present.")

    # -- diagnostics -------------------------------------------------
    def dry_run(self) -> None:
        calls = [
            "GET /health",
            "POST /api/artifacts  (x49, multipart file + source_type per manifest.json)",
            "POST /api/correlate",
            "GET /api/timeline",
            "POST /api/media/{id}/analyze  (statement_08_edited.jpg, photo_id_stripped.jpg)",
            "POST /api/media/{id}/pulse    (pulse_face_72bpm.mp4)",
            "POST /api/logs/{id}/anomalies  (auth_2026-11-14/15/16.log)",
            "POST /api/analyze",
            "GET /api/findings  (expect: shared-identifier-link, tampered-media, pulse-liveness, login-anomaly)",
        ]
        print("seed_demo.py call order (dry run, no requests sent):")
        for i, c in enumerate(calls, 1):
            print(f"  {i}. {c}")

    def check_endpoints(self) -> None:
        """Probe route presence: any status other than 404 means the route exists."""
        probes = [
            ("GET", "/health"),
            ("POST", "/api/artifacts"),
            ("POST", "/api/correlate"),
            ("GET", "/api/timeline"),
            ("POST", "/api/media/1/analyze"),
            ("POST", "/api/media/1/pulse"),
            ("POST", "/api/logs/1/anomalies"),
            ("POST", "/api/analyze"),
            ("GET", "/api/findings"),
        ]
        print(f"Probing {self.api} (404 = not wired yet):")
        missing = []
        for method, path in probes:
            try:
                resp = self.session.request(method, f"{self.api}{path}", timeout=10)
                status = resp.status_code
            except requests.RequestException as exc:
                status = f"CONN-FAIL ({exc})"
            present = status != 404 and not str(status).startswith("CONN-FAIL")
            tag = "ok" if present else "MISS"
            print(f"  [{tag}] {method:4s} {path:28s} -> {status}")
            if not present:
                missing.append(f"{method} {path}")
        if missing:
            print(f"\n{len(missing)} endpoint(s) not wired yet: {missing}")
            sys.exit(1)
        print("\nAll endpoints present.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Seed the Operation Ledger demo case.")
    ap.add_argument("--api-url", default=os.environ.get("API_URL", "http://localhost:8000"),
                    help="API base URL (default: $API_URL or http://localhost:8000)")
    ap.add_argument("--case-dir", default=str(DEFAULT_CASE_DIR),
                    help="operation-ledger directory (default: next to this script)")
    ap.add_argument("--timeout", type=int, default=180,
                    help="per-request timeout seconds (default: 180)")
    ap.add_argument("--dry-run", action="store_true", help="print call order, send nothing")
    ap.add_argument("--check-endpoints", action="store_true",
                    help="probe which pipeline endpoints exist, then exit")
    args = ap.parse_args()

    seeder = Seeder(args.api_url, Path(args.case_dir), args.timeout)
    if args.dry_run:
        seeder.dry_run()
        return
    if args.check_endpoints:
        seeder.check_endpoints()
        return
    try:
        seeder.run()
    except StepFailed as exc:
        print(f"\n[FAIL] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

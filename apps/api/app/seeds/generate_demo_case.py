#!/usr/bin/env python3
"""Deterministic generator for the "Operation Ledger" demo case.

Produces ~50 fictional artifacts for the SUTRAM Forensics Workbench finale
demo (cyber-financial fraud narrative). Same seed -> byte-identical output
on the same machine (verified with `diff -r`).

Output:  <repo>/apps/api/seeds/operation-ledger/
  chats/        12 WhatsApp-style .txt exports (fraud coordination)
  images/       10 screenshots + 8 bank statements + 1 EXIF-stripped photo
  logs/         12 auth log files (incl. 3 AM brute-force sessions)
  pcaps/        5 pcap summary .txt files
  video/        1 short face video with a pulsing green channel (~72 BPM)
  manifest.json file -> suggested source_type mapping for the seeder

ALL names, phone numbers, account numbers, UPI IDs and IPs below are
fictional and generated for demo purposes only.

Usage:
    python3 generate_demo_case.py [--out DIR] [--seed INT]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SEED = 421337
# Naive datetimes are IST (Asia/Kolkata, UTC+5:30); the timeline module
# treats naive timestamps as IST per the Phase 4 plan.
BASE = datetime(2026, 11, 10, 9, 0, 0)

OUT_DIR = Path(__file__).resolve().parent.parent.parent / "seeds" / "operation-ledger"

# --------------------------------------------------------------------------
# Fictional cast & identifiers (all invented for the demo)
# --------------------------------------------------------------------------
SHARED_PHONE = "+91 98110 24680"          # the coordinator's number; planted in >=3 chats
MULES = [
    ("Arjun Mehta", "+91 98220 13579", "arjun.mule@okhdfcbank"),
    ("Kavya Nair", "+91 98330 24680", "kavya.n@okicici"),
    ("Rohan Iyer", "+91 98440 35791", "rohan.iyer@okaxis"),
    ("Divya Menon", "+91 98550 46802", "divya.m@okhdfcbank"),
    ("Farhan Qureshi", "+91 98660 57913", "farhan.q@oksbi"),
]
OTHERS = [
    ("Neha Kulkarni", "+91 98770 68024"),
    ("Vikram Rao", "+91 98880 79135"),
    ("Sana Sheikh", "+91 98990 80246"),
]
BANK = "Fictional National Bank (DEMO)"
ATTACKER_IP = "103.21.244.15"
VICTIM_HOST = "ledger-web"


def inr(n: int) -> str:
    """Indian digit grouping: 450000 -> 4,50,000."""
    s = str(n)
    if len(s) <= 3:
        return s
    tail, head = s[-3:], s[:-3]
    groups = []
    while len(head) > 2:
        groups.append(head[-2:])
        head = head[:-2]
    groups.append(head)
    return ",".join(reversed(groups)) + "," + tail


# --------------------------------------------------------------------------
# Chats
# --------------------------------------------------------------------------
CHAT_TEMPLATES = [
    "{a}: bro new mule ready, {mule} opened the {bank} account yesterday",
    "{b}: good. account number? send it here, delete after",
    "{a}: {acct} IFSC {ifsc}. daily limit 2L, we stay under it",
    "{b}: ledger updated. {mule} gets 8% on each pass",
    "{a}: {mule} is asking for his cut early, says {amount} stuck since morning",
    "{b}: tell him the settlement hits after the second hop. no early payouts",
    "{a}: call me on {phone}, this chat is getting long",
    "{b}: fine. also rotate the upi id, {upi} is burned",
    "{a}: new id {upi2}, test with 500 first",
    "{b}: police checking cyber cell reports near {city}, keep heads down this week",
    "{a}: moving {amount} tonight in 3 splits, confirm the mule phones are on",
    "{b}: {mule2} ghosted. if he talks, we are done",
    "{a}: relax, he only knows {phone}. nothing else",
    "{b}: ledger total this month {amount}. boss wants the split by friday",
    "{a}: {mule} wants out after this run",
    "{b}: nobody walks out mid-ledger. one more run, then he is free",
]

CITIES = ["Hyderabad", "Pune", "Jaipur", "Lucknow", "Indore"]


def fake_acct(rng: random.Random) -> str:
    return "5010" + "".join(str(rng.randint(0, 9)) for _ in range(12))


def fake_ifsc(rng: random.Random) -> str:
    return "FICB" + "".join(str(rng.randint(0, 9)) for _ in range(7))


def chat_timestamp(rng: random.Random, day_offset: int) -> datetime:
    # mostly daytime IST, occasional 3 AM coordination
    if rng.random() < 0.12:
        t = datetime(2026, 11, 10, 3, 0, 0) + timedelta(minutes=rng.randint(0, 50))
    else:
        t = datetime(2026, 11, 10, 10, 0, 0) + timedelta(minutes=rng.randint(0, 780))
    return t + timedelta(days=day_offset)


def write_chats(rng: random.Random, d: Path, manifest: list) -> None:
    shared_in = 0
    for i in range(12):
        a_name = MULES[i % len(MULES)][0].split()[0]
        b_pool = [m[0].split()[0] for m in MULES if m[0].split()[0] != a_name]
        b_name = rng.choice(b_pool)
        mule = rng.choice(MULES)
        mule2 = rng.choice([m for m in MULES if m != mule])
        day = rng.randint(0, 20)
        n_msg = rng.randint(8, 14)
        ts = chat_timestamp(rng, day)
        lines = []
        for _ in range(n_msg):
            who = a_name if rng.random() < 0.5 else b_name
            tpl = rng.choice(CHAT_TEMPLATES)
            msg = tpl.format(
                a=a_name, b=b_name,
                mule=mule[0], mule2=mule2[0],
                phone=SHARED_PHONE,
                acct=fake_acct(rng), ifsc=fake_ifsc(rng),
                amount="₹" + inr(rng.choice([45000, 90000, 150000, 275000, 450000])),
                upi=mule[2], upi2=mule2[2],
                city=rng.choice(CITIES), bank=BANK,
            )
            # strip the "a:"/"b:" prefix marker, keep "Name:" form
            msg = msg.replace(f"{a_name}: ", "", 1).replace(f"{b_name}: ", "", 1)
            lines.append((ts, who, msg))
            ts += timedelta(minutes=rng.randint(2, 40))
        # some files deliberately out of chronological order (timeline must sort)
        if i in (3, 7, 10):
            rng.shuffle(lines)
        body = "".join(
            f"[{t.strftime('%d/%m/%Y')}, {t.strftime('%H:%M:%S')}] {w}: {m}\n"
            for t, w, m in lines
        )
        # plant the shared phone explicitly in >=3 chats
        if i in (1, 4, 8, 11):
            body += (
                f"[{ts.strftime('%d/%m/%Y')}, {ts.strftime('%H:%M:%S')}] {a_name}: "
                f"save this number {SHARED_PHONE}, only contact on signal\n"
            )
            shared_in += 1
        p = d / f"chat_{i+1:02d}.txt"
        p.write_text(body, encoding="utf-8")
        manifest.append({"file": f"chats/{p.name}", "source_type": "chat",
                         "note": "WhatsApp-style export, fraud coordination"})
    assert shared_in >= 3, "shared phone must appear in >=3 chats"


# --------------------------------------------------------------------------
# Screenshots (Pillow-rendered, OCR-readable)
# --------------------------------------------------------------------------
def _font(size: int):
    # load_default is deterministic across runs on the same machine
    return ImageFont.load_default(size=size)


def render_screenshot(rng: random.Random, idx: int) -> Image.Image:
    w, h = 540, 960
    img = Image.new("RGB", (w, h), (240, 242, 245))
    dr = ImageDraw.Draw(img)
    # status bar
    dr.rectangle([0, 0, w, 44], fill=(18, 140, 126))
    dr.text((16, 12), "09:41", font=_font(20), fill="white")
    kind = rng.choice(["chat", "chat", "bank"])
    if kind == "chat":
        mule = rng.choice(MULES)
        dr.rectangle([0, 44, w, 110], fill=(18, 140, 126))
        dr.text((16, 58), mule[0], font=_font(24), fill="white")
        dr.text((16, 88), "online", font=_font(16), fill=(220, 240, 230))
        msgs = [
            f"Ledger updated: received",
            f"Call me on {SHARED_PHONE}",
            f"UPI {mule[2]} confirmed",
            f"Amount ₹{inr(rng.choice([45000, 90000, 150000]))} moved",
        ]
        y = 140
        for m in rng.sample(msgs, k=rng.randint(2, 4)):
            tw = dr.textbbox((0, 0), m, font=_font(20))
            bw = tw[2] - tw[0] + 28
            dr.rounded_rectangle([16, y, 16 + bw, y + 52], radius=12, fill="white")
            dr.text((30, y + 14), m, font=_font(20), fill="black")
            y += 66
    else:
        dr.rectangle([0, 44, w, 150], fill=(30, 60, 120))
        dr.text((16, 60), BANK, font=_font(22), fill="white")
        dr.text((16, 95), "Transfer Confirmation", font=_font(28), fill="white")
        mule = rng.choice(MULES)
        rows = [
            ("From", "XXXXXX" + fake_acct(rng)[-4:]),
            ("To", mule[0]),
            ("Amount", "₹" + inr(rng.choice([45000, 90000, 275000]))),
            ("UPI Ref", f"{rng.randint(100000000000, 999999999999)}"),
            ("Date", "12/11/2026 14:22 IST"),
            ("Status", "SUCCESS"),
        ]
        y = 190
        for k, v in rows:
            dr.text((24, y), k, font=_font(20), fill=(120, 120, 120))
            dr.text((24, y + 26), v, font=_font(24), fill="black")
            y += 66
    return img


def write_screenshots(rng: random.Random, d: Path, manifest: list) -> None:
    for i in range(10):
        img = render_screenshot(rng, i)
        p = d / f"screenshot_{i+1:02d}.png"
        img.save(p, "PNG")
        manifest.append({"file": f"images/screenshots/{p.name}", "source_type": "image",
                         "note": "rendered phone screen (chat/bank), OCR-readable"})


# --------------------------------------------------------------------------
# Bank statements (JPEG + EXIF; one edited twin)
# --------------------------------------------------------------------------
def render_statement(rng: random.Random, holder: str, acct: str, seed_txns: int) -> Image.Image:
    w, h = 800, 1100
    img = Image.new("RGB", (w, h), "white")
    dr = ImageDraw.Draw(img)
    dr.rectangle([0, 0, w, 110], fill=(20, 60, 110))
    dr.text((24, 20), BANK, font=_font(28), fill="white")
    dr.text((24, 60), "Account Statement  (DEMO DOCUMENT)", font=_font(18), fill=(200, 220, 255))
    dr.text((24, 140), f"Holder: {holder}", font=_font(22), fill="black")
    dr.text((24, 172), f"Account: {acct}", font=_font(22), fill="black")
    dr.text((24, 204), "Period: 01/11/2026 - 28/11/2026", font=_font(22), fill="black")
    y = 260
    dr.text((24, y), "Date", font=_font(20), fill=(100, 100, 100))
    dr.text((200, y), "Description", font=_font(20), fill=(100, 100, 100))
    dr.text((620, y), "Amount (INR)", font=_font(20), fill=(100, 100, 100))
    y += 34
    descs = ["UPI transfer", "NEFT credit", "Cash deposit", "UPI collect", "IMPS transfer"]
    for _ in range(seed_txns):
        day = rng.randint(1, 28)
        amt = rng.choice([5000, 12000, 45000, 75000, 90000, 150000])
        dr.text((24, y), f"{day:02d}/11/2026", font=_font(20), fill="black")
        dr.text((200, y), rng.choice(descs), font=_font(20), fill="black")
        dr.text((620, y), inr(amt), font=_font(20), fill="black")
        y += 32
    dr.text((24, h - 60), "Generated for SUTRAM 2026 demo - all data fictional",
            font=_font(16), fill=(150, 150, 150))
    return img


def exif_bytes(dt_str: str):
    ex = Image.Exif()
    ex[36867] = dt_str  # DateTimeOriginal
    ex[271] = "DEMO-SCANNER"  # Make
    return ex


def write_statements(rng: random.Random, d: Path, manifest: list) -> None:
    # 6 unique clean + 1 clean twin + 1 edited twin of it = 8
    holders = [m[0] for m in MULES] + [o[0] for o in OTHERS[:2]]
    twins = []
    for i in range(7):
        img = render_statement(rng, holders[i], fake_acct(rng), rng.randint(7, 10))
        dt = f"2026:11:{rng.randint(10, 20):02d} 10:22:31"
        p = d / f"statement_{i+1:02d}.jpg"
        img.save(p, "JPEG", quality=85, exif=exif_bytes(dt))
        manifest.append({"file": f"images/statements/{p.name}", "source_type": "image",
                         "note": "bank statement scan with EXIF"})
        if i == 6:
            twins.append((p, img))
    # edited twin: paste a high-contrast box changing one amount, re-save
    clean_path, clean_img = twins[0]
    ed = clean_img.copy()
    dr = ImageDraw.Draw(ed)
    # cover the 3rd transaction amount row with a slightly-off white box
    dr.rectangle([600, 260 + 34 + 64, 780, 260 + 34 + 96], fill=(252, 252, 248))
    dr.text((620, 260 + 34 + 66), inr(425000), font=_font(20), fill="black")
    p = d / "statement_08_edited.jpg"
    ed.save(p, "JPEG", quality=85,
            exif=exif_bytes("2026:11:15 10:22:31"))
    manifest.append({"file": f"images/statements/{p.name}", "source_type": "image",
                     "note": "TAMPERED: amount edited vs statement_07.jpg clean twin (ELA target)"})


def write_stripped_photo(rng: random.Random, d: Path, manifest: list) -> None:
    # ID-card-style photo with NO exif at all -> the "stripped metadata" anomaly
    img = Image.new("RGB", (600, 380), (235, 230, 220))
    dr = ImageDraw.Draw(img)
    dr.rectangle([0, 0, 600, 70], fill=(40, 40, 40))
    dr.text((20, 20), "DEMO IDENTITY CARD - FICTIONAL", font=_font(22), fill="white")
    dr.ellipse([40, 110, 180, 260], fill=(210, 170, 140))  # photo placeholder
    dr.text((220, 120), "Name: Arjun Mehta", font=_font(22), fill="black")
    dr.text((220, 160), "ID: DEMO-00012345", font=_font(22), fill="black")
    dr.text((220, 200), "DOB: 01/01/1990 (fictional)", font=_font(22), fill="black")
    p = d / "photo_id_stripped.jpg"
    img.save(p, "JPEG", quality=88)  # no exif= -> stripped
    manifest.append({"file": f"images/stripped/{p.name}", "source_type": "image",
                     "note": "TAMPERED: photo with EXIF stripped (metadata anomaly)"})


# --------------------------------------------------------------------------
# Auth logs (12 days; 3 contain 3 AM brute-force bursts + break-in)
# --------------------------------------------------------------------------
def write_auth_logs(rng: random.Random, d: Path, manifest: list) -> None:
    brute_days = {4, 5, 6}  # 0-based -> Nov 14/15/16
    users = ["admin", "root", "oracle", "test", "ubuntu"]
    for i in range(12):
        day = BASE + timedelta(days=i)
        lines = []
        # background noise: a few normal logins
        for _ in range(rng.randint(2, 5)):
            t = day + timedelta(hours=rng.randint(8, 20), minutes=rng.randint(0, 59))
            lines.append(
                f"{t.strftime('%b %d %H:%M:%S')} {VICTIM_HOST} sshd[{rng.randint(1000, 9999)}]: "
                f"Accepted password for analyst from 192.168.1.{rng.randint(2, 50)} "
                f"port {rng.randint(1024, 65535)} ssh2"
            )
        if i in brute_days:
            # 3 AM brute-force burst from the attacker IP, then a break-in
            t = day.replace(hour=3, minute=5, second=0)
            for _ in range(rng.randint(45, 60)):
                lines.append(
                    f"{t.strftime('%b %d %H:%M:%S')} {VICTIM_HOST} sshd[{rng.randint(1000, 9999)}]: "
                    f"Failed password for {'invalid user ' if rng.random() < 0.5 else ''}"
                    f"{rng.choice(users)} from {ATTACKER_IP} port {rng.randint(1024, 65535)} ssh2"
                )
                t += timedelta(seconds=rng.randint(2, 9))
            lines.append(
                f"{t.strftime('%b %d %H:%M:%S')} {VICTIM_HOST} sshd[{rng.randint(1000, 9999)}]: "
                f"Accepted password for root from {ATTACKER_IP} port {rng.randint(1024, 65535)} ssh2"
            )
        lines.sort()  # syslog chronological
        p = d / f"auth_{day.strftime('%Y-%m-%d')}.log"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        note = "auth log"
        if i in brute_days:
            note += " - CONTAINS 3AM brute-force burst + break-in (anomaly target)"
        manifest.append({"file": f"logs/{p.name}", "source_type": "log", "note": note})


# --------------------------------------------------------------------------
# Pcap summaries
# --------------------------------------------------------------------------
def write_pcaps(rng: random.Random, d: Path, manifest: list) -> None:
    for i in range(5):
        start = BASE + timedelta(days=rng.randint(0, 18), hours=rng.randint(0, 20))
        end = start + timedelta(minutes=30)
        pkts = rng.randint(20000, 90000)
        beacon = (i == 2)  # one shows C2-like beaconing to the attacker IP
        body = (
            "# pcap summary (generated fixture)\n"
            f"capture_start: {start.strftime('%Y-%m-%dT%H:%M:%S')}+05:30\n"
            f"capture_end:   {end.strftime('%Y-%m-%dT%H:%M:%S')}+05:30\n"
            f"packets: {pkts}\n"
            f"tcp: {rng.uniform(55, 70):.1f}%  udp: {rng.uniform(25, 38):.1f}%  "
            f"icmp: {rng.uniform(2, 9):.1f}%\n"
            "top_talkers:\n"
            f"  192.168.1.14 -> {ATTACKER_IP}  {rng.uniform(8, 20):.1f} MB\n"
            f"  192.168.1.14 -> 142.250.10.5  {rng.uniform(2, 6):.1f} MB\n"
        )
        if beacon:
            body += "notes: periodic 60s beacon to 103.21.244.15 (possible C2)\n"
        p = d / f"pcap_{i+1:02d}.txt"
        p.write_text(body, encoding="utf-8")
        note = "pcap summary"
        if beacon:
            note += " - shows 60s beaconing to attacker IP"
        manifest.append({"file": f"pcaps/{p.name}", "source_type": "pcap", "note": note})


# --------------------------------------------------------------------------
# Pulse video: synthetic face, green channel modulated at 72 BPM
# --------------------------------------------------------------------------
def render_pulse_video(out_path: Path) -> None:
    import cv2
    import numpy as np

    w, h, fps, secs = 320, 240, 30, 10
    n = fps * secs
    freq = 72.0 / 60.0  # 1.2 Hz
    vw = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    cx, cy, ax, ay = w // 2, h // 2, 70, 90
    yy, xx = np.mgrid[0:h, 0:w]
    face = ((xx - cx) / ax) ** 2 + ((yy - cy) / ay) ** 2 <= 1.0
    # simple facial shading so the "face" is not a flat disc
    shade = np.clip(1.0 - 0.25 * (((xx - cx) / ax) ** 2 + ((yy - cy) / ay) ** 2), 0.6, 1.0)
    for i in range(n):
        t = i / fps
        pulse = 18.0 * math.sin(2 * math.pi * freq * t)  # 72 BPM green modulation
        frame = np.zeros((h, w, 3), dtype=np.float32)
        frame[:, :] = (35, 60, 45)  # BGR background
        skin_b, skin_g, skin_r = 150.0, 175.0 + pulse, 200.0
        skin = np.stack([skin_b * shade[face],
                         skin_g * shade[face],
                         skin_r * shade[face]], axis=1)
        frame[face] = skin
        # eyes + mouth shading (helps any face-region heuristic)
        eye = ((xx - cx - 28) / 14) ** 2 + ((yy - cy + 18) / 10) ** 2 <= 1.0
        eye |= ((xx - cx + 28) / 14) ** 2 + ((yy - cy + 18) / 10) ** 2 <= 1.0
        mouth = ((xx - cx) / 26) ** 2 + ((yy - cy - 34) / 9) ** 2 <= 1.0
        frame[eye | mouth] *= 0.55
        vw.write(np.clip(frame, 0, 255).astype(np.uint8))
    vw.release()


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def build(out_dir: Path, seed: int) -> list:
    rng = random.Random(seed)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    chats = out_dir / "chats"
    images = out_dir / "images"
    logs = out_dir / "logs"
    pcaps = out_dir / "pcaps"
    video = out_dir / "video"
    for d in (chats, images / "screenshots", images / "statements",
              images / "stripped", logs, pcaps, video):
        d.mkdir(parents=True, exist_ok=True)

    manifest: list = []
    write_chats(rng, chats, manifest)
    write_screenshots(rng, images / "screenshots", manifest)
    write_statements(rng, images / "statements", manifest)
    write_stripped_photo(rng, images / "stripped", manifest)
    write_auth_logs(rng, logs, manifest)
    write_pcaps(rng, pcaps, manifest)

    vpath = video / "pulse_face_72bpm.mp4"
    render_pulse_video(vpath)
    manifest.append({"file": f"video/{vpath.name}", "source_type": "video",
                     "note": "synthetic face, green channel pulsing at 72 BPM (FRD-03 target)"})

    manifest.sort(key=lambda e: e["file"])
    (out_dir / "manifest.json").write_text(
        json.dumps({"case": "Operation Ledger", "seed": seed,
                    "artifacts": manifest}, indent=2),
        encoding="utf-8",
    )
    return manifest


def main(argv=None) -> Path:
    ap = argparse.ArgumentParser(description="Generate the Operation Ledger demo case")
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args(argv)
    manifest = build(args.out.resolve(), args.seed)
    by_type: dict = {}
    for e in manifest:
        by_type[e["source_type"]] = by_type.get(e["source_type"], 0) + 1
    print(f"wrote {len(manifest)} artifacts to {args.out} (seed={args.seed})")
    for k in sorted(by_type):
        print(f"  {k}: {by_type[k]}")
    # content hash of the whole tree (excludes manifest ordering effects: sorted)
    h = hashlib.sha256()
    for p in sorted(args.out.rglob("*")):
        if p.is_file() and p.name != "manifest.json":
            h.update(p.read_bytes())
    print(f"tree sha256 (excl. manifest): {h.hexdigest()}")
    return args.out


if __name__ == "__main__":
    main()

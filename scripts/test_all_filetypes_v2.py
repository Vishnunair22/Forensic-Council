#!/usr/bin/env python3
"""
Live file-type acceptance + rejection test — Forensic Council.
Runs against http://localhost:8000. Uses unique content per run
to avoid the dedup-cache 409 from previous runs.
"""
import io, json, os, secrets, struct, subprocess, sys, time
import httpx
from PIL import Image as PILImage

BASE = "http://localhost:8000"
PW   = os.environ.get("BOOTSTRAP_INVESTIGATOR_PASSWORD", "")
RUN  = secrets.token_hex(4)   # unique 8-char tag per test run

# ── Auth (double-submit CSRF) ─────────────────────────────────────────────
client = httpx.Client(timeout=60.0)
r = client.post(
    f"{BASE}/api/v1/auth/login",
    data={"username": "investigator", "password": PW},
    headers={"Content-Type": "application/x-www-form-urlencoded"},
)
assert r.status_code == 200, f"Login failed {r.status_code}: {r.text[:200]}"
body  = r.json()
TOKEN = body["access_token"]
CSRF  = client.cookies.get("csrf_token")
HDRS  = {"Authorization": f"Bearer {TOKEN}", "X-CSRF-Token": CSRF}
print(f"Auth OK  role={body['role']}  run_tag={RUN}")

# ── Unique-content helpers ────────────────────────────────────────────────

def _salt() -> bytes:
    return secrets.token_bytes(8)

def pil_img(fmt: str) -> bytes:
    col = tuple(int(b) for b in _salt()[:3])
    img = PILImage.new("RGB", (4, 4), color=col)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()

def hand_wav() -> bytes:
    payload = _salt() * 4          # 32 bytes of unique silence
    fmt = struct.pack("<HHIIHH", 1, 1, 8000, 8000, 1, 8)
    return (
        b"RIFF" + (36 + len(payload)).to_bytes(4, "little") + b"WAVE"
        + b"fmt " + len(fmt).to_bytes(4, "little") + fmt
        + b"data" + len(payload).to_bytes(4, "little") + payload
    )

def hand_pdf() -> bytes:
    tag = RUN.encode()
    lines = [
        b"%PDF-1.4",
        b"%run:" + tag,
        b"1 0 obj<</Type /Catalog /Pages 2 0 R>>endobj",
        b"2 0 obj<</Type /Pages /Kids [3 0 R] /Count 1>>endobj",
        b"3 0 obj<</Type /Page /MediaBox [0 0 612 792] /Parent 2 0 R>>endobj",
        b"xref",
        b"0 4",
        b"0000000000 65535 f ",
        b"0000000016 00000 n ",
        b"0000000068 00000 n ",
        b"0000000126 00000 n ",
        b"trailer<</Size 4 /Root 1 0 R>>",
        b"startxref",
        b"210",
        b"%%EOF",
    ]
    return b"\n".join(lines) + b"\n"

def ffaudio(ext: str) -> bytes | None:
    out = f"/tmp/fc_{RUN}{ext}"
    seed = str(int(time.time() * 1000) % 10000)
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"sine=frequency=440:sample_rate=44100",
        "-t", "0.15", out,
    ]
    res = subprocess.run(cmd, capture_output=True, timeout=20)
    if res.returncode != 0:
        print(f"    ffmpeg err ({ext}): {res.stderr[-60:].decode(errors='replace')}")
        return None
    data = open(out, "rb").read()
    os.unlink(out)
    return data + _salt()          # extra bytes ensure unique hash

def ffvideo(ext: str, vcodec: str, acodec: str) -> bytes | None:
    out = f"/tmp/fc_{RUN}{ext}"
    # Random hex color per run
    col = "0x" + RUN[:6]
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c={col}:s=8x8:r=5",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
        "-t", "0.2", "-c:v", vcodec, "-c:a", acodec, out,
    ]
    res = subprocess.run(cmd, capture_output=True, timeout=30)
    if res.returncode != 0:
        print(f"    ffmpeg err ({ext}): {res.stderr[-60:].decode(errors='replace')}")
        return None
    data = open(out, "rb").read()
    os.unlink(out)
    return data + _salt()

# ── Submit helper ─────────────────────────────────────────────────────────

def submit(fname: str, data: bytes):
    return client.post(
        f"{BASE}/api/v1/investigate",
        headers=HDRS,
        files={"file": (fname, io.BytesIO(data))},
        data={"case_id": f"CASE-{RUN}", "investigator_id": "tester"},
    )

# ── Build test matrix ─────────────────────────────────────────────────────

print(f"\nGenerating unique test files for run {RUN}...")

ACCEPT = [
    # Images — PIL-generated, pass backend PIL.verify()
    ("img_png.png",   pil_img("PNG"),                       ["Agent1", "Agent3", "Agent5"]),
    ("img_jpg.jpg",   pil_img("JPEG"),                      ["Agent1", "Agent3", "Agent5"]),
    ("img_webp.webp", pil_img("WEBP"),                      ["Agent1", "Agent3", "Agent5"]),
    ("img_gif.gif",   pil_img("GIF"),                       ["Agent1", "Agent3", "Agent5"]),
    ("img_bmp.bmp",   pil_img("BMP"),                       ["Agent1", "Agent3", "Agent5"]),
    ("img_tiff.tiff", pil_img("TIFF"),                      ["Agent1", "Agent3", "Agent5"]),
    # Audio — WAV hand-crafted; others via ffmpeg
    ("aud_wav.wav",   hand_wav(),                            ["Agent2", "Agent5"]),
    ("aud_mp3.mp3",   ffaudio(".mp3"),                       ["Agent2", "Agent5"]),
    ("aud_ogg.ogg",   ffaudio(".ogg"),                       ["Agent2", "Agent5"]),
    ("aud_m4a.m4a",   ffaudio(".m4a"),                       ["Agent2", "Agent5"]),
    # Video
    ("vid_mp4.mp4",   ffvideo(".mp4",  "libx264", "aac"),   ["Agent4", "Agent5"]),
    ("vid_webm.webm", ffvideo(".webm", "libvpx",  "libvorbis"), ["Agent4", "Agent5"]),
    # Document
    ("doc_pdf.pdf",   hand_pdf(),                            ["Agent5"]),
]

REJECT = [
    ("spoof.txt",   pil_img("PNG") + _salt(), 400, "PNG content with .txt extension"),
    ("bad.exe",     b"MZ\x90\x00" + _salt(),  400, "PE executable, unsupported type"),
    ("noext",       pil_img("PNG") + _salt(),  400, "no file extension"),
    ("wrong.mp4",   hand_wav() + _salt(),      400, "WAV content in .mp4 extension"),
]

# ── Run ACCEPT tests ──────────────────────────────────────────────────────

P = F = SK = 0

print()
print("=" * 72)
print("ACCEPT TESTS — expect HTTP 200 with correct agent routing")
print("=" * 72)

for fname, data, expected_agents in ACCEPT:
    if data is None:
        print(f"  [SKIP] {fname:<24} — ffmpeg generation failed")
        SK += 1
        continue

    r2  = submit(fname, data)
    bd  = {}
    try:
        bd = r2.json()
    except Exception:
        pass

    got_agents = bd.get("applicable_agents", [])
    agents_ok  = all(a in got_agents for a in expected_agents)
    status_ok  = r2.status_code == 200
    passed     = status_ok and agents_ok

    sym = "PASS" if passed else "FAIL"
    if passed:
        P += 1
    else:
        F += 1

    extra = [a for a in got_agents if a not in expected_agents]
    sz    = f"{max(1, len(data) // 1024)}KB"
    note  = f" +extra={extra}" if extra else ""
    print(f"  [{sym}] {fname:<24} HTTP {r2.status_code}  sz={sz:<7} agents={got_agents}{note}")

    if not passed:
        detail = bd.get("detail", bd.get("message", ""))
        print(f"         expected_subset={expected_agents}")
        print(f"         detail: {str(detail)[:90]}")

# ── Run REJECT tests ──────────────────────────────────────────────────────

print()
print("=" * 72)
print("REJECT TESTS — expect HTTP 400")
print("=" * 72)

for fname, data, exp_status, reason in REJECT:
    r2 = submit(fname, data)
    bd  = {}
    try:
        bd = r2.json()
    except Exception:
        pass

    passed = r2.status_code == exp_status
    sym    = "PASS" if passed else "FAIL"
    if passed:
        P += 1
    else:
        F += 1

    detail = bd.get("detail", bd.get("message", ""))
    print(f"  [{sym}] REJECT {fname:<22} HTTP {r2.status_code}  ({reason})")
    print(f"         detail: {str(detail)[:90]}")

# ── Summary ───────────────────────────────────────────────────────────────

total   = P + F
verdict = "ALL PASS" if F == 0 else f"{F} FAILED"

print()
print("=" * 72)
print(f"RESULT: {P}/{total} passed  {SK} skipped  >>> {verdict}")
print("=" * 72)
sys.exit(0 if F == 0 else 1)

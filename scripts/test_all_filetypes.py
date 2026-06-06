#!/usr/bin/env python3
"""
Live file-type acceptance + rejection test.
Runs against the Forensic Council backend at http://localhost:8000.
Uses PIL for valid images, ffmpeg for audio/video, hand-crafted PDF/WAV.
"""
import io, json, os, struct, subprocess, sys, tempfile
import httpx
from PIL import Image as PILImage

BASE = "http://localhost:8000"
PW   = os.environ.get("BOOTSTRAP_INVESTIGATOR_PASSWORD", "")

# ── Auth (double-submit CSRF: cookie must == X-CSRF-Token header) ─────────
client = httpx.Client(timeout=60.0)
r = client.post(
    f"{BASE}/api/v1/auth/login",
    data={"username": "investigator", "password": PW},
    headers={"Content-Type": "application/x-www-form-urlencoded"},
)
assert r.status_code == 200, f"Login failed {r.status_code}: {r.text[:200]}"
body  = r.json()
TOKEN = body["access_token"]
CSRF  = client.cookies.get("csrf_token")   # cookie-jar value for double-submit
HDRS  = {"Authorization": f"Bearer {TOKEN}", "X-CSRF-Token": CSRF}
print(f"Auth OK  role={body['role']}  csrf={CSRF[:16]}...")

# ── File factories ────────────────────────────────────────────────────────

def pil_image(fmt: str) -> bytes:
    """Generate a minimal valid image via Pillow."""
    img = PILImage.new("RGB", (4, 4), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()

def hand_wav() -> bytes:
    """Minimal 44-byte WAV (PCM mono 8 kHz 8-bit, 2 samples silence)."""
    d   = b"\x00\x00"
    fmt = struct.pack("<HHIIHH", 1, 1, 8000, 8000, 1, 8)
    return (
        b"RIFF" + (36 + len(d)).to_bytes(4, "little") + b"WAVE"
        + b"fmt " + len(fmt).to_bytes(4, "little") + fmt
        + b"data" + len(d).to_bytes(4, "little") + d
    )

def hand_pdf() -> bytes:
    """Minimal valid single-page PDF."""
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f\r\n0000000009 00000 n\r\n"
        b"0000000058 00000 n\r\n0000000115 00000 n\r\n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n188\n%%EOF\n"
    )

def ffmpeg_audio(ext: str) -> bytes | None:
    """Generate a 0.1s silent audio file via ffmpeg."""
    out = f"/tmp/fc_test{ext}"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
        "-t", "0.1", out,
    ]
    r2 = subprocess.run(cmd, capture_output=True, timeout=20)
    if r2.returncode != 0:
        print(f"  ffmpeg FAILED for {ext}: {r2.stderr[-80:].decode(errors='replace')}")
        return None
    data = open(out, "rb").read()
    os.unlink(out)
    return data

def ffmpeg_video(ext: str, vcodec: str = "libx264", acodec: str = "aac") -> bytes | None:
    """Generate a 0.1s silent 4×4 video via ffmpeg."""
    out = f"/tmp/fc_test{ext}"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=red:s=4x4:r=1",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
        "-t", "0.1",
        "-c:v", vcodec, "-c:a", acodec,
        out,
    ]
    r2 = subprocess.run(cmd, capture_output=True, timeout=30)
    if r2.returncode != 0:
        print(f"  ffmpeg FAILED for {ext}: {r2.stderr[-80:].decode(errors='replace')}")
        return None
    data = open(out, "rb").read()
    os.unlink(out)
    return data

# ── Submit helper ─────────────────────────────────────────────────────────

def submit(fname: str, data: bytes):
    return client.post(
        f"{BASE}/api/v1/investigate",
        headers=HDRS,
        files={"file": (fname, io.BytesIO(data))},
        data={"case_id": "CASE-TEST-001", "investigator_id": "tester"},
    )

# ── Build test matrix ─────────────────────────────────────────────────────

print("\nGenerating test files...")
mp3_data  = ffmpeg_audio(".mp3")
ogg_data  = ffmpeg_audio(".ogg")
m4a_data  = ffmpeg_audio(".m4a")
mp4_data  = ffmpeg_video(".mp4", "libx264", "aac")
webm_data = ffmpeg_video(".webm", "libvpx", "libvorbis")

ACCEPT = [
    # Images — PIL-generated (go through PIL verify on backend)
    ("test.png",  pil_image("PNG"),  ["Agent1", "Agent3", "Agent5"]),
    ("test.jpg",  pil_image("JPEG"), ["Agent1", "Agent3", "Agent5"]),
    ("test.webp", pil_image("WEBP"), ["Agent1", "Agent3", "Agent5"]),
    ("test.gif",  pil_image("GIF"),  ["Agent1", "Agent3", "Agent5"]),
    ("test.bmp",  pil_image("BMP"),  ["Agent1", "Agent3", "Agent5"]),
    ("test.tiff", pil_image("TIFF"), ["Agent1", "Agent3", "Agent5"]),
    # Audio — ffmpeg-generated (go through ffprobe on backend)
    ("test.wav",  hand_wav(),        ["Agent2", "Agent5"]),
    ("test.mp3",  mp3_data,          ["Agent2", "Agent5"]),
    ("test.ogg",  ogg_data,          ["Agent2", "Agent5"]),
    ("test.m4a",  m4a_data,          ["Agent2", "Agent5"]),
    # Video
    ("test.mp4",  mp4_data,          ["Agent4", "Agent5"]),
    ("test.webm", webm_data,         ["Agent4", "Agent5"]),
    # Documents
    ("test.pdf",  hand_pdf(),        ["Agent5"]),
]

REJECT = [
    ("spoof.txt",  pil_image("PNG"),     400, "PNG content with .txt extension"),
    ("bad.exe",    b"MZ\x90\x00" * 50,  400, "PE executable, unsupported"),
    ("noext",      pil_image("PNG"),     400, "no file extension"),
]

# ── Run ACCEPT tests ──────────────────────────────────────────────────────

P = F = 0
skipped = 0

print("\n" + "=" * 68)
print("ACCEPT TESTS — expect HTTP 200 + correct agent routing")
print("=" * 68)

for fname, data, expected_agents in ACCEPT:
    if data is None:
        print(f"  [SKIP] {fname:<16} — ffmpeg generation failed")
        skipped += 1
        continue

    r2 = submit(fname, data)
    bd: dict = {}
    try:
        bd = r2.json()
    except Exception:
        pass

    got_agents  = bd.get("applicable_agents", [])
    agents_ok   = all(a in got_agents for a in expected_agents)
    status_ok   = r2.status_code == 200
    passed      = status_ok and agents_ok

    sym = "PASS" if passed else "FAIL"
    if passed:
        P += 1
    else:
        F += 1

    extra = [a for a in got_agents if a not in expected_agents]
    size  = f"{len(data)//1024}KB"
    line  = f"  [{sym}] {fname:<16} HTTP {r2.status_code}  sz={size:<7}  agents={got_agents}"
    if extra:
        line += f"  +extra={extra}"
    print(line)
    if not passed:
        detail = bd.get("detail", bd.get("message", ""))
        print(f"         expected_subset={expected_agents}")
        print(f"         detail: {str(detail)[:90]}")

# ── Run REJECT tests ──────────────────────────────────────────────────────

print("\n" + "=" * 68)
print("REJECT TESTS — expect HTTP 400")
print("=" * 68)

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
    print(f"  [{sym}] REJECT {fname:<20} HTTP {r2.status_code}  ({reason})")
    print(f"         detail: {str(detail)[:90]}")

# ── Summary ───────────────────────────────────────────────────────────────

total   = P + F
verdict = "ALL PASS" if F == 0 else f"{F} FAILED"
print("\n" + "=" * 68)
print(f"RESULT: {P}/{total} passed  {skipped} skipped  >>> {verdict}")
print("=" * 68)
sys.exit(0 if F == 0 else 1)

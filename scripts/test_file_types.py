#!/usr/bin/env python3
"""Live file-type acceptance test against the running Forensic Council backend."""
import io, json, os, struct, zlib, sys
import httpx

BASE = "http://localhost:8000"
PW   = os.environ.get("BOOTSTRAP_INVESTIGATOR_PASSWORD", "")

# ── Auth ──────────────────────────────────────────────────────────────────
r = httpx.post(
    f"{BASE}/api/v1/auth/login",
    data={"username": "investigator", "password": PW},
    headers={"Content-Type": "application/x-www-form-urlencoded"},
)
assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
TOKEN = r.json()["access_token"]
CSRF  = r.cookies.get("csrf_token", "")
HDRS  = {"Authorization": f"Bearer {TOKEN}", "X-CSRF-Token": CSRF}
print(f"Auth OK  role={r.json()['role']}")

# ── File factories ─────────────────────────────────────────────────────────

def _chunk(name: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(name + data).to_bytes(4, "big")
    return len(data).to_bytes(4, "big") + name + data + crc

def make_png() -> bytes:
    sig  = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw  = b"\x00\xff\x00\x00"          # filter byte + 1 RGB pixel
    idat = _chunk(b"IDAT", zlib.compress(raw))
    iend = _chunk(b"IEND", b"")
    return sig + ihdr + idat + iend

def make_jpeg() -> bytes:
    return (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xdb\x00C\x00" + bytes([8,6,6,7,6,5,8,7,7,7,9,9,8,10,12,20,13,12,11])
        + bytes([11,12,25,18,19,15,20,29,26,31,30,29,26,28,28,36,44,36,28,27,41,60])
        + bytes([41,28,28,51,68,51,47,57,1,2,2,2,2,2,6,7,7,6])
        + b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
        b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00"
        b"\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b"
        b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xf5\x0f\xff\xd9"
    )

def make_webp() -> bytes:
    # Lossless WebP 1×1 white pixel
    vp8l = bytes([0x2f,0x00,0x00,0x00,0x00,0xff,0xff,0x00,0xfe,0xef,0x01,0x00,0x00])
    chunk = b"VP8L" + len(vp8l).to_bytes(4, "little") + vp8l
    body  = b"WEBP" + chunk
    return b"RIFF" + len(body).to_bytes(4, "little") + body

def make_gif() -> bytes:
    return (
        b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00"
        b"!\xf9\x04\x00\x00\x00\x00\x00"
        b",\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
    )

def make_bmp() -> bytes:
    # 1×1 24bpp BMP
    return (
        b"BM8\x00\x00\x00\x00\x00\x00\x006\x00\x00\x00"
        b"(\x00\x00\x00\x01\x00\x00\x00\x01\x00\x00\x00\x01\x00\x18\x00"
        b"\x00\x00\x00\x00\x02\x00\x00\x00\x13\x0b\x00\x00\x13\x0b\x00\x00"
        b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\x00\x00"
    )

def make_tiff() -> bytes:
    # LE 1×1 RGB TIFF — 8 bits per sample, 3 samples
    bps_offset = 8 + 2 + 11*12 + 4   # after IFD
    data_offset = bps_offset + 6      # after BitsPerSample values
    ifd = struct.pack("<H", 11)       # entry count
    def e(tag, typ, cnt, val):        # IFD entry helper
        return struct.pack("<HHII", tag, typ, cnt, val)
    ifd += (
        e(256, 3, 1, 1)              # ImageWidth = 1
        + e(257, 3, 1, 1)            # ImageLength = 1
        + e(258, 3, 3, bps_offset)   # BitsPerSample → offset
        + e(259, 3, 1, 1)            # Compression = none
        + e(262, 3, 1, 2)            # PhotometricInterp = RGB
        + e(273, 4, 1, data_offset)  # StripOffsets
        + e(277, 3, 1, 3)            # SamplesPerPixel = 3
        + e(278, 3, 1, 1)            # RowsPerStrip = 1
        + e(279, 4, 1, 3)            # StripByteCounts = 3
        + e(284, 3, 1, 1)            # PlanarConfig = chunky
        + e(339, 3, 1, 1)            # SampleFormat = uint
    )
    ifd += struct.pack("<I", 0)       # next IFD = none
    bps_values = struct.pack("<HHH", 8, 8, 8)
    pixel = b"\xff\x00\x00"          # red pixel
    hdr = struct.pack("<HHI", 0x4949, 42, 8)
    return hdr + ifd + bps_values + pixel

def make_wav() -> bytes:
    data = b"\x00\x00"
    fmt  = struct.pack("<HHIIHH", 1, 1, 8000, 8000, 1, 8)
    return (
        b"RIFF" + (36 + len(data)).to_bytes(4, "little") + b"WAVE"
        + b"fmt " + len(fmt).to_bytes(4, "little") + fmt
        + b"data" + len(data).to_bytes(4, "little") + data
    )

def make_mp3() -> bytes:
    # MPEG-1 Layer 3 frame header: sync(11) + MPEG1(11) + Layer3(01) + 128k(1001) + 44.1k(00) + …
    header = bytes([0xFF, 0xFB, 0x90, 0x00])
    return header + bytes(417)   # fill rest of frame with silence

def make_ogg() -> bytes:
    # OGG capture header with vorbis magic — enough for libmagic
    return (
        b"OggS\x00\x02" + b"\x00" * 8   # header + granule
        + b"\x00\x00\x00\x00"            # serial
        + b"\x00\x00\x00\x00"            # page seq
        + b"\x00\x00\x00\x00"            # crc (uncalculated — ffprobe still IDs it)
        + b"\x01\x1e"                    # 1 segment, 30 bytes
        + b"\x01vorbis"                  # vorbis id header
        + b"\x00\x00\x00\x00"            # version
        + b"\x01"                        # channels=1
        + b"\x80\xbb\x00\x00"            # sample rate=48000
        + b"\x00\x00\x00\x00\x00\x00\x00\x00\x01"
    )

def make_mp4() -> bytes:
    ftyp_body = b"ftypisom\x00\x00\x02\x00isomiso2mp41"
    ftyp_box  = len(ftyp_body + b"ftyp").to_bytes(4, "big") + b"ftyp" + ftyp_body
    mdat_box  = (9).to_bytes(4, "big") + b"mdat\x00"
    return ftyp_box + mdat_box

def make_webm() -> bytes:
    # EBML header with DocType=webm
    return (
        b"\x1a\x45\xdf\xa3\x9f"
        b"\x42\x86\x81\x01"
        b"\x42\xf7\x81\x01"
        b"\x42\xf2\x81\x04"
        b"\x42\xf3\x81\x08"
        b"\x42\x82\x84webm"
        b"\x42\x87\x81\x04"
        b"\x42\x85\x81\x02"
    )

def make_pdf() -> bytes:
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f\r\n0000000009 00000 n\r\n"
        b"0000000058 00000 n\r\n0000000115 00000 n\r\n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n188\n%%EOF\n"
    )

# ── Submit helper ──────────────────────────────────────────────────────────
def submit(fname, data):
    return httpx.post(
        f"{BASE}/api/v1/investigate",
        headers=HDRS,
        files={"file": (fname, io.BytesIO(data))},
        data={"case_id": "CASE-TEST-001", "investigator_id": "tester"},
        timeout=30.0,
    )

# ── Test table ─────────────────────────────────────────────────────────────
ACCEPT = [
    ("test.png",  make_png(),  ["Agent1","Agent3","Agent5"]),
    ("test.jpg",  make_jpeg(), ["Agent1","Agent3","Agent5"]),
    ("test.webp", make_webp(), ["Agent1","Agent3","Agent5"]),
    ("test.gif",  make_gif(),  ["Agent1","Agent3","Agent5"]),
    ("test.bmp",  make_bmp(),  ["Agent1","Agent3","Agent5"]),
    ("test.tiff", make_tiff(), ["Agent1","Agent3","Agent5"]),
    ("test.wav",  make_wav(),  ["Agent2","Agent5"]),
    ("test.mp3",  make_mp3(),  ["Agent2","Agent5"]),
    ("test.ogg",  make_ogg(),  ["Agent2","Agent5"]),
    ("test.mp4",  make_mp4(),  ["Agent4","Agent5"]),
    ("test.webm", make_webm(), ["Agent4","Agent5"]),
    ("test.pdf",  make_pdf(),  ["Agent5"]),
]
REJECT = [
    ("spoof.txt",  make_png(),       "MIME/ext mismatch"),
    ("bad.exe",    b"MZ\x90\x00" * 100, "unsupported exe"),
]

PASS = FAIL = 0

print()
print("=" * 68)
print("ACCEPT TESTS — all should return 200 with correct agents")
print("=" * 68)
for fname, data, exp_agents in ACCEPT:
    r  = submit(fname, data)
    bd = {}
    try: bd = r.json()
    except: pass
    got = bd.get("applicable_agents", [])
    ok  = r.status_code == 200 and all(a in got for a in exp_agents)
    sym = "PASS" if ok else "FAIL"
    if ok: PASS += 1
    else:  FAIL += 1
    ext_agents = [a for a in got if a not in exp_agents]
    note = f"+{ext_agents}" if ext_agents else ""
    print(f"  [{sym}] {fname:<14} HTTP {r.status_code}  agents={got}{note}")
    if not ok:
        print(f"         expected {exp_agents}")
        print(f"         detail: {str(bd.get('detail',''))[:100]}")

print()
print("=" * 68)
print("REJECT TESTS — all should return 400")
print("=" * 68)
for fname, data, reason in REJECT:
    r  = submit(fname, data)
    bd = {}
    try: bd = r.json()
    except: pass
    ok  = r.status_code == 400
    sym = "PASS" if ok else "FAIL"
    if ok: PASS += 1
    else:  FAIL += 1
    detail = str(bd.get("detail", ""))[:90]
    print(f"  [{sym}] {fname:<18} HTTP {r.status_code}  ({reason})")
    print(f"         detail: {detail}")

print()
print("=" * 68)
print(f"TOTAL: {PASS} passed  {FAIL} failed")
print("=" * 68)
sys.exit(0 if FAIL == 0 else 1)

"""
Smoke test upload script — runs inside the API container.
Called by phase_guard.sh via: docker exec forensic_api python3 /app/scripts/smoke_upload.py
"""
import struct, zlib, json, os, sys


def make_png() -> bytes:
    def chunk(name: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + name + data
        return c + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw = b"\x00\xff\xff\xff"
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


password = os.environ.get("LOGIN_PASS", "")
if not password:
    print(json.dumps({"error": "LOGIN_PASS env var not set"}))
    sys.exit(1)

png_bytes = make_png()

try:
    import httpx

    with httpx.Client(base_url="http://localhost:8000", timeout=20) as c:
        c.get("/api/v1/health")
        csrf = c.cookies.get("csrf_token", "")

        r = c.post(
            "/api/v1/auth/login",
            data={"username": "admin", "password": password},
            headers={"X-CSRF-Token": csrf},
        )
        if r.status_code != 200:
            print(json.dumps({"error": f"Login failed: {r.status_code} {r.text[:100]}"}))
            sys.exit(1)
        csrf = r.json().get("csrf_token", csrf)

        r = c.post(
            "/api/v1/investigate",
            files={"file": ("smoke.png", png_bytes, "image/png")},
            data={"case_id": "CASE-PHASE-GUARD-SMOKE", "investigator_id": "smoke-guard"},
            headers={"X-CSRF-Token": csrf},
        )
        print(r.text)

except Exception as e:
    print(json.dumps({"error": str(e)}))
    sys.exit(1)

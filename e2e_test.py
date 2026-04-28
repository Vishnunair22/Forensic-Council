#!/usr/bin/env python3
"""
End-to-end test: evidence upload -> initial analysis -> deep analysis -> report.
"""

import json
import io
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse

BASE = "http://localhost:8000"
ADMIN_USER = "admin"
ADMIN_PASS = os.environ.get("ADMIN_PASS")
if not ADMIN_PASS:
    sys.exit("Set ADMIN_PASS env var before running e2e_test.py")

PASS_S = "\033[92m[PASS]\033[0m"
FAIL_S = "\033[91m[FAIL]\033[0m"
INFO_S = "\033[94m[INFO]\033[0m"
WARN_S = "\033[93m[WARN]\033[0m"


def step(n, msg):
    print(f"\n\033[1m-- Step {n}: {msg}\033[0m")


def ok(msg):
    print(f"  {PASS_S} {msg}")


def fail(msg):
    print(f"  {FAIL_S} {msg}")
    sys.exit(1)


def info(msg):
    print(f"  {INFO_S} {msg}")


def warn(msg):
    print(f"  {WARN_S} {msg}")


# ─── HTTP helpers ─────────────────────────────────────────────────────────────

csrf_token = None
jwt_token = None


def _make_cookie_header():
    if csrf_token:
        return f"csrf_token={csrf_token}"
    return ""


def _base_headers(extra=None):
    h = {}
    if jwt_token:
        h["Authorization"] = f"Bearer {jwt_token}"
    if csrf_token:
        h["Cookie"] = _make_cookie_header()
        h["X-CSRF-Token"] = csrf_token
    if extra:
        h.update(extra)
    return h


def do_get(path):
    url = BASE + path
    req = urllib.request.Request(url, headers=_base_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except:
            return e.code, {"error": str(e)}
    except Exception as e:
        return 0, {"error": str(e)}


def do_post_form(path, data):
    url = BASE + path
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            **_base_headers(),
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except:
            return e.code, {"error": str(e)}


def do_post_multipart(path, fields, file_name, file_data, file_ct):
    url = BASE + path
    boundary = b"----FormBoundary7MA4YWxkTrZu0gW"
    parts = []
    for k, v in fields.items():
        parts.append(b"--" + boundary + b"\r\n")
        parts.append(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode())
        parts.append(v.encode() + b"\r\n")
    parts.append(b"--" + boundary + b"\r\n")
    parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'.encode()
    )
    parts.append(f"Content-Type: {file_ct}\r\n\r\n".encode())
    parts.append(file_data + b"\r\n")
    parts.append(b"--" + boundary + b"--\r\n")
    body = b"".join(parts)

    headers = {
        **_base_headers(),
        "Content-Type": f"multipart/form-data; boundary={boundary.decode()}",
        "Content-Length": str(len(body)),
    }
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except:
            return e.code, {"raw": e.read().decode(errors="replace")}


# ─── Test Steps ───────────────────────────────────────────────────────────────

# Step 1: Health
step(1, "Health check")
code, body = do_get("/health")
if code == 200 and body.get("status") == "healthy":
    ok(f"API healthy: {body}")
else:
    fail(f"API not healthy (HTTP {code}): {body}")

# Step 2: Login — also captures CSRF token from response body
step(2, "Authentication (admin login)")
# Login is CSRF-exempt, no token needed for this request
url = BASE + "/api/v1/auth/login"
body_data = urllib.parse.urlencode(
    {"username": ADMIN_USER, "password": ADMIN_PASS}
).encode()
req = urllib.request.Request(
    url,
    data=body_data,
    method="POST",
    headers={"Content-Type": "application/x-www-form-urlencoded"},
)
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        login_code = r.status
        login_body = json.loads(r.read())
except urllib.error.HTTPError as e:
    login_code = e.code
    login_body = json.loads(e.read())

if login_code == 200 and "access_token" in login_body:
    jwt_token = login_body["access_token"]
    csrf_token = login_body.get("csrf_token")
    ok(
        f"Logged in. Token type: {login_body.get('token_type')}, Role: {login_body.get('role')}"
    )
    if csrf_token:
        ok("CSRF token obtained from login response")
    else:
        warn("No csrf_token in login response — will try fetching via GET")
else:
    fail(f"Login failed (HTTP {login_code}): {login_body}")

# If no CSRF in login body, do a GET to obtain the cookie
if not csrf_token:
    code, body = do_get("/api/v1/health")
    warn("Attempting CSRF token from GET /api/v1/health (should be set via cookie)")
    # In this case we'd need actual cookie jar — but login body should always have it

# Step 3: /me
step(3, "Verify identity (/auth/me)")
code, body = do_get("/api/v1/auth/me")
if code == 200 and "username" in body:
    ok(f"Authenticated as: {body['username']} (role={body.get('role')})")
else:
    fail(f"/me failed (HTTP {code}): {body}")

# Step 4: Create test evidence image
step(4, "Create synthetic test evidence (image)")
try:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (800, 600), color=(100, 149, 237))
    draw = ImageDraw.Draw(img)
    draw.rectangle([60, 60, 380, 300], fill=(220, 50, 50))
    draw.ellipse([420, 160, 730, 460], fill=(50, 205, 50))
    draw.rectangle([100, 400, 700, 550], fill=(255, 215, 0))
    draw.text((200, 520), "FORENSIC TEST EVIDENCE", fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    image_bytes = buf.getvalue()
    ok(f"Synthetic JPEG created: {len(image_bytes):,} bytes (800x600)")
except ImportError:
    # Standard test JPEG from bytes
    import base64

    # A real 10x10 red JPEG
    TINY_JPEG_B64 = (
        "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8U"
        "HRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgN"
        "DRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy"
        "MjL/wAARCAAKAAoDASIAAhEBAxEB/8QAFgABAQEAAAAAAAAAAAAAAAAABgUE/8QAIhAAAgIB"
        "BAMBAAAAAAAAAAAAAQIDBAUREiExQf/EABUBAQEAAAAAAAAAAAAAAAAAAAIE/8QAGhEAAgID"
        "AAAAAAAAAAAAAAAAARECEiEx/9oADAMBAAIRAxEAPwCdo3RWvMsOPatFHFXOY2SSNdy5J3+"
        "EVJW4KXJRS5JyT9nLly5eNbbNq1as2rVq0EbVv//Z"
    )
    image_bytes = base64.b64decode(TINY_JPEG_B64)
    warn(f"PIL not available, using embedded test JPEG ({len(image_bytes)} bytes)")

# Step 5: Upload & start investigation
step(5, "Upload evidence & start investigation")
case_id = f"E2E-TEST-{int(time.time())}"
investigator_id = "e2e-test-runner"

info(f"  Sending to: POST {BASE}/api/v1/investigate")
info(f"  case_id={case_id}  investigator_id={investigator_id}")
info(f"  CSRF token present: {bool(csrf_token)}")

code, body = do_post_multipart(
    path="/api/v1/investigate",
    fields={"case_id": case_id, "investigator_id": investigator_id},
    file_name="test_evidence.jpg",
    file_data=image_bytes,
    file_ct="image/jpeg",
)

if code == 200 and "session_id" in body:
    session_id = body["session_id"]
    ok("Investigation started!")
    info(f"  session_id   : {session_id}")
    info(f"  case_id      : {body.get('case_id')}")
    info(f"  status       : {body.get('status')}")
    info(f"  file_hash    : {body.get('file_hash', 'n/a')}")
    info(f"  media_type   : {body.get('media_type', 'n/a')}")
    info(f"  Full response: {json.dumps(body)[:500]}")
else:
    info(f"  Full error response: {json.dumps(body, indent=2)}")
    fail(f"Investigation start failed (HTTP {code})")

# Step 6: Poll progress
step(6, "Polling progress (initial + deep analysis phases)")
POLL_INTERVAL = 10
MAX_WAIT = 600
elapsed = 0
last_phase = ""
last_pct = -1
final_status = "unknown"

while elapsed < MAX_WAIT:
    time.sleep(POLL_INTERVAL)
    elapsed += POLL_INTERVAL
    code, progress = do_get(f"/api/v1/sessions/{session_id}/progress")
    if code != 200:
        warn(f"  [{elapsed:>4}s] Progress poll failed (HTTP {code}): {progress}")
        continue

    status = progress.get("status", "unknown")
    phase = str(progress.get("phase", progress.get("current_phase", "")))
    pct = progress.get("progress_pct", progress.get("progress", 0)) or 0
    msg = str(progress.get("message", progress.get("status_message", "")))

    if phase != last_phase or abs(pct - last_pct) >= 5:
        print(
            f"  [{elapsed:>4}s] status={status:<18} phase={phase:<32} {pct:>3}%  {msg[:65]}"
        )
        last_phase = phase
        last_pct = pct

    final_status = status
    if status in ("completed", "complete", "done", "finished"):
        ok(f"Investigation COMPLETED at {elapsed}s!")
        break
    elif status in ("failed", "error"):
        print(f"\n  Full progress dump:\n{json.dumps(progress, indent=2)}")
        fail(f"Investigation FAILED at {elapsed}s")
    elif status in ("hitl_required", "awaiting_human", "needs_review", "paused"):
        warn(f"HITL/pause at {elapsed}s — awaiting human decision.")
        info(f"Progress: {json.dumps(progress, indent=2)[:600]}")
        break
else:
    warn(f"Timed out after {MAX_WAIT}s (final status={final_status})")
    _, prog2 = do_get(f"/api/v1/sessions/{session_id}/progress")
    info(f"Final progress state: {json.dumps(prog2, indent=2)[:800]}")

# Step 7: Session details
step(7, "Retrieve full session details")
code, body = do_get(f"/api/v1/sessions/{session_id}")
if code == 200:
    agents = body.get("agent_results", body.get("agents", {}))
    agent_count = len(agents) if isinstance(agents, (dict, list)) else "n/a"
    ok(f"Session: status={body.get('status')}  agents_run={agent_count}")
    info(f"  media_type   : {body.get('media_type', 'n/a')}")
    info(f"  created_at   : {body.get('created_at')}")
    info(f"  updated_at   : {body.get('updated_at')}")
    info(f"  keys         : {list(body.keys())}")
    if body.get("error"):
        warn(f"  ERROR field  : {body.get('error')}")
    if isinstance(agents, dict):
        for agent_id, result in list(agents.items())[:3]:
            status_a = result.get("status", "?") if isinstance(result, dict) else "?"
            info(f"    agent {agent_id}: status={status_a}")
else:
    warn(f"Session retrieval (HTTP {code}): {body}")

# Step 8: Arbiter status
step(8, "Check arbiter deliberation status")
code, body = do_get(f"/api/v1/sessions/{session_id}/arbiter-status")
if code == 200:
    ok("Arbiter status retrieved")
    info(f"  {json.dumps(body, indent=2)[:600]}")
else:
    warn(f"Arbiter status (HTTP {code}): {json.dumps(body)[:300]}")

# Step 9: Report
step(9, "Fetch final forensic report")
code, body = do_get(f"/api/v1/sessions/{session_id}/report")
if code == 200:
    ok("Report generated!")
    verdict = body.get(
        "verdict", body.get("overall_verdict", body.get("authenticity_verdict", "n/a"))
    )
    confidence = body.get(
        "confidence",
        body.get("overall_confidence", body.get("confidence_score", "n/a")),
    )
    info(f"  verdict      : {verdict}")
    info(f"  confidence   : {confidence}")
    summary = body.get("executive_summary", body.get("summary", ""))
    if summary:
        info(f"  summary      : {str(summary)[:400]}")
    info(f"  report keys  : {list(body.keys())}")
elif code == 404:
    warn("Report 404 — analysis may still be in progress or session didn't complete")
    info(f"  Response: {json.dumps(body)[:300]}")
else:
    warn(f"Report (HTTP {code}): {json.dumps(body)[:400]}")

# Step 10: Sessions list
step(10, "List all sessions (admin overview)")
code, body = do_get("/api/v1/sessions")
if code == 200:
    sessions = (
        body if isinstance(body, list) else body.get("sessions", body.get("items", []))
    )
    ok(f"Sessions visible: {len(sessions)}")
    for s in (sessions or [])[:5]:
        sid = str(s.get("session_id", "?"))[:28]
        info(f"  {sid}  status={s.get('status', '?'):<18} case={s.get('case_id', '?')}")
else:
    warn(f"Sessions list (HTTP {code}): {body}")

print("\n\033[1m=============================================\033[0m")
print("\033[1m  END-TO-END TEST COMPLETE\033[0m")
print("\033[1m=============================================\033[0m\n")

import json
import mimetypes
import os
import sys
import time
import uuid
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


BASE_URL = os.environ.get("FC_BASE_URL", "http://localhost:8000")
USERNAME = os.environ.get("FC_USERNAME", "investigator")
PASSWORD = os.environ["FC_PASSWORD"]
ROOT = Path(os.environ.get("FC_FIXTURE_DIR", r"D:\Forensic Council\.tmp_e2e"))


def request_json(opener, method, path, body=None, headers=None, timeout=60):
    data = None
    final_headers = dict(headers or {})
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode("utf-8")
            final_headers["Content-Type"] = "application/json"
        else:
            data = body
    req = Request(f"{BASE_URL}{path}", data=data, headers=final_headers, method=method)
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except Exception as exc:
        if hasattr(exc, "read"):
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw)
            except Exception:
                detail = raw
            return getattr(exc, "code", 0), detail
        raise


def multipart_body(fields, file_field, file_path, content_type):
    boundary = f"----forensic-council-{uuid.uuid4().hex}"
    chunks = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(str(value).encode())
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}\r\n".encode())
    chunks.append(
        (
            f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode()
    )
    chunks.append(file_path.read_bytes())
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def login():
    cookies = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookies))
    request_json(opener, "GET", "/health", timeout=30)
    form = urlencode({"username": USERNAME, "password": PASSWORD}).encode()
    csrf_token = next((cookie.value for cookie in cookies if cookie.name == "csrf_token"), "")
    status, data = request_json(
        opener,
        "POST",
        "/api/v1/auth/login",
        form,
        {"Content-Type": "application/x-www-form-urlencoded", "X-CSRF-Token": csrf_token},
        timeout=30,
    )
    if status != 200:
        raise RuntimeError(f"login failed: {status} {data}")
    token = data["access_token"]
    opener.addheaders = [("Authorization", f"Bearer {token}")]
    return opener


def csrf_header(opener):
    request_json(opener, "GET", "/health", timeout=30)
    for handler in opener.handlers:
        cookiejar = getattr(handler, "cookiejar", None)
        if cookiejar:
            token = next((cookie.value for cookie in cookiejar if cookie.name == "csrf_token"), "")
            return {"X-CSRF-Token": token} if token else {}
    return {}


def start_investigation(opener, file_path, case_id):
    mime = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    body, content_type = multipart_body(
        {"case_id": case_id, "investigator_id": "codex-e2e"},
        "file",
        file_path,
        mime,
    )
    status, data = request_json(
        opener,
        "POST",
        "/api/v1/investigate",
        body,
        {"Content-Type": content_type, **csrf_header(opener)},
        timeout=120,
    )
    if status != 200:
        raise RuntimeError(f"investigate failed for {file_path.name}: {status} {data}")
    return data["session_id"]


def wait_for_pause_or_complete(opener, session_id, timeout_s=240):
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        status, data = request_json(opener, "GET", f"/api/v1/sessions/{session_id}/arbiter-status")
        last = (status, data)
        if status == 200:
            state = data.get("status")
            if state in {"paused", "complete", "completed", "failed", "error"}:
                return data
            if data.get("awaiting_decision") or "pause" in str(data).lower():
                return data
        time.sleep(3)
    raise TimeoutError(f"session {session_id} did not pause/complete in time; last={last}")


def resume(opener, session_id, deep):
    status, data = request_json(
        opener,
        "POST",
        f"/api/v1/sessions/{session_id}/resume",
        {"deep_analysis": deep},
        headers=csrf_header(opener),
        timeout=60,
    )
    if status not in {200, 202}:
        raise RuntimeError(f"resume failed: {status} {data}")
    return data


def wait_for_report(opener, session_id, timeout_s=420):
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        status, data = request_json(opener, "GET", f"/api/v1/sessions/{session_id}/report", timeout=60)
        last = (status, data)
        if status == 200:
            return data
        if status not in {202, 404}:
            raise RuntimeError(f"report failed: {status} {data}")
        time.sleep(4)
    raise TimeoutError(f"report timeout for {session_id}; last={last}")


def summarize_report(label, report):
    per_agent = report.get("per_agent_findings") or {}
    metrics = report.get("per_agent_metrics") or {}
    return {
        "label": label,
        "session_id": report.get("session_id"),
        "verdict": report.get("overall_verdict"),
        "confidence": report.get("overall_confidence"),
        "manipulation_probability": report.get("manipulation_probability"),
        "signature_present": bool(report.get("cryptographic_signature")),
        "hash_present": bool(report.get("report_hash")),
        "applicable_agent_count": report.get("applicable_agent_count"),
        "agent_finding_counts": {k: len(v or []) for k, v in per_agent.items()},
        "metric_agents": sorted(metrics.keys()),
        "degradation_flags": report.get("degradation_flags") or [],
        "summary_len": len(report.get("executive_summary") or ""),
        "verdict_sentence_len": len(report.get("verdict_sentence") or ""),
    }


def run_case(opener, label, filename, deep=True):
    session_id = start_investigation(opener, ROOT / filename, f"codex-e2e-{label}-{int(time.time())}")
    first_state = wait_for_pause_or_complete(opener, session_id)
    if str(first_state.get("status")).lower() != "complete":
        resume(opener, session_id, deep)
    report = wait_for_report(opener, session_id)
    return summarize_report(label, report)


def main():
    opener = login()
    cases = [
        ("image", "e2e_image.jpg", True),
        ("audio", "e2e_audio.wav", True),
        ("video", "e2e_video.mp4", True),
    ]
    summaries = []
    for label, filename, deep in cases:
        print(f"RUN {label} {filename}", flush=True)
        try:
            summaries.append(run_case(opener, label, filename, deep=deep))
        except Exception as exc:
            summaries.append({"label": label, "error": str(exc)})
            print(f"ERROR {label}: {exc}", file=sys.stderr, flush=True)
    print(json.dumps(summaries, indent=2))
    if any("error" in item for item in summaries):
        sys.exit(1)


if __name__ == "__main__":
    main()

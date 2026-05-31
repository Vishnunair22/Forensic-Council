#!/usr/bin/env python3
"""Image pipeline acceptance runner for local Docker stacks.

Generates a small forensic image corpus, runs each image through the public API,
resumes either initial-only or deep analysis, and records report quality signals.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont, ImageOps, PngImagePlugin

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "scratch" / "acceptance_images"
RESULTS_DIR = ROOT / "scratch" / "acceptance_results"


def _read_env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value:
        return value
    env_path = ROOT / ".env"
    if not env_path.exists():
        return default
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, raw = line.split("=", 1)
        if key.strip() == name:
            return raw.strip().strip('"').strip("'")
    return default


def _font(size: int = 18) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _gradient(size: tuple[int, int], c1: tuple[int, int, int], c2: tuple[int, int, int]) -> Image.Image:
    w, h = size
    img = Image.new("RGB", size)
    px = img.load()
    for y in range(h):
        t = y / max(1, h - 1)
        color = tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3))
        for x in range(w):
            px[x, y] = color
    return img


def generate_corpus() -> list[dict[str, Any]]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any]] = []

    # 1. Metadata-rich camera-like JPEG.
    img = _gradient((1280, 850), (130, 170, 210), (45, 70, 55))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 610, 1280, 850), fill=(40, 75, 42))
    d.ellipse((900, 120, 1040, 260), fill=(245, 220, 140))
    d.rectangle((330, 420, 560, 650), fill=(142, 111, 79))
    d.text((36, 34), "Camera-like outdoor scene", fill=(15, 25, 25), font=_font(26))
    exif = Image.Exif()
    exif[271] = "ForensicCouncilCam"
    exif[272] = "FC-Prime-2026"
    exif[306] = "2026:05:30 10:12:44"
    exif[36867] = "2026:05:30 10:12:44"
    path = OUT_DIR / "camera_metadata_scene.jpg"
    img.save(path, quality=92, exif=exif)
    cases.append({"name": "camera_metadata_scene", "path": path, "expect_agents": ["Agent1", "Agent3", "Agent5"]})

    # 2. Screenshot/document UI PNG.
    img = Image.new("RGB", (1280, 760), (248, 250, 252))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 1280, 68), fill=(35, 45, 64))
    d.rectangle((24, 18, 360, 50), fill=(255, 255, 255))
    d.text((42, 26), "https://court.example/evidence", fill=(20, 40, 60), font=_font(16))
    d.rectangle((88, 118, 1192, 660), outline=(180, 190, 205), width=2)
    d.text((118, 150), "Case Exhibit: Contract Screenshot", fill=(25, 35, 45), font=_font(30))
    for i, line in enumerate(["Invoice #FC-2026-001", "Amount: $12,430.00", "Status: PAID", "Timestamp: 2026-05-30 10:14 UTC"]):
        d.text((135, 230 + i * 54), line, fill=(45, 55, 65), font=_font(24))
    path = OUT_DIR / "screenshot_document.png"
    img.save(path)
    cases.append({"name": "screenshot_document", "path": path, "expect_agents": ["Agent1", "Agent3", "Agent5"]})

    # 3. Visible splice/composite JPEG.
    base = _gradient((1100, 760), (170, 185, 180), (72, 86, 84))
    patch = Image.new("RGB", (260, 190), (190, 45, 42))
    pd = ImageDraw.Draw(patch)
    pd.text((28, 70), "INSERTED\nREGION", fill=(255, 255, 255), font=_font(28))
    base.paste(patch, (650, 330))
    d = ImageDraw.Draw(base)
    d.rectangle((650, 330, 910, 520), outline=(20, 20, 20), width=3)
    path = OUT_DIR / "obvious_composite.jpg"
    base.save(path, quality=72)
    cases.append({"name": "obvious_composite", "path": path, "expect_agents": ["Agent1", "Agent3", "Agent5"]})

    # 4. AI metadata PNG.
    img = Image.new("RGB", (896, 896), (28, 31, 38))
    d = ImageDraw.Draw(img)
    for i in range(18):
        d.ellipse((70 + i * 39, 150, 190 + i * 39, 270), outline=(120, 200, 235), width=3)
    d.text((96, 420), "Synthetic-style image with embedded generation metadata", fill=(235, 240, 245), font=_font(24))
    meta = PngImagePlugin.PngInfo()
    meta.add_text("parameters", "prompt: cyber forensic lab, model: Stable Diffusion XL, sampler: Euler")
    meta.add_text("Software", "AUTOMATIC1111 Stable Diffusion WebUI")
    path = OUT_DIR / "ai_metadata_sdxl.png"
    img.save(path, pnginfo=meta)
    cases.append({"name": "ai_metadata_sdxl", "path": path, "expect_agents": ["Agent1", "Agent3", "Agent5"]})

    # 5. Metadata-stripped recompressed WebP.
    img = _gradient((900, 620), (230, 215, 190), (88, 104, 120))
    d = ImageDraw.Draw(img)
    d.rectangle((120, 140, 760, 480), fill=(245, 245, 235), outline=(70, 80, 95), width=3)
    d.text((150, 230), "Recompressed social-media style image", fill=(50, 60, 70), font=_font(24))
    path = OUT_DIR / "metadata_stripped.webp"
    ImageOps.exif_transpose(img).save(path, quality=55, method=6)
    cases.append({"name": "metadata_stripped_webp", "path": path, "expect_agents": ["Agent1", "Agent3", "Agent5"]})

    # 6. Small BMP edge case.
    img = Image.new("RGB", (320, 220), (235, 235, 235))
    d = ImageDraw.Draw(img)
    d.rectangle((40, 40, 280, 180), outline=(20, 20, 20), width=2)
    d.text((70, 95), "BMP EDGE", fill=(20, 20, 20), font=_font(20))
    path = OUT_DIR / "small_bmp_edge.bmp"
    img.save(path)
    cases.append({"name": "small_bmp_edge", "path": path, "expect_agents": ["Agent1", "Agent3", "Agent5"]})

    return cases


def _csrf(client: httpx.Client) -> str:
    return client.cookies.get("csrf_token", "")


def login(client: httpx.Client, base_url: str) -> str:
    password = _read_env("BOOTSTRAP_INVESTIGATOR_PASSWORD") or _read_env("DEMO_PASSWORD")
    if not password:
        raise RuntimeError("No investigator password found in .env")
    response = client.post(
        f"{base_url}/api/v1/auth/login",
        data={"username": "investigator", "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    response.raise_for_status()
    token = response.json()["access_token"]
    return token


def _post_json(client: httpx.Client, url: str, token: str, payload: dict[str, Any]) -> httpx.Response:
    return client.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {token}", "X-CSRF-Token": _csrf(client)},
    )


def submit_case(client: httpx.Client, base_url: str, token: str, case: dict[str, Any]) -> str:
    path = Path(case["path"])
    case_id = f"CASE-ACCEPT-{int(time.time())}-{case['name'][:22]}".replace("_", "-")
    with path.open("rb") as fh:
        response = client.post(
            f"{base_url}/api/v1/investigate",
            data={"case_id": case_id, "investigator_id": "acceptance-runner"},
            files={"file": (path.name, fh, _mime(path))},
            headers={"Authorization": f"Bearer {token}", "X-CSRF-Token": _csrf(client)},
        )
    if response.status_code == 409:
        detail = response.json().get("detail", {})
        if isinstance(detail, dict) and detail.get("existing_session_id"):
            return str(detail["existing_session_id"])
    response.raise_for_status()
    return response.json()["session_id"]


def _mime(path: Path) -> str:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
    }.get(path.suffix.lower(), "application/octet-stream")


def wait_and_resume(
    client: httpx.Client,
    base_url: str,
    token: str,
    session_id: str,
    deep: bool,
    timeout_s: int,
) -> dict[str, Any]:
    start = time.time()
    last_body: dict[str, Any] = {}
    resume_count = 0
    deep_report_requested = False
    while time.time() - start < timeout_s:
        report = client.get(
            f"{base_url}/api/v1/sessions/{session_id}/report",
            headers={"Authorization": f"Bearer {token}"},
        )
        if report.status_code == 200:
            return {"report": report.json(), "resume_count": resume_count}
        if report.status_code >= 500:
            raise RuntimeError(f"report failed {report.status_code}: {report.text[:500]}")
        try:
            last_body = report.json()
        except Exception:
            last_body = {"raw": report.text[:500]}

        status_text = json.dumps(last_body).lower()
        initial_gate_open = (
            resume_count == 0
            and (
                "awaiting_decision" in status_text
                or "initial_results_ready" in status_text
                or "initial analysis" in status_text
            )
        )
        deep_gate_open = deep and not deep_report_requested and (
            "awaiting_deep_report" in status_text
            or "deep_results_ready" in status_text
            or "deep analysis complete" in status_text
        )
        should_resume = initial_gate_open or deep_gate_open
        if should_resume:
            expected_phase = "initial" if initial_gate_open else "deep"
            resume = _post_json(
                client,
                f"{base_url}/api/v1/sessions/{session_id}/resume",
                token,
                {
                    "deep_analysis": deep if initial_gate_open else False,
                    "expected_phase": expected_phase,
                },
            )
            if resume.status_code in (200, 202):
                resume_count += 1
                if resume_count > 1:
                    deep_report_requested = True
            elif resume.status_code not in (400, 404, 409):
                raise RuntimeError(f"resume failed {resume.status_code}: {resume.text[:500]}")
        time.sleep(5)
    raise TimeoutError(f"session {session_id} timed out; last={last_body}")


def report_quality(report: dict[str, Any], expected_agents: list[str], deep: bool) -> dict[str, Any]:
    findings = report.get("per_agent_findings") or {}
    metrics = report.get("per_agent_metrics") or {}
    issues: list[str] = []
    if bool(report.get("is_deep_analysis")) != deep:
        issues.append(f"is_deep_analysis mismatch: got {report.get('is_deep_analysis')} expected {deep}")
    for agent in expected_agents:
        agent_findings = findings.get(agent) or findings.get(agent.lower()) or []
        if not agent_findings:
            issues.append(f"{agent} produced no findings")
        metric = metrics.get(agent) or metrics.get(agent.lower()) or {}
        if metric and int(metric.get("total_tools_called") or 0) == 0:
            issues.append(f"{agent} metric shows zero tools called")
    if not report.get("executive_summary"):
        issues.append("missing executive_summary")
    if not report.get("key_findings"):
        issues.append("missing key_findings")
    if not report.get("cryptographic_signature") or not report.get("report_hash"):
        issues.append("missing report integrity fields")
    if str(report.get("overall_verdict") or "").upper() in {"", "REVIEW REQUIRED"}:
        issues.append(f"weak overall_verdict: {report.get('overall_verdict')}")
    return {
        "issues": issues,
        "overall_verdict": report.get("overall_verdict"),
        "overall_confidence": report.get("overall_confidence"),
        "overall_error_rate": report.get("overall_error_rate"),
        "degradation_flags": report.get("degradation_flags"),
        "agent_counts": {agent: len(rows or []) for agent, rows in findings.items()},
        "tool_metrics": metrics,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--mode", choices=["initial", "deep", "both"], default="deep")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    cases = generate_corpus()
    if args.limit:
        cases = cases[: args.limit]
    modes = [False, True] if args.mode == "both" else [args.mode == "deep"]

    run_result: dict[str, Any] = {
        "started_at": datetime.now(UTC).isoformat(),
        "base_url": args.base_url,
        "cases": [],
    }
    with httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        token = login(client, args.base_url)
        for case in cases:
            for deep in modes:
                label = f"{case['name']}:{'deep' if deep else 'initial'}"
                print(f"[acceptance] starting {label}", flush=True)
                session_id = submit_case(client, args.base_url, token, case)
                result = wait_and_resume(client, args.base_url, token, session_id, deep, args.timeout)
                report = result["report"]
                quality = report_quality(report, case["expect_agents"], deep)
                record = {
                    "case": case["name"],
                    "file": str(case["path"]),
                    "deep": deep,
                    "session_id": session_id,
                    "quality": quality,
                }
                run_result["cases"].append(record)
                out_report = RESULTS_DIR / f"{case['name']}_{'deep' if deep else 'initial'}_{session_id}.json"
                out_report.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
                print(f"[acceptance] completed {label} issues={len(quality['issues'])}", flush=True)

    summary_path = RESULTS_DIR / f"summary_{int(time.time())}.json"
    summary_path.write_text(json.dumps(run_result, indent=2, default=str), encoding="utf-8")
    print(f"[acceptance] summary {summary_path}")
    total_issues = sum(len(c["quality"]["issues"]) for c in run_result["cases"])
    return 1 if total_issues else 0


if __name__ == "__main__":
    raise SystemExit(main())

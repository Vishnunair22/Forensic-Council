#!/usr/bin/env python3
"""Live end-to-end audio investigation to exercise Agent2 + deterministic synthesis."""
from __future__ import annotations
import asyncio, json, os, random, subprocess, sys, time
import httpx

BASE = "http://localhost:8000"
PASS = os.environ["BOOTSTRAP_INVESTIGATOR_PASSWORD"]


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=60.0, follow_redirects=True) as c:
        r = await c.post("/api/v1/auth/login", data={"username": "investigator", "password": PASS})
        print("login:", r.status_code)
        if r.status_code != 200:
            print(r.text[:400]); sys.exit(1)
        tok = r.json()["access_token"]
        c.headers["Authorization"] = f"Bearer {tok}"
        csrf = c.cookies.get("csrf_token")
        if csrf:
            c.headers["X-CSRF-Token"] = csrf

        wav = "/tmp/audit_audio.wav"
        dur = round(random.uniform(1.5, 2.5), 3)
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=f={random.randint(300,600)}:r=44100",
             "-t", str(dur), wav],
            capture_output=True, timeout=30,
        )
        with open(wav, "rb") as f:
            r = await c.post(
                "/api/v1/investigate",
                files={"file": ("audit_audio.wav", f, "audio/wav")},
                data={"case_id": "CASE-AUDIT-A1", "investigator_id": "investigator"},
            )
        print("investigate:", r.status_code)
        if r.status_code not in (200, 202):
            print(r.text[:600]); sys.exit(1)
        body = r.json()
        sid = body.get("session_id") or body.get("session", {}).get("session_id")
        print("session_id:", sid, "| applicable_agents:", body.get("applicable_agents"))

        # Drive the two HITL gates (initial→deep, deep→report) via /resume.
        resumed = {"initial": False, "deep": False}
        report = None
        for i in range(120):
            await asyncio.sleep(2)
            sr = await c.get(f"/api/v1/sessions/{sid}")
            status = sr.json().get("status", "") if sr.status_code == 200 else ""
            if status == "awaiting_decision" and not resumed["initial"]:
                rd = await c.post(f"/api/v1/sessions/{sid}/resume",
                                  json={"deep_analysis": True, "expected_phase": "initial"})
                print(f"  resume initial(deep=True) -> {rd.status_code} {rd.text[:120]}")
                resumed["initial"] = True
            elif status == "awaiting_deep_report" and not resumed["deep"]:
                rd = await c.post(f"/api/v1/sessions/{sid}/resume",
                                  json={"deep_analysis": False, "expected_phase": "deep"})
                print(f"  resume deep(accept) -> {rd.status_code} {rd.text[:120]}")
                resumed["deep"] = True
            rr = await c.get(f"/api/v1/sessions/{sid}/report")
            if rr.status_code == 200:
                report = rr.json()
                break
            if i % 5 == 0:
                print(f"  ...poll {i} status={status} report={rr.status_code}")

        if not report:
            print("NO REPORT after polling"); sys.exit(1)

        print("\n==== REPORT ====")
        print("overall_verdict:", report.get("overall_verdict"))
        agents = report.get("agent_reports") or report.get("agents") or report.get("per_agent") or []
        if isinstance(agents, dict):
            agents = list(agents.values())
        print(f"agent_reports: {len(agents)}")
        for a in agents:
            if not isinstance(a, dict):
                continue
            aid = a.get("agent_id") or a.get("agent") or "?"
            role = a.get("agent_role") or a.get("role") or ""
            verdict = a.get("verdict") or a.get("agent_verdict") or ""
            conf = a.get("agent_confidence") or a.get("confidence")
            src = a.get("synthesis_source", "")
            leaked = "You are" in str(role)
            print(f"  [{aid}] verdict={verdict} conf={conf} role={role!r} src={src} LEAKED_ROLE={leaked}")
        print("\nDONE")


if __name__ == "__main__":
    asyncio.run(main())

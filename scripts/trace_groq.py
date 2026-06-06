"""Trace the GROQ synthesis path using a doctored image that triggers alert verdicts."""
import asyncio, json, os, random, httpx
import numpy as np
from skimage import data
from PIL import Image


def make_doctored():
    arr = np.array(Image.fromarray(data.astronaut()).convert("RGB"))
    # Copy-move: duplicate a 120x120 block to another location (classic tamper).
    block = arr[60:180, 60:180].copy()
    arr[300:420, 300:420] = block
    # Paste a hard-edged bright rectangle (splice-like discontinuity).
    arr[20:90, 380:470] = [random.randint(200, 255), 20, 200]
    p = "/tmp/doctored.jpg"
    Image.fromarray(arr).save(p, "JPEG", quality=92)
    return p


async def main():
    p = make_doctored()
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=60) as c:
        r = await c.post("/api/v1/auth/login", data={"username": "investigator", "password": os.environ["BOOTSTRAP_INVESTIGATOR_PASSWORD"]})
        c.headers["Authorization"] = "Bearer " + r.json()["access_token"]
        cs = c.cookies.get("csrf_token"); c.headers["X-CSRF-Token"] = cs if cs else ""
        with open(p, "rb") as f:
            r = await c.post("/api/v1/investigate", files={"file": ("doctored.jpg", f, "image/jpeg")},
                             data={"case_id": "CASE-GROQ", "investigator_id": "investigator"})
        sid = r.json()["session_id"]
        ri = {"i": False, "d": False}
        rep = None
        for i in range(150):
            await asyncio.sleep(2)
            st = (await c.get(f"/api/v1/sessions/{sid}")).json().get("status", "")
            if st == "awaiting_decision" and not ri["i"]:
                await c.post(f"/api/v1/sessions/{sid}/resume", json={"deep_analysis": True, "expected_phase": "initial"}); ri["i"] = True
            elif st == "awaiting_deep_report" and not ri["d"]:
                await c.post(f"/api/v1/sessions/{sid}/resume", json={"deep_analysis": False, "expected_phase": "deep"}); ri["d"] = True
            rr = await c.get(f"/api/v1/sessions/{sid}/report")
            if rr.status_code == 200:
                rep = rr.json(); break
    if not rep:
        print("NO REPORT"); return
    print("overall:", rep.get("overall_verdict"))
    nar = rep.get("per_agent_narrative_structured", {})
    for aid in ("Agent1", "Agent3", "Agent5"):
        summ = rep.get("per_agent_summary", {}).get(aid, {})
        n = (nar.get(aid) if isinstance(nar, dict) else {}) or {}
        print(f"\n===== {aid}  verdict={summ.get('verdict')} src={n.get('synthesis_source')} =====")
        print(" brief:", (n.get("agent_brief") or "")[:260])
        print(" key_findings:", json.dumps(n.get("key_findings"))[:260])
    with open("/tmp/trace_groq.json", "w") as f:
        json.dump({"overall": rep.get("overall_verdict"), "narrative": nar,
                   "summary": rep.get("per_agent_summary")}, f, indent=1, default=str)


asyncio.run(main())

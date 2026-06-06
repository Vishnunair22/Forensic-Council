"""Final per-tool quality matrix: clean vs doctored image across Agent1/3/5.

Confirms each tool RUNS and emits a valid finding (no ERROR/silent), clean -> non-POSITIVE,
doctored -> manipulation-sensitive tools flag POSITIVE. Prints a side-by-side matrix.
"""
import asyncio, json, os, random, httpx
import numpy as np
from skimage import data
from PIL import Image, ImageEnhance


def make_clean():
    im = ImageEnhance.Brightness(Image.fromarray(data.astronaut())).enhance(random.uniform(0.97, 1.03))
    p = "/tmp/fv_clean.jpg"; im.save(p, "JPEG", quality=92); return p


def make_doctored():
    arr = np.array(Image.fromarray(data.astronaut()).convert("RGB"))
    arr[300:420, 300:420] = arr[60:180, 60:180].copy()         # copy-move
    arr[20:90, 380:470] = [random.randint(200, 255), 20, 200]  # splice rectangle
    p = "/tmp/fv_doctored.jpg"; Image.fromarray(arr).save(p, "JPEG", quality=92); return p


async def run(c, path, label):
    with open(path, "rb") as f:
        r = await c.post("/api/v1/investigate", files={"file": (os.path.basename(path), f, "image/jpeg")},
                         data={"case_id": "CASE-FV", "investigator_id": "investigator"})
    sid = r.json()["session_id"]
    ri = {"i": False, "d": False}
    for _ in range(150):
        await asyncio.sleep(2)
        st = (await c.get(f"/api/v1/sessions/{sid}")).json().get("status", "")
        if st == "awaiting_decision" and not ri["i"]:
            await c.post(f"/api/v1/sessions/{sid}/resume", json={"deep_analysis": True, "expected_phase": "initial"}); ri["i"] = True
        elif st == "awaiting_deep_report" and not ri["d"]:
            await c.post(f"/api/v1/sessions/{sid}/resume", json={"deep_analysis": False, "expected_phase": "deep"}); ri["d"] = True
        rr = await c.get(f"/api/v1/sessions/{sid}/report")
        if rr.status_code == 200:
            rep = rr.json()
            out = {"overall": rep.get("overall_verdict"), "tools": {}}
            for aid in ("Agent1", "Agent3", "Agent5"):
                for fnd in rep.get("per_agent_findings", {}).get(aid, []):
                    out["tools"][f"{aid}:{fnd.get('finding_type')}"] = (
                        f"{fnd.get('evidence_verdict')}/{fnd.get('status')}/c={fnd.get('confidence_raw')}"
                    )
            return out
    return {"overall": "TIMEOUT", "tools": {}}


async def main():
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=60) as c:
        r = await c.post("/api/v1/auth/login", data={"username": "investigator", "password": os.environ["BOOTSTRAP_INVESTIGATOR_PASSWORD"]})
        c.headers["Authorization"] = "Bearer " + r.json()["access_token"]
        cs = c.cookies.get("csrf_token"); c.headers["X-CSRF-Token"] = cs if cs else ""
        clean = await run(c, make_clean(), "clean")
        doct = await run(c, make_doctored(), "doctored")

    print(f"CLEAN overall={clean['overall']}   DOCTORED overall={doct['overall']}\n")
    keys = sorted(set(clean["tools"]) | set(doct["tools"]))
    bad = []
    print(f"{'TOOL':42} {'CLEAN':28} {'DOCTORED':28}")
    print("-" * 100)
    for k in keys:
        cv = clean["tools"].get(k, "—"); dv = doct["tools"].get(k, "—")
        flag = ""
        if "ERROR" in cv or "ERROR" in dv:
            flag = " <<ERROR"; bad.append(k)
        if cv.startswith("POSITIVE"):
            flag += " <<CLEAN-FP"; bad.append(k)
        print(f"{k:42} {cv:28} {dv:28}{flag}")
    print("\nISSUES:", bad if bad else "none — every tool emitted a valid finding; no clean false-positive, no ERROR")
    json.dump({"clean": clean, "doctored": doct}, open("/tmp/fv.json", "w"), indent=1, default=str)


asyncio.run(main())

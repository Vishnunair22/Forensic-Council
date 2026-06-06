"""Real e2e image investigation with a REAL photo (astronaut), deep phase, per-tool dump.

Usage: python3 live_image_audit.py <FORMAT>
Ground-truth audit: what each tool actually produces in the worker pipeline.
"""
import asyncio, json, os, random, sys, httpx
from skimage import data
from PIL import Image

FMT = (sys.argv[1] if len(sys.argv) > 1 else "JPEG").upper()
SPEC = {"JPEG": (".jpg", "image/jpeg"), "PNG": (".png", "image/png"),
        "TIFF": (".tiff", "image/tiff"), "WEBP": (".webp", "image/webp"),
        "GIF": (".gif", "image/gif"), "BMP": (".bmp", "image/bmp")}
suffix, mime = SPEC[FMT]


def make_image():
    arr = data.astronaut()
    im = Image.fromarray(arr)
    p = f"/tmp/audit_real{suffix}"
    kw = {}
    if FMT == "JPEG":
        kw["quality"] = 92
    # Unique-hash without a localized anomaly: apply a GLOBAL brightness jitter.
    # A single random pixel is a real localized splice/noise signal on lossless
    # formats (and was confounding this audit); a uniform brightness scale is a
    # natural global transform that changes every byte but introduces no anomaly.
    from PIL import ImageEnhance
    im = ImageEnhance.Brightness(im).enhance(random.uniform(0.97, 1.03))
    if FMT == "GIF":
        im = im.convert("P")
    im.save(p, FMT, **kw)
    return p


async def main():
    p = make_image()
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=60) as c:
        r = await c.post("/api/v1/auth/login", data={"username": "investigator", "password": os.environ["BOOTSTRAP_INVESTIGATOR_PASSWORD"]})
        c.headers["Authorization"] = "Bearer " + r.json()["access_token"]
        cs = c.cookies.get("csrf_token"); c.headers["X-CSRF-Token"] = cs if cs else ""
        with open(p, "rb") as f:
            r = await c.post("/api/v1/investigate", files={"file": (f"a{suffix}", f, mime)},
                             data={"case_id": "CASE-IMGAUDIT", "investigator_id": "investigator"})
        if r.status_code != 200:
            print("investigate FAILED", r.status_code, r.text[:200]); return
        sid = r.json()["session_id"]
        print(f"FORMAT={FMT} sid={sid[:8]} agents={r.json().get('applicable_agents')}")
        ri = {"i": False, "d": False}
        for i in range(150):
            await asyncio.sleep(2)
            st = (await c.get(f"/api/v1/sessions/{sid}")).json().get("status", "")
            if st == "awaiting_decision" and not ri["i"]:
                await c.post(f"/api/v1/sessions/{sid}/resume", json={"deep_analysis": True, "expected_phase": "initial"}); ri["i"] = True
            elif st == "awaiting_deep_report" and not ri["d"]:
                await c.post(f"/api/v1/sessions/{sid}/resume", json={"deep_analysis": False, "expected_phase": "deep"}); ri["d"] = True
            rr = await c.get(f"/api/v1/sessions/{sid}/report")
            if rr.status_code == 200:
                rep = rr.json()
                print("overall:", rep.get("overall_verdict"))
                for aid in ("Agent1", "Agent3", "Agent5"):
                    print(f"\n=== {aid}  summary={rep.get('per_agent_summary',{}).get(aid,{}).get('verdict')} ===")
                    for f in rep.get("per_agent_findings", {}).get(aid, []):
                        print(f"  {str(f.get('finding_type'))[:30]:30} | {str(f.get('evidence_verdict')):13} | {str(f.get('status')):12} | c={f.get('confidence_raw')} | {str(f.get('reasoning_summary') or '')[:55]}")
                with open(f"/tmp/live_{FMT}.json", "w") as jf:
                    json.dump(rep.get("per_agent_findings", {}), jf, indent=1, default=str)
                return
            if i % 8 == 0:
                print("  poll", i, "status=", st)
        print("timeout")
    os.unlink(p)


asyncio.run(main())

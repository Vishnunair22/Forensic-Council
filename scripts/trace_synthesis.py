"""Trace visual-context creation -> grounding -> per-agent synthesis for one investigation."""
import asyncio, json, os, random, sys, httpx
from skimage import data
from PIL import Image, ImageEnhance

FMT = (sys.argv[1] if len(sys.argv) > 1 else "JPEG").upper()
SPEC = {"JPEG": (".jpg", "image/jpeg"), "PNG": (".png", "image/png")}
suffix, mime = SPEC.get(FMT, (".jpg", "image/jpeg"))


def make():
    im = Image.fromarray(data.astronaut())
    im = ImageEnhance.Brightness(im).enhance(random.uniform(0.97, 1.03))
    p = f"/tmp/trace{suffix}"
    im.save(p, FMT, **({"quality": 92} if FMT == "JPEG" else {}))
    return p


async def main():
    p = make()
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=60) as c:
        r = await c.post("/api/v1/auth/login", data={"username": "investigator", "password": os.environ["BOOTSTRAP_INVESTIGATOR_PASSWORD"]})
        c.headers["Authorization"] = "Bearer " + r.json()["access_token"]
        cs = c.cookies.get("csrf_token"); c.headers["X-CSRF-Token"] = cs if cs else ""
        with open(p, "rb") as f:
            r = await c.post("/api/v1/investigate", files={"file": (f"a{suffix}", f, mime)},
                             data={"case_id": "CASE-TRACE", "investigator_id": "investigator"})
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
    out = {}
    # (a) visual context — from visual_evidence_profile finding
    for f in rep.get("per_agent_findings", {}).get("Agent1", []):
        if f.get("finding_type") == "Visual Evidence Profile":
            md = f.get("metadata", {})
            out["VISUAL_CONTEXT"] = {
                "provider_used": md.get("provider_used"),
                "analysis_source": md.get("analysis_source"),
                "external_ai_used": md.get("external_ai_used"),
                "authenticity_verdict": md.get("authenticity_verdict"),
                "evidence_verdict": f.get("evidence_verdict"),
                "scene": (md.get("content_description") or "")[:120],
                "detected_objects": md.get("detected_objects"),
                "file_type_assessment": md.get("file_type_assessment"),
            }
    # (b) grounding flags per agent
    out["GROUNDING"] = {}
    for aid in ("Agent1", "Agent3", "Agent5"):
        rows = []
        for f in rep.get("per_agent_findings", {}).get(aid, []):
            md = f.get("metadata", {})
            rows.append({
                "tool": f.get("finding_type"),
                "grounded_by_visual_profile": md.get("grounded_by_visual_profile"),
                "uncorroborated_visual_claim": md.get("uncorroborated_visual_claim"),
                "visual_inference_only": md.get("visual_inference_only"),
            })
        out["GROUNDING"][aid] = rows
    # (c) synthesis
    out["SYNTHESIS"] = {}
    for aid in ("Agent1", "Agent3", "Agent5"):
        summ = rep.get("per_agent_summary", {}).get(aid, {})
        analysis = rep.get("per_agent_analysis", {})
        nar = rep.get("per_agent_narrative_structured", {})
        out["SYNTHESIS"][aid] = {
            "summary": summ,
            "analysis_present": aid in (analysis if isinstance(analysis, dict) else {}),
            "analysis": (analysis.get(aid) if isinstance(analysis, dict) else None),
            "narrative_structured": (nar.get(aid) if isinstance(nar, dict) else None),
        }
    with open("/tmp/trace_out.json", "w") as f:
        json.dump(out, f, indent=1, default=str)
    print(json.dumps(out, indent=1, default=str)[:3500])


asyncio.run(main())

"""Execute every non-gated image tool against a real sample image and capture findings.

Usage: python3 img_tool_exec_audit.py <FORMAT>   (JPEG|PNG|TIFF|WEBP|GIF|BMP)
Seeds cross-tool context in dependency order, runs each tool via registry.call
(content gate applied), and prints a per-tool audit row + dumps raw JSON.
"""
import asyncio, json, os, sys, tempfile, traceback
from unittest.mock import AsyncMock
from uuid import uuid4
os.environ.setdefault("APP_ENV", "testing")
from skimage import data
from PIL import Image
from agents.agent1_image import Agent1Image
from agents.agent3_object import Agent3Object
from agents.agent5_metadata import Agent5Metadata
from core.config import get_settings
from core.evidence import ArtifactType, EvidenceArtifact
from core.file_type_policy import get_applicable_agents, content_aware_gate

AGENTS = {"Agent1": Agent1Image, "Agent3": Agent3Object, "Agent5": Agent5Metadata}
FMT = (sys.argv[1] if len(sys.argv) > 1 else "JPEG").upper()
SPEC = {
    "JPEG": (".jpg", "image/jpeg"), "PNG": (".png", "image/png"),
    "TIFF": (".tiff", "image/tiff"), "WEBP": (".webp", "image/webp"),
    "GIF": (".gif", "image/gif"), "BMP": (".bmp", "image/bmp"),
}
suffix, mime = SPEC[FMT]

# Run context-seeding tools first so dependents have data.
PRIORITY = [
    "visual_evidence_profile", "exif_extract", "read_shared_image_context",
    "analyze_image_content", "object_detection", "file_hash_verify",
    "file_structure_analysis",
]


def make_image():
    arr = data.astronaut()
    im = Image.fromarray(arr)
    p = tempfile.mktemp(suffix=suffix)
    kw = {}
    if FMT == "JPEG":
        kw["quality"] = 92
        ex = Image.Exif(); ex[271] = "Canon"; ex[272] = "EOS 5D"; ex[305] = "Adobe Photoshop"; kw["exif"] = ex
    if FMT == "TIFF":
        ex = Image.Exif(); ex[271] = "Canon"; ex[272] = "EOS 5D"; kw["exif"] = ex
    if FMT == "GIF":
        im = im.convert("P")
    im.save(p, FMT, **kw)
    return p


def mk_agent(aid, path):
    art = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL, file_path=path, content_hash="abc123",
        action="upload", agent_id="system", session_id=uuid4(), metadata={"mime_type": mime})
    return AGENTS[aid](agent_id=aid, session_id=uuid4(), evidence_artifact=art,
        config=get_settings(), working_memory=AsyncMock(), episodic_memory=AsyncMock(),
        custody_logger=AsyncMock(), evidence_store=AsyncMock())


def classify(res: dict):
    """Return (flag, note) — flag in OK/ERROR/DEGRADED/EMPTY/NA."""
    if not isinstance(res, dict):
        return "ERROR", f"non-dict result: {type(res).__name__}"
    if res.get("error"):
        return "ERROR", str(res.get("error"))[:80]
    if res.get("available") is False:
        return "DEGRADED", "available=False " + str(res.get("limitation") or res.get("fallback_reason") or "")[:60]
    if res.get("degraded") is True:
        return "DEGRADED", str(res.get("limitation") or res.get("note") or "")[:60]
    na = res.get("not_applicable") or res.get("skipped") or str(res.get("verdict", "")).upper() == "NOT_APPLICABLE" or str(res.get("status", "")).upper() in ("NOT_APPLICABLE", "SKIPPED")
    if na:
        return "NA", str(res.get("reason") or res.get("note") or res.get("verdict") or "")[:60]
    meaningful = [k for k in res.keys() if k not in ("available", "court_defensible")]
    if len(meaningful) <= 1:
        return "EMPTY", f"keys={list(res.keys())}"
    return "OK", ""


async def run_agent(aid, path):
    agent = mk_agent(aid, path)
    reg = await agent.build_tool_registry()
    tools = sorted(reg._tools.keys())
    ordered = [t for t in PRIORITY if t in tools] + [t for t in tools if t not in PRIORITY]
    rows, dump = [], {}
    for t in ordered:
        if content_aware_gate(t, path, mime):
            rows.append((t, "GATE", "content-gated NOT_APPLICABLE"))
            continue
        try:
            tr = await reg.call(t, {"artifact": agent.evidence_artifact}, aid, agent.session_id,
                                 evidence_file_path=path, evidence_mime_type=mime)
            res = tr.data if hasattr(tr, "data") and isinstance(getattr(tr, "data", None), dict) else (tr if isinstance(tr, dict) else getattr(tr, "__dict__", {}))
            # ToolResult: prefer .output/.data
            for attr in ("output", "data", "result"):
                v = getattr(tr, attr, None)
                if isinstance(v, dict):
                    res = v; break
            flag, note = classify(res)
            conf = res.get("confidence") if isinstance(res, dict) else None
            verdict = res.get("verdict") or res.get("authenticity_verdict") if isinstance(res, dict) else None
            rows.append((t, flag, f"v={verdict} c={conf} {note}".strip()))
            dump[t] = {"flag": flag, "verdict": verdict, "confidence": conf,
                       "keys": list(res.keys()) if isinstance(res, dict) else None,
                       "sample": {k: res[k] for k in list(res.keys())[:8]} if isinstance(res, dict) else str(res)[:200]}
        except Exception as e:
            rows.append((t, "EXC", f"{type(e).__name__}: {e}"))
            dump[t] = {"flag": "EXC", "error": f"{type(e).__name__}: {e}", "tb": traceback.format_exc()[-400:]}
    return rows, dump


async def main():
    path = make_image()
    print(f"\n##### FORMAT={FMT} ({mime}) sample=astronaut #####")
    all_dump = {}
    for aid in get_applicable_agents(mime):
        if aid not in AGENTS:
            continue
        print(f"\n===== {aid} =====")
        rows, dump = await run_agent(aid, path)
        all_dump[aid] = dump
        for t, flag, note in rows:
            mark = "" if flag in ("OK", "GATE") else "  <<<"
            print(f"  [{flag:8}] {t:34} {note[:74]}{mark}")
    out = f"/tmp/audit_{FMT}.json"
    with open(out, "w") as f:
        json.dump(all_dump, f, indent=1, default=str)
    print(f"\nJSON -> {out}")
    os.unlink(path)


asyncio.run(main())

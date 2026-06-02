"""
Direct in-container investigation driver (bypasses the CSRF-gated HTTP path).

Runs the REAL ForensicCouncilPipeline.run_investigation — the same entry the
worker uses — auto-accepts the HITL gate to proceed into deep+arbiter, then
dumps: the 3 Gemini visual-context fields, each agent's initial tool findings
(from working memory), and the final report (per-agent + overall).

Usage:  python scripts/drive_investigation.py /path/to/image  [case_suffix]
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import uuid


def _j(obj, n=2000):
    try:
        return json.dumps(obj, indent=1, default=str)[:n]
    except Exception:
        return str(obj)[:n]


_INITIAL_SNAPSHOT = {}


async def _snapshot_initial(session_id):
    """Capture each agent's INITIAL working memory (before deep clears it)."""
    from core.persistence.redis_client import get_redis_client
    rc = await get_redis_client()
    snap = {}
    for ag in ("Agent1", "Agent3", "Agent5"):
        raw = await rc.get(f"wm:{session_id}:{ag}")
        if not raw:
            continue
        try:
            d = json.loads(raw)
        except Exception:
            continue
        gf = d.get("grounded_findings") or []
        tasks = d.get("tasks") or []
        snap[ag] = {
            "tools_ran": [
                {"tool": f.get("tool_name"), "verdict": f.get("evidence_verdict"),
                 "status": (f.get("metadata") or {}).get("status"),
                 "reasoning": (f.get("reasoning_summary") or "")[:140]}
                for f in gf
            ],
            "tasks": [{"d": t.get("description", "")[:55], "status": t.get("status"),
                       "ref": t.get("result_ref")} for t in tasks],
        }
    if snap:
        _INITIAL_SNAPSHOT.update(snap)


async def _auto_accept(pipeline, session_id):
    """Continuously answer EVERY HITL gate (initial->deep AND deep->report).

    On the FIRST gate (initial done) we snapshot the initial working memory so
    the initial per-agent findings + which tools actually ran are captured
    before the deep phase mutates state. Cancelled in main()'s finally.
    """
    snapped = False
    while True:
        if getattr(pipeline, "_awaiting_user_decision", False):
            if not snapped:
                try:
                    await _snapshot_initial(session_id)
                except Exception:
                    pass
                snapped = True
            pipeline.run_deep_analysis_flag = True
            pipeline.deep_analysis_decision_event.set()
        await asyncio.sleep(0.3)


async def _dump_agent_wm(session_id):
    from core.persistence.redis_client import get_redis_client
    rc = await get_redis_client()
    out = {}
    for ag in ("Agent1", "Agent3", "Agent5"):
        raw = await rc.get(f"wm:{session_id}:{ag}")
        if not raw:
            out[ag] = "(no working memory)"
            continue
        try:
            d = json.loads(raw)
        except Exception:
            out[ag] = "(unparseable)"
            continue
        gf = d.get("grounded_findings") or []
        out[ag] = [
            {
                "tool": f.get("tool_name"),
                "verdict": f.get("evidence_verdict"),
                "reasoning": (f.get("reasoning_summary") or "")[:200],
            }
            for f in gf
        ]
    return out


async def _dump_visual_context(session_id):
    from core.persistence.redis_client import get_redis_client
    rc = await get_redis_client()
    raw = await rc.get(f"visual_context:{session_id}")
    if not raw:
        return "(none)"
    try:
        d = json.loads(raw)
    except Exception:
        return "(unparseable)"
    return {
        "source": d.get("source"),
        "provider": d.get("provider_name"),
        "authenticity_verdict": d.get("authenticity_verdict"),
        "file_type": d.get("file_type_assessment"),
        "a_image_integrity": d.get("image_integrity_context"),
        "b_object_scene": d.get("object_scene_context"),
        "c_metadata_visual": d.get("metadata_visual_context"),
    }


async def main(path: str, suffix: str = "001"):
    from orchestration.pipeline import ForensicCouncilPipeline

    # Load signing keys from Postgres (worker does this at startup) so the
    # in-pipeline arbiter can sign the final report.
    from core.signing import get_keystore
    await get_keystore().initialize()

    data = open(path, "rb").read()
    sha = hashlib.sha256(data).hexdigest()
    sid = uuid.uuid4()

    # Fire the Gemini visual-context preflight before the pipeline runs — exactly
    # what the /investigate route does — and await it so the shared context is in
    # Redis before any agent grounds. The HTTP path fires this; run_investigation
    # alone does not, so without this the agents/arbiter race the late per-agent
    # Gemini call (the img1 "Visual context not found" false-positive).
    try:
        from core.config import get_settings
        from core.visual_context_store import create_visual_context_preflight
        await asyncio.wait_for(
            create_visual_context_preflight(
                session_id=str(sid), file_path=path, sha256=sha, config=get_settings()
            ),
            timeout=90,
        )
        print(f"[driver] visual-context preflight complete for {sid}")
    except Exception as _pf_err:
        print(f"[driver] preflight skipped/failed: {_pf_err}")

    pipeline = ForensicCouncilPipeline()
    accept = asyncio.create_task(_auto_accept(pipeline, sid))
    try:
        report = await asyncio.wait_for(
            pipeline.run_investigation(
                evidence_file_path=path,
                case_id=f"CASE-DRIVE-{suffix}",
                investigator_id="inv-investigator",
                original_filename=path.rsplit("/", 1)[-1],
                session_id=sid,
                content_sha256=sha,
                file_size_bytes=len(data),
            ),
            timeout=900,
        )
    finally:
        accept.cancel()

    vc = await _dump_visual_context(sid)
    wm = _INITIAL_SNAPSHOT or await _dump_agent_wm(sid)

    print("\n" + "=" * 70)
    print(f"SESSION {sid}  |  file={path.rsplit('/', 1)[-1]}")
    print("=" * 70)
    print("\n##### GEMINI 3 FIELDS #####")
    print(_j(vc, 3500))
    print("\n##### INITIAL PER-AGENT TOOL FINDINGS (working memory) #####")
    print(_j(wm, 3500))
    print("\n##### FINAL REPORT #####")
    rep = {
        "overall_verdict": getattr(report, "overall_verdict", None),
        "overall_confidence": getattr(report, "overall_confidence", None),
        "overall_error_rate": getattr(report, "overall_error_rate", None),
        "verdict_sentence": getattr(report, "verdict_sentence", None),
        "executive_summary": getattr(report, "executive_summary", None),
        "key_findings": getattr(report, "key_findings", None),
        "per_agent_metrics": getattr(report, "per_agent_metrics", None),
        "per_agent_analysis": getattr(report, "per_agent_analysis", None),
    }
    print(_j(rep, 5000))
    print("\n##### RAW per_agent_findings (tool / verdict / phase) — duplicate audit #####")
    _paf_raw = getattr(report, "per_agent_findings", {}) or {}
    for aid, flist in _paf_raw.items():
        rows = []
        seen_tool = {}
        for f in (flist or []):
            m = (f.get("metadata") if isinstance(f, dict) else {}) or {}
            tool = m.get("tool_name") or (f.get("finding_type") if isinstance(f, dict) else "") or "?"
            ver = (f.get("evidence_verdict") if isinstance(f, dict) else "") or "?"
            ph = m.get("analysis_phase", "initial")
            rows.append(f"{tool}|{ver}|{ph}")
            seen_tool[tool] = seen_tool.get(tool, 0) + 1
        dups = {t: c for t, c in seen_tool.items() if c > 1}
        print(f"  {aid}: {len(rows)} findings; tools-with-multiple-entries={dups}")
        for r in rows:
            print(f"     - {r}")

    summ = getattr(report, "per_agent_summary", {}) or {}
    analysis = getattr(report, "per_agent_analysis", {}) or {}
    paf = getattr(report, "per_agent_findings", {}) or {}
    _names = {"Agent1": "Image Integrity", "Agent3": "Object & Context", "Agent5": "Metadata"}
    for aid in ("Agent1", "Agent3", "Agent5"):
        s = summ.get(aid, {})
        print("\n" + "=" * 60)
        print(f"{_names.get(aid, aid)} ({aid})")
        print("=" * 60)
        print(f"Verdict score : {s.get('verdict', '?')}  —  {s.get('confidence_pct', '?')}%")
        print(f"Agent brief   : {analysis.get(aid, '(none)')}")
        print("Key findings  :")
        for f in (paf.get(aid) or []):
            if isinstance(f, dict):
                m = f.get("metadata") or {}
                ev = f.get("evidence_verdict")
                st = f.get("status")
                txt = (f.get("court_statement") or f.get("reasoning_summary") or f.get("key_signal") or "").strip()
                flag = "  [FAILED]" if (ev == "ERROR" or st in ("INCOMPLETE", "TIMEOUT", "ERROR")) else ""
                print(f"   • {txt[:200]}{flag}")
    print("\n##### END #####")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "001"))

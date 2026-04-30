import asyncio
import hashlib
import os
import struct
import tempfile
import time
import wave
from uuid import uuid4

import numpy as np
from PIL import Image


def _create_test_jpeg(path: str) -> str:
    img = Image.fromarray(np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8))
    img.save(path, format="JPEG", quality=85)
    return path


def _create_test_png(path: str) -> str:
    img = Image.fromarray(np.random.randint(0, 255, (64, 64, 4), dtype=np.uint8), mode="RGBA")
    img.save(path, format="PNG")
    return path


def _create_test_wav(path: str) -> str:
    n_channels = 1
    sampwidth = 2
    framerate = 44100
    duration = 1
    n_frames = framerate * duration
    with wave.open(path, "w") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(framerate)
        frames = b"".join(
            struct.pack(
                "<h",
                int(
                    32767
                    * 0.3
                    * __import__("math").sin(2 * __import__("math").pi * 440 * i / framerate)
                ),
            )
            for i in range(n_frames)
        )
        wf.writeframes(frames)
    return path


def _create_test_mp4(path: str) -> str:
    try:
        import cv2

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(path, fourcc, 10.0, (64, 64))
        for _ in range(10):
            frame = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
            out.write(frame)
        out.release()
    except ImportError:
        with open(path, "wb") as f:
            f.write(b"\x00" * 1024)
    return path


async def _run_file_analysis(file_path, mime_type, label):
    from agents.agent1_image import Agent1Image
    from agents.agent2_audio import Agent2Audio
    from agents.agent3_object import Agent3Object
    from agents.agent4_video import Agent4Video
    from agents.agent5_metadata import Agent5Metadata
    from agents.arbiter import CouncilArbiter
    from core.config import get_settings
    from core.custody_logger import CustodyLogger
    from core.episodic_memory import EpisodicMemory
    from core.evidence import ArtifactType, EvidenceArtifact
    from core.inter_agent_bus import InterAgentBus
    from core.persistence.evidence_store import EvidenceStore
    from core.working_memory import WorkingMemory

    settings = get_settings()
    sid = uuid4()
    with open(file_path, "rb") as f:
        ch = hashlib.sha256(f.read()).hexdigest()
    artifact = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=file_path,
        content_hash=ch,
        action="upload",
        agent_id="ingestion",
        session_id=sid,
        metadata={"mime_type": mime_type, "original_filename": os.path.basename(file_path)},
    )
    cl = CustodyLogger()
    es = EvidenceStore()
    bus = InterAgentBus()

    agents = [
        ("Agent1", Agent1Image, bus),
        ("Agent2", Agent2Audio, bus),
        ("Agent3", Agent3Object, bus),
        ("Agent4", Agent4Video, bus),
        ("Agent5", Agent5Metadata, None),
    ]
    findings_all = {}
    details = {}
    for aid, acls, ibus in agents:
        t0 = time.perf_counter()
        kw = {"inter_agent_bus": ibus} if ibus else {}
        try:
            agent = acls(
                agent_id=aid,
                session_id=sid,
                evidence_artifact=artifact,
                config=settings,
                working_memory=WorkingMemory(),
                episodic_memory=EpisodicMemory(),
                custody_logger=cl,
                evidence_store=es,
                **kw,
            )
            if not agent.supports_uploaded_file:
                findings_all[aid] = []
                details[aid] = "SKIP"
                continue
            fs = await asyncio.wait_for(agent.run_investigation(), timeout=180.0)
            nf = [f.model_dump(mode="json") if hasattr(f, "model_dump") else f for f in fs]
            findings_all[aid] = nf
            cv = [
                f.get("confidence_raw", 0)
                for f in nf
                if isinstance(f, dict) and f.get("confidence_raw") is not None
            ]
            tn = {(f.get("metadata") or {}).get("tool_name", "") for f in nf if isinstance(f, dict)}
            dg = sum(
                1 for f in nf if isinstance(f, dict) and (f.get("metadata") or {}).get("degraded")
            )
            avg_c = sum(cv) / len(cv) if cv else 0
            details[aid] = (
                f"{len(nf)}f/{len(tn)}t/conf={avg_c:.2f}/deg={dg}/{time.perf_counter() - t0:.0f}s"
            )
        except Exception as e:
            findings_all[aid] = [
                {"finding_type": "error", "status": "INCOMPLETE", "confidence_raw": 0.0}
            ]
            details[aid] = f"ERR:{str(e)[:80]}"

    ar = {aid: {"findings": fs} for aid, fs in findings_all.items() if fs}
    arbiter = CouncilArbiter(session_id=sid, config=settings)
    report = await arbiter.deliberate(ar, case_id=f"{label}-init", use_llm=True)

    ac = sum(1 for d in details.values() if not d.startswith("SKIP") and not d.startswith("ERR"))
    tf = sum(len(fs) for fs in findings_all.values())
    groq = len(report.per_agent_analysis) > 0 and len(report.executive_summary) > 50
    errs = [f"{aid}: {d}" for aid, d in details.items() if d.startswith("ERR")]

    print(f"\n{'=' * 55}")
    print(f"  {label} ({mime_type})")
    print(f"{'=' * 55}")
    for aid in ["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"]:
        print(f"  {aid}: {details.get(aid, '?')}")
    print(
        f"  ARBITER: {report.overall_verdict} conf={report.overall_confidence:.3f} manip={report.manipulation_probability:.3f}"
    )
    print(
        f"  GROQ: {'YES' if groq else 'NO'} narr={len(report.per_agent_analysis)} exec={len(report.executive_summary)}ch"
    )
    print(f"  VERDICT: {report.verdict_sentence}")
    print(f"  KEY FINDINGS: {report.key_findings[:3]}")
    for aid, s in report.per_agent_summary.items():
        if not s.get("skipped"):
            print(
                f"    {aid}: {s['verdict']} ({s['confidence_pct']}% conf, {s['error_rate_pct']}% err)"
            )

    return ac >= 2 and tf >= 5 and groq and not errs


async def main():
    tmpdir = tempfile.mkdtemp(prefix="forensic_test_")
    test_files = [
        (os.path.join(tmpdir, "test_jpeg.jpg"), "image/jpeg", "JPEG", _create_test_jpeg),
        (os.path.join(tmpdir, "test_png.png"), "image/png", "PNG", _create_test_png),
        (os.path.join(tmpdir, "test_audio.wav"), "audio/wav", "WAV", _create_test_wav),
        (os.path.join(tmpdir, "test_video.mp4"), "video/mp4", "MP4", _create_test_mp4),
    ]

    for fp, mt, lb, creator in test_files:
        creator(fp)

    results = []
    for fp, mt, lb, _ in test_files:
        ok = await _run_file_analysis(fp, mt, lb)
        results.append((lb, ok))

    import shutil

    shutil.rmtree(tmpdir, ignore_errors=True)

    print(f"\n\n{'=' * 55}")
    print("  INITIAL ANALYSIS - FINAL VERDICT")
    print(f"{'=' * 55}")
    all_ok = all(ok for _, ok in results)
    for lb, ok in results:
        print(f"  {lb:<6} {'PASS' if ok else 'FAIL'}")
    print(
        f"\n  OVERALL: {'GREEN' if all_ok else 'RED'} - Initial analysis pipeline {'is solid and ready' if all_ok else 'has issues'}"
    )


if __name__ == "__main__":
    asyncio.run(main())

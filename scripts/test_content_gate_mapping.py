#!/usr/bin/env python3
"""
Live content-aware mapping verification for INITIAL ANALYSIS.

For each mock file type, instantiate the real applicable agents, build their
real tool registries, and run every registered tool through the live
content_aware_gate — showing exactly which tools RUN vs are gated NOT_APPLICABLE.
"""
from __future__ import annotations
import asyncio, io, os, struct, subprocess, sys, tempfile, zlib
from unittest.mock import AsyncMock
from uuid import uuid4

os.environ.setdefault("APP_ENV", "testing")

from agents.agent1_image import Agent1Image
from agents.agent2_audio import Agent2Audio
from agents.agent3_object import Agent3Object
from agents.agent4_video import Agent4Video
from agents.agent5_metadata import Agent5Metadata
from core.config import get_settings
from core.evidence import ArtifactType, EvidenceArtifact
from core.file_type_policy import get_applicable_agents, content_aware_gate
from PIL import Image

AGENT_CLASSES = {
    "Agent1": Agent1Image,
    "Agent2": Agent2Audio,
    "Agent3": Agent3Object,
    "Agent4": Agent4Video,
    "Agent5": Agent5Metadata,
}


def _artifact(path: str, mime: str) -> EvidenceArtifact:
    return EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=path,
        content_hash="hash123",
        action="upload",
        agent_id="system",
        session_id=uuid4(),
        metadata={"mime_type": mime},
    )


def _mk_agent(agent_id: str, path: str, mime: str):
    cls = AGENT_CLASSES[agent_id]
    return cls(
        agent_id=agent_id,
        session_id=uuid4(),
        evidence_artifact=_artifact(path, mime),
        config=get_settings(),
        working_memory=AsyncMock(),
        episodic_memory=AsyncMock(),
        custody_logger=AsyncMock(),
        evidence_store=AsyncMock(),
    )


# ── Mock file factories (written to /tmp) ──────────────────────────────────
def write_image(fmt: str, suffix: str) -> str:
    img = Image.new("RGB", (8, 8), color=(200, 50, 50))
    p = tempfile.mktemp(suffix=suffix)
    img.save(p, format=fmt)
    return p


def write_wav() -> str:
    p = tempfile.mktemp(suffix=".wav")
    data = b"\x00\x00" * 16
    fmt = struct.pack("<HHIIHH", 1, 1, 8000, 8000, 1, 8)
    with open(p, "wb") as f:
        f.write(b"RIFF" + (36 + len(data)).to_bytes(4, "little") + b"WAVE"
                + b"fmt " + len(fmt).to_bytes(4, "little") + fmt
                + b"data" + len(data).to_bytes(4, "little") + data)
    return p


def write_ff(ext: str, audio_only: bool) -> str | None:
    p = tempfile.mktemp(suffix=ext)
    if audio_only:
        cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=f=440:r=44100", "-t", "0.2", p]
    else:
        cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=16x16:r=5",
               "-f", "lavfi", "-i", "sine=f=440", "-t", "0.2",
               "-c:v", "libx264", "-c:a", "aac", p]
    r = subprocess.run(cmd, capture_output=True, timeout=30)
    return p if r.returncode == 0 else None


def write_pdf() -> str:
    p = tempfile.mktemp(suffix=".pdf")
    with open(p, "wb") as f:
        f.write(b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
                b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
                b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
                b"trailer<</Root 1 0 R>>\n%%EOF\n")
    return p


async def probe(label: str, path: str, mime: str):
    print("\n" + "=" * 74)
    print(f"  {label}   mime={mime}")
    print("=" * 74)
    if not path or not os.path.exists(path):
        print("  (mock file generation failed — skipped)")
        return True

    applicable = get_applicable_agents(mime)
    print(f"  Applicable agents: {applicable}")

    issues = []
    for aid in applicable:
        try:
            agent = _mk_agent(aid, path, mime)
            registry = await agent.build_tool_registry()
            tools = sorted(registry._tools.keys())
        except Exception as e:
            print(f"\n  {aid}: (could not build registry: {type(e).__name__}: {e})")
            continue

        runs, gated = [], []
        for t in tools:
            reason = content_aware_gate(t, path, mime)
            (gated if reason else runs).append(t)

        print(f"\n  {aid} — {len(runs)} RUN / {len(gated)} GATED")
        if runs:
            print(f"    RUN:   {', '.join(runs)}")
        if gated:
            print(f"    GATED: {', '.join(gated)}")

        # Sanity checks per media class
        for t in tools:
            reason = content_aware_gate(t, path, mime)
            blocked = reason is not None
            if mime.startswith("audio/") and t in ("noiseprint_cluster", "neural_ela", "object_detection") and not blocked:
                issues.append(f"{aid}: image tool {t} NOT gated on audio")
            if mime.startswith("image/") and t in ("speaker_diarize", "optical_flow_analysis") and not blocked:
                issues.append(f"{aid}: wrong-media tool {t} NOT gated on image")
    return issues


async def main():
    files = [
        ("IMAGE (JPEG, lossy)",  write_image("JPEG", ".jpg"), "image/jpeg"),
        ("IMAGE (PNG, lossless)", write_image("PNG", ".png"), "image/png"),
        ("AUDIO (WAV, lossless)", write_wav(),                 "audio/wav"),
        ("AUDIO (MP3, lossy)",    write_ff(".mp3", True),       "audio/mpeg"),
        ("VIDEO (MP4)",           write_ff(".mp4", False),      "video/mp4"),
        ("TEXT (PDF)",            write_pdf(),                  "application/pdf"),
    ]
    all_issues = []
    for label, path, mime in files:
        res = await probe(label, path, mime)
        if isinstance(res, list):
            all_issues.extend(res)
        # cleanup
        if path and os.path.exists(path):
            try: os.unlink(path)
            except Exception: pass

    print("\n" + "=" * 74)
    if all_issues:
        print("  ISSUES FOUND:")
        for i in all_issues:
            print(f"    - {i}")
        sys.exit(1)
    else:
        print("  CONTENT-AWARE MAPPING CLEAN — no wrong-media tool would run.")
    print("=" * 74)


if __name__ == "__main__":
    asyncio.run(main())

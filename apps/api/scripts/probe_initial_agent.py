from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import subprocess
import struct
import tempfile
import wave
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
from PIL import Image, ImageDraw


def _create_jpeg(path: Path) -> None:
    img = Image.new("RGB", (192, 144), (42, 72, 116))
    draw = ImageDraw.Draw(img)
    draw.rectangle((18, 18, 84, 78), fill=(204, 76, 66))
    draw.ellipse((108, 34, 170, 96), fill=(86, 174, 112))
    draw.text((18, 112), "FC PROBE", fill=(245, 245, 245))
    img.save(path, format="JPEG", quality=88)


def _create_png(path: Path) -> None:
    arr = np.zeros((160, 160, 4), dtype=np.uint8)
    arr[:, :, 0] = np.linspace(20, 220, 160, dtype=np.uint8)
    arr[:, :, 1] = np.linspace(220, 40, 160, dtype=np.uint8)[:, None]
    arr[:, :, 2] = 128
    arr[:, :, 3] = 255
    Image.fromarray(arr, mode="RGBA").save(path, format="PNG")


def _create_tiff(path: Path) -> None:
    img = Image.new("RGB", (192, 144), (48, 92, 70))
    draw = ImageDraw.Draw(img)
    draw.rectangle((24, 24, 104, 88), fill=(196, 186, 84))
    draw.line((0, 143, 191, 0), fill=(232, 232, 232), width=3)
    draw.text((20, 112), "TIFF PROBE", fill=(255, 255, 255))
    img.save(path, format="TIFF")


def _create_wav(path: Path) -> None:
    framerate = 16_000
    duration_s = 2
    frames = bytearray()
    for i in range(framerate * duration_s):
        sample = int(32767 * 0.25 * math.sin(2 * math.pi * 440 * i / framerate))
        frames.extend(struct.pack("<h", sample))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(bytes(frames))


def _create_mp4(path: Path) -> None:
    import cv2

    raw_video = path.with_name("raw_video.mp4")
    wav_path = path.with_name("probe_audio.wav")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(raw_video), fourcc, 10.0, (160, 120))
    for idx in range(24):
        frame = np.zeros((120, 160, 3), dtype=np.uint8)
        frame[:, :, 0] = (idx * 7) % 255
        frame[:, :, 1] = np.linspace(40, 220, 160, dtype=np.uint8)
        frame[:, :, 2] = np.linspace(220, 40, 120, dtype=np.uint8)[:, None]
        cv2.putText(frame, "FC", (20 + idx, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)
        out.write(frame)
    out.release()
    _create_wav(wav_path)
    try:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(raw_video),
                "-i",
                str(wav_path),
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-shortest",
                str(path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        raw_video.replace(path)


SAMPLES = {
    "jpeg": ("probe.jpg", "image/jpeg", _create_jpeg),
    "png": ("probe.png", "image/png", _create_png),
    "tiff": ("probe.tiff", "image/tiff", _create_tiff),
    "wav": ("probe.wav", "audio/wav", _create_wav),
    "mp4": ("probe.mp4", "video/mp4", _create_mp4),
}


AGENT_CLASSES = {
    "Agent1": ("agents.agent1_image", "Agent1Image"),
    "Agent2": ("agents.agent2_audio", "Agent2Audio"),
    "Agent3": ("agents.agent3_object", "Agent3Object"),
    "Agent4": ("agents.agent4_video", "Agent4Video"),
    "Agent5": ("agents.agent5_metadata", "Agent5Metadata"),
}


async def _run_probe(agent_id: str, sample: str, include_findings: bool = False) -> dict[str, Any]:
    from importlib import import_module

    from core.config import get_settings
    from core.custody_logger import CustodyLogger
    from core.episodic_memory import get_episodic_memory
    from core.evidence import ArtifactType, EvidenceArtifact
    from core.inter_agent_bus import InterAgentBus
    from core.ml_subprocess import shutdown_ml_workers
    from core.persistence.evidence_store import EvidenceStore
    from core.working_memory import get_working_memory

    if agent_id not in AGENT_CLASSES:
        raise ValueError(f"Unknown agent_id: {agent_id}")
    if sample not in SAMPLES:
        raise ValueError(f"Unknown sample: {sample}")

    tmpdir = Path(tempfile.mkdtemp(prefix=f"probe_{agent_id.lower()}_"))
    filename, mime_type, creator = SAMPLES[sample]
    file_path = tmpdir / filename
    creator(file_path)

    content_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
    session_id = uuid4()
    artifact = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=str(file_path),
        content_hash=content_hash,
        action="probe_upload",
        agent_id="probe",
        session_id=session_id,
        metadata={"mime_type": mime_type, "original_filename": filename},
    )

    module_name, class_name = AGENT_CLASSES[agent_id]
    agent_cls = getattr(import_module(module_name), class_name)
    kwargs: dict[str, Any] = {}
    if agent_id in {"Agent1", "Agent2", "Agent3", "Agent4"}:
        kwargs["inter_agent_bus"] = InterAgentBus()

    agent = agent_cls(
        agent_id=agent_id,
        session_id=session_id,
        evidence_artifact=artifact,
        config=get_settings(),
        working_memory=await get_working_memory(),
        episodic_memory=await get_episodic_memory(),
        custody_logger=CustodyLogger(),
        evidence_store=EvidenceStore(),
        **kwargs,
    )

    expected_tasks = list(agent.task_decomposition)
    supported = bool(agent.supports_uploaded_file)
    try:
        findings = await asyncio.wait_for(agent.run_investigation(), timeout=240.0)
    finally:
        await shutdown_ml_workers()
    serialized = [f.model_dump(mode="json") for f in findings]
    tools = [((f.get("metadata") or {}).get("tool_name") or f.get("finding_type")) for f in serialized]
    verdicts = [
        {
            "tool": (f.get("metadata") or {}).get("tool_name") or f.get("finding_type"),
            "status": f.get("status"),
            "evidence_verdict": f.get("evidence_verdict"),
            "confidence": f.get("confidence_raw"),
            "summary": f.get("reasoning_summary"),
            "signals": {
                k: (f.get("metadata") or {}).get(k)
                for k in (
                    "verdict",
                    "status",
                    "anomaly_detected",
                    "inconsistency_detected",
                    "discontinuity_detected",
                    "vfi_artifact_detected",
                    "interpolation_artifact_detected",
                    "thumbnail_mismatch_detected",
                    "flagged_frames",
                    "inconsistencies",
                    "inconsistent_frame_count",
                    "anomaly_count",
                    "positive_frame_count",
                    "error",
                    "available",
                    "degraded",
                )
                if k in (f.get("metadata") or {})
            },
        }
        for f in serialized
    ]
    degraded = [
        {
            "tool": (f.get("metadata") or {}).get("tool_name"),
            "reason": (f.get("metadata") or {}).get("fallback_reason") or (f.get("metadata") or {}).get("note"),
        }
        for f in serialized
        if (f.get("metadata") or {}).get("degraded")
    ]
    incomplete = [
        {
            "tool": (f.get("metadata") or {}).get("tool_name"),
            "summary": f.get("reasoning_summary"),
        }
        for f in serialized
        if f.get("status") == "INCOMPLETE" or f.get("evidence_verdict") == "ERROR"
    ]

    result = {
        "agent_id": agent_id,
        "sample": sample,
        "mime_type": mime_type,
        "supported": supported,
        "expected_task_count": len(expected_tasks),
        "expected_tasks": expected_tasks,
        "finding_count": len(serialized),
        "tools": tools,
        "verdicts": verdicts,
        "missing_tool_tasks": [
            t for t in expected_tasks if not any(tool and tool in str(t).lower().replace("-", "_") for tool in tools)
        ],
        "degraded": degraded,
        "incomplete": incomplete,
        "agent_confidence": getattr(agent, "_agent_confidence", None),
        "agent_error_rate": getattr(agent, "_agent_error_rate", None),
        "synthesis": getattr(agent, "_agent_synthesis", None),
    }
    if include_findings:
        result["findings"] = serialized
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True, choices=sorted(AGENT_CLASSES))
    parser.add_argument("--sample", required=True, choices=sorted(SAMPLES))
    parser.add_argument("--include-findings", action="store_true")
    args = parser.parse_args()

    result = asyncio.run(_run_probe(args.agent, args.sample, include_findings=args.include_findings))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

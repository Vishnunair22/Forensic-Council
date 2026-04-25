from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import tempfile
from importlib import import_module
from pathlib import Path
from typing import Any
from uuid import uuid4

from probe_initial_agent import AGENT_CLASSES, SAMPLES

TOOL_ALIASES: dict[str, tuple[str, ...]] = {
    "neural_splicing": ("neural_splicing",),
    "neural_copy_move": ("neural_copy_move",),
    "diffusion_artifact_detector": ("diffusion_artifact_detector",),
    "f3_net_frequency": ("f3_net_frequency",),
    "anomaly_tracer": ("anomaly_tracer",),
    "gemini_deep_forensic": ("gemini_deep_forensic",),
    "prosody_analyze": ("prosody_analyze",),
    "audio_splice_detect": ("audio_splice_detect",),
    "enf_analysis": ("enf_analysis",),
    "background_noise_analysis": ("background_noise_analysis",),
    "voice_clone_deep_ensemble": ("voice_clone_deep_ensemble",),
    "anti_spoofing_deep_ensemble": ("anti_spoofing_deep_ensemble",),
    "secondary_classification": ("secondary_classification",),
    "scale_validation": ("scale_validation",),
    "adversarial_robustness_check": ("adversarial_robustness_check",),
    "lighting_consistency": ("lighting_consistency",),
    "optical_flow_analysis": ("optical_flow_analysis",),
    "interframe_forgery_detector": ("interframe_forgery_detector",),
    "frame_extraction": ("frame_extraction",),
    "face_swap_detection": ("face_swap_detection",),
    "deepfake_frequency_check": ("deepfake_frequency_check",),
    "rolling_shutter_validation": ("rolling_shutter_validation",),
    "compression_artifact_analysis": ("compression_artifact_analysis",),
    "provenance_chain_verify": ("provenance_chain_verify",),
    "metadata_anomaly_score": ("metadata_anomaly_score",),
    "camera_profile_match": ("camera_profile_match",),
}


def _task_tool_name(task: str) -> str | None:
    lowered = task.lower().replace("-", "_")
    for tool in TOOL_ALIASES:
        if tool in lowered:
            return tool
    return None


def _finding_tool(finding: dict[str, Any]) -> str:
    metadata = finding.get("metadata") or {}
    return str(metadata.get("tool_name") or finding.get("finding_type") or "")


def _valid_finding(finding: dict[str, Any]) -> bool:
    metadata = finding.get("metadata") or {}
    if finding.get("status") == "INCOMPLETE" or finding.get("evidence_verdict") == "ERROR":
        return False
    if metadata.get("error") and metadata.get("available") is False:
        return False
    return bool(finding.get("reasoning_summary") or metadata)


async def run_probe(agent_id: str, sample: str, include_findings: bool = False) -> dict[str, Any]:
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

    tmpdir = Path(tempfile.mkdtemp(prefix=f"probe_deep_{agent_id.lower()}_"))
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

    supported = bool(agent.supports_uploaded_file)
    initial_findings = []
    deep_findings = []
    try:
        if supported:
            initial_findings = await asyncio.wait_for(agent.run_investigation(), timeout=300.0)
            deep_findings = await asyncio.wait_for(agent.run_deep_investigation(), timeout=360.0)
    finally:
        await shutdown_ml_workers()

    serialized_initial = [f.model_dump(mode="json") for f in initial_findings]
    serialized_deep = [f.model_dump(mode="json") for f in deep_findings]
    deep_tasks = list(agent.deep_task_decomposition)
    expected_tools = [_task_tool_name(task) for task in deep_tasks]
    expected_tools = [tool for tool in expected_tools if tool]
    fired_tools = [_finding_tool(f) for f in serialized_deep]

    missing_tools = [
        tool
        for tool in expected_tools
        if not any(
            alias in fired for alias in TOOL_ALIASES.get(tool, (tool,)) for fired in fired_tools
        )
    ]
    invalid_findings = [
        {
            "tool": _finding_tool(f),
            "status": f.get("status"),
            "evidence_verdict": f.get("evidence_verdict"),
            "summary": f.get("reasoning_summary"),
            "metadata": {
                key: (f.get("metadata") or {}).get(key)
                for key in (
                    "error",
                    "available",
                    "degraded",
                    "fallback_reason",
                    "note",
                    "model_used",
                )
                if key in (f.get("metadata") or {})
            },
        }
        for f in serialized_deep
        if not _valid_finding(f)
    ]
    gemini = [
        {
            "tool": _finding_tool(f),
            "status": f.get("status"),
            "confidence": f.get("confidence_raw"),
            "summary": f.get("reasoning_summary"),
            "model_used": (f.get("metadata") or {}).get("model_used"),
            "error": (f.get("metadata") or {}).get("error"),
            "analysis_source": (f.get("metadata") or {}).get("analysis_source"),
        }
        for f in serialized_deep
        if _finding_tool(f) == "gemini_deep_forensic"
    ]

    result = {
        "agent_id": agent_id,
        "sample": sample,
        "mime_type": mime_type,
        "supported": supported,
        "initial_finding_count": len(serialized_initial),
        "deep_task_count": len(deep_tasks),
        "deep_tasks": deep_tasks,
        "expected_tools": expected_tools,
        "deep_finding_count": len(serialized_deep),
        "fired_tools": fired_tools,
        "missing_tools": missing_tools,
        "invalid_findings": invalid_findings,
        "gemini_findings": gemini,
        "agent_confidence": getattr(agent, "_agent_confidence", None),
        "agent_error_rate": getattr(agent, "_agent_error_rate", None),
        "synthesis": getattr(agent, "_agent_synthesis", None),
        "green": supported and bool(serialized_deep) and not missing_tools and not invalid_findings,
    }
    if include_findings:
        result["initial_findings"] = serialized_initial
        result["deep_findings"] = serialized_deep
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True, choices=sorted(AGENT_CLASSES))
    parser.add_argument("--sample", required=True, choices=sorted(SAMPLES))
    parser.add_argument("--include-findings", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(run_probe(args.agent, args.sample, args.include_findings))
    print(json.dumps(result, indent=2, default=str))
    if not result["green"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

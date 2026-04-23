from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from probe_initial_agent import SAMPLES


async def _resume_deep_when_paused(pipeline: Any, timeout_s: float = 360.0) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        if getattr(pipeline, "_awaiting_user_decision", False):
            pipeline.run_deep_analysis_flag = True
            pipeline.deep_analysis_decision_event.set()
            return True
        await asyncio.sleep(0.5)
    return False


def _phase_counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    initial = 0
    deep = 0
    incomplete = 0
    for finding in findings:
        metadata = finding.get("metadata") or {}
        if metadata.get("analysis_phase") == "deep":
            deep += 1
        else:
            initial += 1
        if finding.get("status") == "INCOMPLETE" or finding.get("evidence_verdict") == "ERROR":
            incomplete += 1
    return {"initial": initial, "deep": deep, "incomplete": incomplete}


async def _run_pipeline_probe(sample: str) -> dict[str, Any]:
    from orchestration.pipeline import ForensicCouncilPipeline

    filename, _mime_type, creator = SAMPLES[sample]
    with tempfile.TemporaryDirectory(prefix=f"pipeline_probe_{sample}_") as tmp:
        file_path = Path(tmp) / filename
        creator(file_path)

        pipeline = ForensicCouncilPipeline()
        session_id = uuid4()
        case_id = f"probe-{sample}-full"

        investigation = asyncio.create_task(
            pipeline.run_investigation(
                evidence_file_path=str(file_path),
                case_id=case_id,
                investigator_id="live_probe",
                original_filename=filename,
                session_id=session_id,
            )
        )
        resumed = await _resume_deep_when_paused(pipeline)
        report = await asyncio.wait_for(investigation, timeout=900.0)

    agent_counts = {
        agent_id: _phase_counts(findings)
        for agent_id, findings in report.per_agent_findings.items()
    }
    active_agents = [
        agent_id
        for agent_id, counts in agent_counts.items()
        if counts["initial"] or counts["deep"]
    ]
    report_findings = sum(
        counts["initial"] + counts["deep"] for counts in agent_counts.values()
    )
    deep_findings = sum(counts["deep"] for counts in agent_counts.values())
    incomplete_findings = sum(counts["incomplete"] for counts in agent_counts.values())
    llm_bypassed = any(
        "LLM synthesis bypassed" in str(flag)
        or "LLM synthesis timed out" in str(flag)
        for flag in report.degradation_flags
    )

    return {
        "sample": sample,
        "session_id": str(session_id),
        "case_id": case_id,
        "resumed_deep_analysis": resumed,
        "active_agents": active_agents,
        "agent_counts": agent_counts,
        "overall_verdict": report.overall_verdict,
        "overall_confidence": report.overall_confidence,
        "overall_error_rate": report.overall_error_rate,
        "manipulation_probability": report.manipulation_probability,
        "applicable_agent_count": report.applicable_agent_count,
        "total_findings": report_findings,
        "deep_findings": deep_findings,
        "incomplete_findings": incomplete_findings,
        "signed": bool(report.report_hash and report.cryptographic_signature),
        "report_hash_present": bool(report.report_hash),
        "signature_present": bool(report.cryptographic_signature),
        "executive_summary_chars": len(report.executive_summary or ""),
        "per_agent_analysis_count": len(report.per_agent_analysis or {}),
        "llm_narrative_used": bool(report.per_agent_analysis) and not llm_bypassed,
        "degradation_flags": report.degradation_flags,
        "analysis_coverage_note": report.analysis_coverage_note,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", required=True, choices=sorted(SAMPLES))
    args = parser.parse_args()

    result = asyncio.run(_run_pipeline_probe(args.sample))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

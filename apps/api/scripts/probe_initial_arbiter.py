from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any
from uuid import uuid4

from probe_initial_agent import _run_probe

SAMPLE_AGENTS = {
    "jpeg": ["Agent1", "Agent3", "Agent5"],
    "png": ["Agent1", "Agent3", "Agent5"],
    "tiff": ["Agent1", "Agent3", "Agent5"],
    "wav": ["Agent2", "Agent5"],
    "mp4": ["Agent2", "Agent3", "Agent4", "Agent5"],
}


async def _run_arbiter_probe(sample: str) -> dict[str, Any]:
    from agents.arbiter import CouncilArbiter
    from core.config import get_settings

    agent_results: dict[str, dict[str, Any]] = {}
    agent_summaries: dict[str, Any] = {}

    for agent_id in SAMPLE_AGENTS[sample]:
        probe = await _run_probe(agent_id, sample, include_findings=True)
        agent_summaries[agent_id] = {
            k: probe.get(k)
            for k in (
                "finding_count",
                "missing_tool_tasks",
                "degraded",
                "incomplete",
                "agent_confidence",
                "agent_error_rate",
            )
        }
        agent_results[agent_id] = {"findings": probe["findings"]}

    arbiter = CouncilArbiter(session_id=uuid4(), config=get_settings())
    report = await asyncio.wait_for(
        arbiter.deliberate(agent_results, case_id=f"probe-{sample}-initial", use_llm=False),
        timeout=180.0,
    )

    return {
        "sample": sample,
        "agents": list(agent_results),
        "agent_summaries": agent_summaries,
        "overall_verdict": report.overall_verdict,
        "overall_confidence": report.overall_confidence,
        "overall_error_rate": report.overall_error_rate,
        "manipulation_probability": report.manipulation_probability,
        "applicable_agent_count": report.applicable_agent_count,
        "incomplete_count": len(report.incomplete_findings),
        "contested_count": len(report.contested_findings),
        "degradation_flags": report.degradation_flags,
        "analysis_coverage_note": report.analysis_coverage_note,
        "per_agent_metrics": report.per_agent_metrics,
        "per_agent_summary": report.per_agent_summary,
        "signed": bool(report.cryptographic_signature and report.report_hash),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", required=True, choices=sorted(SAMPLE_AGENTS))
    args = parser.parse_args()

    result = asyncio.run(_run_arbiter_probe(args.sample))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

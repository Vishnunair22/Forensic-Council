"""
Pipeline Enrichment
===================

Post-deliberation report enrichment: metadata collection, custody verification,
visual profile provenance recording, and degradation flag propagation.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from uuid import UUID

from core.structured_logging import get_logger

if TYPE_CHECKING:
    from orchestration.agent_factory import AgentLoopResult

logger = get_logger(__name__)


async def enrich_report(
    *,
    pipeline: Any,
    report: Any,
    session_id: UUID,
    artifact: Any,
    agent_results: list[AgentLoopResult],
) -> None:
    """Enrich the report with metadata, logs, custody checks, and real degradation flags."""
    _detect_visual_profile_provenance(pipeline, report)

    tasks = [
        _collect_case_linking_flags(pipeline, session_id, artifact),
        _get_custody_log(pipeline, session_id),
        _get_version_trees(pipeline, artifact.artifact_id),
    ]
    results = await asyncio.gather(
        *[asyncio.wait_for(t, timeout=15.0) for t in tasks],
        return_exceptions=True,
    )

    report.case_linking_flags = results[0] if not isinstance(results[0], BaseException) else []
    report.chain_of_custody_log = results[1] if not isinstance(results[1], BaseException) else []
    report.evidence_version_trees = results[2] if not isinstance(results[2], BaseException) else []

    if any(isinstance(r, (Exception, asyncio.TimeoutError)) for r in results):
        logger.warning("One or more enrichment tasks failed or timed out")

    report.react_chains = {r.agent_id: r.react_chain for r in agent_results if r.error is None}
    report.self_reflection_outputs = {
        r.agent_id: r.reflection_report for r in agent_results if r.error is None
    }

    await _verify_custody_integrity(pipeline, session_id)

    if pipeline._degradation_flags:
        report.degradation_flags.extend(pipeline._degradation_flags)


def _detect_visual_profile_provenance(pipeline: Any, report: Any) -> None:
    """Record visual provider provenance without treating provider choice as degradation."""
    all_findings = []
    for agent_findings in getattr(report, "per_agent_findings", {}).values():
        all_findings.extend(agent_findings)

    visual_findings = [
        f
        for f in all_findings
        if isinstance(f, dict)
        and (
            f.get("finding_type") == "visual_evidence_profile"
            or f.get("metadata", {}).get("tool_name") == "visual_evidence_profile"
        )
    ]

    if not visual_findings:
        pipeline._degradation_flags.append(
            "No visual evidence profile was recorded; downstream agents may lack visual grounding."
        )
        return

    providers = []
    for finding in visual_findings:
        meta = finding.get("metadata", {}) or {}
        provider = meta.get("provider_used") or meta.get("analysis_source")
        if provider:
            providers.append(str(provider))

    if providers:
        note = f"Visual profile provider(s): {', '.join(sorted(set(providers)))}."
        existing = getattr(report, "analysis_coverage_note", "") or ""
        if note not in existing:
            report.analysis_coverage_note = f"{existing} {note}".strip()


async def _verify_custody_integrity(pipeline: Any, session_id: UUID) -> None:
    """Verify chain-of-custody integrity and flag any breaks."""
    custody_logger = pipeline.custody_logger
    if not (custody_logger and getattr(custody_logger, "_postgres", None)):
        pipeline._degradation_flags.append(
            "Chain-of-custody verification skipped - DB unavailable."
        )
        return

    try:
        chain_report = await asyncio.wait_for(custody_logger.verify_chain(session_id), timeout=15.0)
        if not chain_report.valid:
            pipeline._degradation_flags.append(
                f"CRITICAL: Custody integrity FAILED (entry {chain_report.broken_at}). "
                "Report may be tampered."
            )
    except Exception as e:
        logger.warning("Custody verification failed", error=str(e))
        pipeline._degradation_flags.append(f"Custody verification could not complete: {e}")


async def _collect_case_linking_flags(
    pipeline: Any,
    session_id: UUID,
    evidence_artifact: Any,
) -> list[dict[str, Any]]:
    """Collect case linking flags from episodic memory."""
    flags: list[dict[str, Any]] = []
    try:
        entries = await pipeline.episodic_memory.get_by_session(session_id)
        for entry in entries:
            if entry.signature_type and "LINK" in entry.signature_type.value:
                flags.append(
                    {
                        "flag_type": entry.signature_type.value,
                        "description": entry.description,
                        "artifact_id": str(entry.artifact_id),
                    }
                )
    except Exception as e:
        logger.warning("Failed to collect case linking flags", error=str(e))
    return flags


async def _get_custody_log(pipeline: Any, session_id: UUID) -> list[dict[str, Any]]:
    """Get chain-of-custody log for session."""
    try:
        chain = await pipeline.custody_logger.get_session_chain(session_id)
        return [
            {
                "entry_id": str(e.entry_id),
                "entry_type": e.entry_type.value,
                "agent_id": e.agent_id,
                "timestamp_utc": e.timestamp_utc.isoformat(),
                "content_hash": e.content_hash,
            }
            for e in chain
        ]
    except Exception as e:
        logger.warning("Failed to get custody log", error=str(e))
        return []


async def _get_version_trees(pipeline: Any, artifact_id: UUID) -> list[dict[str, Any]]:
    """Get evidence version trees."""
    try:
        tree = await pipeline.evidence_store.get_version_tree(artifact_id)
        if not tree:
            return []
        versions = tree.get_all_artifacts()
        return [
            {
                "artifact_id": str(v.artifact_id),
                "parent_id": str(v.parent_id) if v.parent_id else None,
                "content_hash": v.content_hash,
                "created_at": v.timestamp_utc.isoformat(),
            }
            for v in versions
        ]
    except Exception as e:
        logger.warning("Failed to get version trees", error=str(e))
        return []

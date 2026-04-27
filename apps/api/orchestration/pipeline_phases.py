"""
Pipeline Phases
===============

Concurrent agent execution and HITL deep-analysis gate.
Extracted from pipeline.py to keep the orchestrator file under 400 lines.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any
from uuid import UUID

from core.agents import AgentID
from core.structured_logging import get_logger
from orchestration.agent_factory import AgentLoopResult, _serialize_react_chain

if TYPE_CHECKING:
    from orchestration.pipeline import ForensicCouncilPipeline

logger = get_logger(__name__)


async def run_agents_concurrent(
    pipeline: "ForensicCouncilPipeline",
    evidence_artifact,
    session_id: UUID,
) -> list[AgentLoopResult]:
    """
    Run all specialist agents in two phases:
      Phase 1 — concurrent initial passes
      HITL gate — await analyst decision
      Phase 2 — concurrent deep passes (if approved)
    """
    from core.agent_registry import get_agent_registry
    from core.observability import get_tracer

    _tracer = get_tracer("forensic-council.pipeline")

    with _tracer.start_as_current_span("pipeline.run_agents_concurrent") as span:
        span.set_attribute("session_id", str(session_id))

    registry = get_agent_registry()

    # --- Broadcast helper ---------------------------------------------------

    async def _broadcast_agent_status(
        aid: str, status: str, message: str, findings=None, error=None, agent_inst=None
    ):
        try:
            from api.routes._session_state import AGENT_NAMES, broadcast_update
            from api.schemas import BriefUpdate
            from core.severity import assign_severity_tier

            aname = AGENT_NAMES.get(aid, aid)
            preview = []
            synthesis = (
                getattr(agent_inst, "_agent_synthesis", None) if agent_inst is not None else None
            )
            if findings:
                for f in findings:
                    m = (
                        f.metadata
                        if hasattr(f, "metadata")
                        else f.get("metadata", {}) if isinstance(f, dict) else {}
                    )
                    tool = m.get("tool_name") or (
                        f.finding_type if hasattr(f, "finding_type") else f.get("finding_type")
                    )
                    s = (
                        f.reasoning_summary
                        if hasattr(f, "reasoning_summary")
                        else f.get("reasoning_summary", "")
                    )
                    if not s:
                        continue
                    sev = assign_severity_tier(f)
                    evidence_verdict = str(
                        getattr(f, "evidence_verdict", "")
                        if hasattr(f, "evidence_verdict")
                        else f.get("evidence_verdict", "")
                    ).upper()
                    finding_status = str(
                        getattr(f, "status", "")
                        if hasattr(f, "status")
                        else f.get("status", "")
                    ).upper()
                    if evidence_verdict == "ERROR" or finding_status == "INCOMPLETE":
                        tv = "NEEDS_REVIEW"
                    elif evidence_verdict in (
                        "POSITIVE", "TAMPERED", "SUSPICIOUS", "MANIPULATED",
                    ) or sev in ("CRITICAL", "HIGH", "MEDIUM"):
                        tv = "FLAGGED"
                    elif (
                        evidence_verdict == "NOT_APPLICABLE"
                        or finding_status == "NOT_APPLICABLE"
                    ):
                        tv = "NOT_APPLICABLE"
                    else:
                        tv = "CLEAN"
                    preview.append({
                        "tool": tool,
                        "summary": s[:320],
                        "severity": sev,
                        "verdict": tv,
                        "key_signal": m.get("section_key_signal") or m.get("raw_tool_summary") or "",
                        "confidence": (
                            getattr(f, "confidence_raw", None)
                            if hasattr(f, "confidence_raw")
                            else f.get("confidence_raw")
                        ),
                        "section": m.get("section") or "",
                    })
            if isinstance(synthesis, dict) and not preview:
                summary = str(synthesis.get("narrative_summary") or "").strip()
                if summary:
                    preview.append({
                        "tool": "agent_synthesis",
                        "summary": summary[:420],
                        "severity": "LOW",
                        "verdict": str(synthesis.get("verdict") or "INCONCLUSIVE"),
                    })

            await broadcast_update(
                str(session_id),
                BriefUpdate(
                    type="AGENT_COMPLETE"
                    if status in ("complete", "error", "skipped")
                    else "AGENT_UPDATE",
                    session_id=str(session_id),
                    agent_id=aid,
                    agent_name=aname,
                    message=message,
                    data={
                        "status": status,
                        "findings_count": len(findings) if findings else 0,
                        "error": error,
                        "findings_preview": preview,
                        "agent_verdict": synthesis.get("verdict") if isinstance(synthesis, dict) else None,
                        "tool_error_rate": getattr(agent_inst, "_agent_error_rate", None) if agent_inst else None,
                        "tools_ran": getattr(agent_inst, "_tool_success_count", None) if agent_inst else None,
                        "tools_failed": getattr(agent_inst, "_tool_error_count", None) if agent_inst else None,
                        "section_flags": synthesis.get("sections") if isinstance(synthesis, dict) else None,
                    },
                ),
            )
        except Exception as exc:
            logger.debug("Agent status broadcast failed", agent_id=aid, error=str(exc))

    # --- Phase 1: Initialize agents and run initial passes ------------------

    agent_instances = []
    for aid in registry.get_all_agent_ids():
        extra = {}
        if aid in (AgentID.AGENT2.value, AgentID.AGENT3.value, AgentID.AGENT4.value):
            extra = {"inter_agent_bus": pipeline.inter_agent_bus}

        cls = registry.get_agent_class(aid)
        kwargs = {
            "agent_id": aid,
            "session_id": session_id,
            "evidence_artifact": evidence_artifact,
            "config": pipeline.config,
            "working_memory": pipeline.working_memory,
            "episodic_memory": pipeline.episodic_memory,
            "custody_logger": pipeline.custody_logger,
            "evidence_store": pipeline.evidence_store,
            "heavy_tool_semaphore": pipeline.heavy_tool_semaphore,
            **extra,
        }
        inst = cls(**kwargs)
        if pipeline.inter_agent_bus is not None:
            pipeline.inter_agent_bus.register_agent(aid, inst)

        supported = inst.supports_uploaded_file
        agent_instances.append((inst, supported))

        if not supported:
            await _broadcast_agent_status(
                aid, "skipped", f"{aid} bypassed: file type not supported.",
                error="Unsupported file type.", agent_inst=inst,
            )
        else:
            await _broadcast_agent_status(
                aid, "running", f"Agent {aid} active. Initializing scan...", agent_inst=inst,
            )

    applicable_ids = [
        aid
        for (inst, supported), aid in zip(agent_instances, registry.get_all_agent_ids(), strict=True)
        if supported
    ]
    if pipeline.signal_bus:
        pipeline.signal_bus.update_applicable_agents(applicable_ids)

    async def _run_one(agent, aid: str, supported: bool):
        if not supported:
            return agent, [], "unsupported"
        try:
            logger.info(f"Running {aid} initial investigation")
            initial_findings = await asyncio.wait_for(
                agent.run_investigation(),
                timeout=min(float(pipeline.config.investigation_timeout), 480.0),
            )
            if pipeline.signal_bus:
                await pipeline.signal_bus.signal_ready(aid, initial_findings)
            await _broadcast_agent_status(
                aid, "complete", f"{aid} initial analysis complete.",
                findings=initial_findings, agent_inst=agent,
            )
            return agent, initial_findings, "complete"
        except Exception as e:
            logger.error(f"{aid} initial pass failed", error=str(e))
            findings = list(getattr(agent, "_findings", []) or [])
            if pipeline.signal_bus:
                await pipeline.signal_bus.signal_failure(aid)
            await _broadcast_agent_status(
                aid, "error", f"{aid} error: {e}",
                findings=findings, error=str(e), agent_inst=agent,
            )
            return agent, findings, "error"

    raw_initial = await asyncio.gather(
        *[
            _run_one(inst, aid, supported)
            for (inst, supported), aid in zip(
                agent_instances, registry.get_all_agent_ids(), strict=True
            )
        ],
        return_exceptions=True,
    )

    agent_map: dict[str, tuple] = {}
    for i, aid in enumerate(registry.get_all_agent_ids()):
        res = (
            raw_initial[i]
            if not isinstance(raw_initial[i], BaseException)
            else (None, [], "error")
        )
        agent_map[aid] = res

    initial_results = [
        AgentLoopResult(
            agent_id=aid,
            findings=[
                f.model_dump(mode="json") if hasattr(f, "model_dump") else f for f in findings
            ],
            reflection_report=(
                getattr(agent, "_reflection_report", None).model_dump(mode="json")
                if getattr(agent, "_reflection_report", None)
                else {}
            ),
            react_chain=_serialize_react_chain(getattr(agent, "_react_chain", [])),
            agent_active=status != "unsupported",
            supports_file_type=status != "unsupported",
        )
        for aid, (agent, findings, status) in agent_map.items()
    ]

    # --- HITL Gate ----------------------------------------------------------

    if not await _await_deep_analysis_decision(pipeline, session_id):
        logger.info("Deep analysis skipped by analyst decision", session_id=str(session_id))
        return initial_results

    # --- Phase 2: Deep passes with early context sync ----------------------

    context_event = asyncio.Event()
    context_injected: set[str] = set()
    producer_id = AgentID.AGENT1.value

    def _broadcast_context(producer_finding: Any):
        try:
            meta = {}
            if hasattr(producer_finding, "metadata"):
                meta = (
                    producer_finding.metadata
                    if isinstance(producer_finding.metadata, dict)
                    else {}
                )
            elif isinstance(producer_finding, dict):
                meta = producer_finding.get("metadata", {}) or producer_finding

            if meta:
                for aid, (agent_inst, _, _) in agent_map.items():
                    if agent_inst is None or aid in context_injected or aid == producer_id:
                        continue
                    if hasattr(agent_inst, "inject_agent1_context"):
                        agent_inst.inject_agent1_context(meta)
                        context_injected.add(aid)
                logger.info(f"Early context broadcast from {producer_id} triggered")
            context_event.set()
        except Exception as _cb_err:
            logger.warning(f"Early signal callback failed: {_cb_err}")

    producer_inst = agent_map.get(producer_id, (None, None, "error"))[0]
    if producer_inst:
        producer_inst._gemini_signal_callback = _broadcast_context

    for _aid, (agent_inst, _, _) in agent_map.items():
        if agent_inst and hasattr(agent_inst, "_agent1_context_event"):
            agent_inst._agent1_context_event = context_event

    async def _run_deep_with_fallback(aid: str) -> AgentLoopResult:
        a_inst, a_init, a_status = agent_map[aid]
        a_supported = a_status != "unsupported"
        if not a_supported:
            if aid == producer_id:
                context_event.set()
            return AgentLoopResult(
                agent_id=aid, findings=[], reflection_report={}, react_chain=[],
                agent_active=False, supports_file_type=False,
            )

        try:
            await _broadcast_agent_status(aid, "running", f"Running {aid} deep pass...")
            result = await _run_agent_deep_only(pipeline, a_inst, aid, a_init, a_supported)

            if result.error:
                await _broadcast_agent_status(
                    aid, "error", f"{aid} error: {result.error}",
                    error=result.error, agent_inst=a_inst,
                )
            else:
                await _broadcast_agent_status(
                    aid, "complete", f"{aid} analysis complete.",
                    findings=result.findings, agent_inst=a_inst,
                )

            if aid == producer_id:
                try:
                    gemini_res = {}
                    for f in result.findings or []:
                        if (
                            isinstance(f, dict)
                            and f.get("metadata", {}).get("tool_name") == "gemini_deep_forensic"
                        ):
                            gemini_res = f.get("metadata", {})
                            break
                    if gemini_res:
                        _broadcast_context(gemini_res)
                finally:
                    context_event.set()

            return result
        except Exception:
            if aid == producer_id:
                context_event.set()
            raise

    raw_deep_all = await asyncio.gather(
        *[_run_deep_with_fallback(aid) for aid in agent_map.keys()],
        return_exceptions=True,
    )

    agent_ids_deep = registry.get_all_agent_ids()
    results: list[AgentLoopResult] = []
    for i, r in enumerate(raw_deep_all):
        if isinstance(r, BaseException):
            logger.error(
                f"Agent {agent_ids_deep[i]} deep pass raised unexpectedly",
                error=str(r),
                exc_info=r,
            )
            results.append(AgentLoopResult(
                agent_id=agent_ids_deep[i],
                findings=[], reflection_report={}, react_chain=[],
                error=str(r), agent_active=False,
            ))
        else:
            results.append(r)

    active_agents = [r.agent_id for r in results if r.agent_active]
    skipped_agents = [r.agent_id for r in results if not r.supports_file_type]
    logger.info("Agent execution summary", active_agents=active_agents, skipped_agents=skipped_agents)

    for aid in registry.get_all_agent_ids():
        if pipeline.inter_agent_bus is not None:
            pipeline.inter_agent_bus.unregister_agent(aid)

    return results


async def _run_agent_deep_only(
    pipeline: "ForensicCouncilPipeline",
    agent,
    agent_id: str,
    initial_findings: list,
    supports_file: bool,
) -> AgentLoopResult:
    """Run the deep investigation pass on an already-initialized agent."""
    from core.observability import get_tracer

    _tracer = get_tracer("forensic-council.pipeline")

    if agent is None:
        return AgentLoopResult(
            agent_id=agent_id, findings=[], reflection_report={}, react_chain=[],
            agent_active=False, supports_file_type=supports_file, error="Initial pass failed",
        )
    if not supports_file:
        return AgentLoopResult(
            agent_id=agent_id, findings=[], reflection_report={}, react_chain=[],
            agent_active=False, supports_file_type=False,
        )

    with _tracer.start_as_current_span(f"agent.{agent_id}.deep_pass") as span:
        span.set_attribute("agent_id", agent_id)
        try:
            initial_count = len(initial_findings)
            logger.info(f"Running {agent_id} deep investigation")
            deep_timeout = min(float(pipeline.config.investigation_timeout), 600.0)
            await asyncio.wait_for(
                agent.run_deep_investigation(),
                timeout=deep_timeout,
            )
            all_findings = getattr(agent, "_findings", initial_findings)
            deep_count = max(0, len(all_findings) - initial_count)
            span.set_attribute("deep_finding_count", deep_count)
            span.set_attribute("total_finding_count", len(all_findings))
            return AgentLoopResult(
                agent_id=agent_id,
                findings=[f.model_dump(mode="json") for f in all_findings],
                reflection_report=(
                    getattr(agent, "_reflection_report", None).model_dump(mode="json")
                    if getattr(agent, "_reflection_report", None)
                    else {}
                ),
                react_chain=_serialize_react_chain(getattr(agent, "_react_chain", [])),
                agent_active=True,
                supports_file_type=True,
                deep_findings_count=max(0, deep_count),
            )
        except Exception as e:
            logger.error(f"{agent_id} deep pass failed", error=str(e), exc_info=True)
            return AgentLoopResult(
                agent_id=agent_id,
                findings=[f.model_dump(mode="json") for f in initial_findings],
                reflection_report={},
                react_chain=_serialize_react_chain(getattr(agent, "_react_chain", [])),
                agent_active=True,
                supports_file_type=True,
                error=str(e),
            )


async def _await_deep_analysis_decision(
    pipeline: "ForensicCouncilPipeline",
    session_id: UUID,
) -> bool:
    """
    Pause pipeline and poll Redis/event for analyst decision.
    Returns True if deep analysis should proceed, False to skip.
    """
    from api.routes._session_state import (
        broadcast_update,
        get_active_pipeline_metadata,
        set_active_pipeline_metadata,
    )
    from api.schemas import BriefUpdate
    from core.persistence.redis_client import get_redis_client

    decision_key = f"forensic:session:resume_decision:{session_id}"
    redis = await get_redis_client()
    await redis.delete(decision_key)

    pipeline._awaiting_user_decision = True
    pipeline.deep_analysis_decision_event.clear()
    pipeline.run_deep_analysis_flag = False

    existing_metadata = await get_active_pipeline_metadata(str(session_id)) or {}
    await set_active_pipeline_metadata(
        str(session_id),
        {
            **existing_metadata,
            "status": "awaiting_decision",
            "brief": "Initial analysis complete. Awaiting analyst decision.",
            "awaiting_decision": True,
        },
    )
    await broadcast_update(
        str(session_id),
        BriefUpdate(
            type="PIPELINE_PAUSED",
            session_id=str(session_id),
            message="Initial analysis complete. Awaiting analyst decision.",
            data={"status": "awaiting_decision", "initial_results_ready": True},
        ),
    )

    try:
        active_redis = pipeline._redis or await get_redis_client()
        timeout = pipeline.config.hitl_decision_timeout or 3600
        start_time = time.perf_counter()

        while (time.perf_counter() - start_time) < timeout:
            try:
                raw_decision = await active_redis.get(decision_key)
                if raw_decision:
                    decision = json.loads(raw_decision)
                    if isinstance(decision, dict):
                        pipeline.run_deep_analysis_flag = bool(decision.get("deep_analysis"))
                        logger.info(
                            "Analyst decision received via Redis",
                            session_id=str(session_id),
                            deep_analysis=pipeline.run_deep_analysis_flag,
                        )
                        return pipeline.run_deep_analysis_flag
            except Exception as poll_err:
                logger.debug("Decision polling flicker", error=str(poll_err))

            if pipeline.deep_analysis_decision_event.is_set():
                logger.info(
                    "Analyst decision received via internal event",
                    session_id=str(session_id),
                )
                return bool(pipeline.run_deep_analysis_flag)

            await asyncio.sleep(2.0)

        logger.warning(
            "HITL decision timed out; defaulting to skip deep analysis",
            session_id=str(session_id),
            timeout_seconds=timeout,
        )
        return False
    finally:
        pipeline._awaiting_user_decision = False
        try:
            await redis.delete(decision_key)
        except Exception as _e:
            logger.debug("Decision key cleanup skipped (Redis may be unavailable)", error=str(_e))

import asyncio
from asyncio import TimeoutError
import hashlib
import os
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from api.constants import _PIPELINE_TASK_PHRASES
from api.routes._session_state import (
    AGENT_NAMES,
    _active_pipelines,
    _final_reports,
    broadcast_update,
    get_session_websockets,
    set_active_pipeline_metadata,
    set_final_report,
)
from api.routes.metrics import (
    increment_investigations_completed,
    increment_investigations_failed,
    increment_investigations_started,
)
from api.schemas import (
    BriefUpdate,
)
from core.config import get_settings
from core.severity import assign_severity_tier
from core.structured_logging import get_logger
from orchestration.pipeline import AgentLoopResult, ForensicCouncilPipeline

logger = get_logger(__name__)
settings = get_settings()


def _assign_severity_tier(f: Any) -> str:
    """Assign INFO/LOW/MEDIUM/HIGH/CRITICAL to a finding. Uses shared logic."""
    return assign_severity_tier(f)


async def _wrap_pipeline_with_broadcasts(
    pipeline: ForensicCouncilPipeline,
    session_id: str,
    evidence_file_path: str,
    case_id: str,
    investigator_id: str,
    original_filename: str | None = None,
):
    """
    Wrap the pipeline execution to broadcast per-agent WebSocket updates.
    """
    ws_session_id = session_id

    # Hook custody logger for real-time thinking updates
    def instrument_logger(logger_obj):
        original_log_entry = logger_obj.log_entry

        async def instrumented_log_entry(**kwargs):
            result = await original_log_entry(**kwargs)

            entry_type = kwargs.get("entry_type")
            content = kwargs.get("content", {})
            raw_agent_id = kwargs.get("agent_id")
            agent_id = raw_agent_id if isinstance(raw_agent_id, str) else "system"

            type_val = getattr(entry_type, "value", str(entry_type))

            if type_val == "HITL_CHECKPOINT" and isinstance(content, dict):
                agent_name = AGENT_NAMES.get(agent_id, agent_id)
                await broadcast_update(
                    ws_session_id,
                    BriefUpdate(
                        type="HITL_CHECKPOINT",
                        session_id=ws_session_id,
                        agent_id=agent_id,
                        agent_name=agent_name,
                        message=f"🚨 HITL Checkpoint: {content.get('reason', 'Review required')}",
                        data={
                            "status": "paused",
                            "checkpoint": {
                                "id": content.get("checkpoint_id"),
                                "agent_id": agent_id,
                                "reason": content.get("reason"),
                                "brief": content.get("brief"),
                            },
                        },
                    ),
                )
            elif type_val in ("THOUGHT", "ACTION") and isinstance(content, dict):
                if content.get("action") == "session_start":
                    return result

                agent_name = AGENT_NAMES.get(agent_id, agent_id)

                if type_val == "ACTION" and content.get("tool_name"):
                    tool_label = content["tool_name"].replace("_", " ").title()
                    thinking_text = f"Calling {tool_label}..."
                else:
                    thinking_text = content.get("content", "Analyzing...")

                await broadcast_update(
                    ws_session_id,
                    BriefUpdate(
                        type="AGENT_UPDATE",
                        session_id=ws_session_id,
                        agent_id=agent_id,
                        agent_name=agent_name,
                        message=thinking_text,
                        data={"status": "running", "thinking": thinking_text},
                    ),
                )
            return result

        logger_obj.log_entry = instrumented_log_entry

    if pipeline.custody_logger:
        instrument_logger(pipeline.custody_logger)

    # Initialise arbiter step tracking on the pipeline so getArbiterStatus can read it
    pipeline._arbiter_step = ""

    async def instrumented_run(evidence_artifact, session_id=None, *args, **kwargs):
        """Run all agents concurrently via asyncio.gather with real-time WebSocket updates."""

        mime = evidence_artifact.metadata.get("mime_type", "application/octet-stream")

        from agents.agent1_image import Agent1Image
        from agents.agent2_audio import Agent2Audio
        from agents.agent3_object import Agent3Object
        from agents.agent4_video import Agent4Video
        from agents.agent5_metadata import Agent5Metadata
        from core.mime_registry import MimeRegistry
        from core.working_memory import WorkingMemory

        agent_configs = [
            (
                "Agent1",
                "Image Forensics",
                Agent1Image,
                "🔬 Launching ELA engine — scanning for pixel-level anomalies…",
            ),
            (
                "Agent2",
                "Audio Forensics",
                Agent2Audio,
                "🎙️ Establishing voice-count baseline with diarization…",
            ),
            (
                "Agent3",
                "Object Detection",
                Agent3Object,
                "👁️ Loading YOLO model — running primary object detection…",
            ),
            (
                "Agent4",
                "Video Forensics",
                Agent4Video,
                "🎬 Starting optical flow analysis — building temporal heatmap…",
            ),
            (
                "Agent5",
                "Metadata Forensics",
                Agent5Metadata,
                "📋 Extracting EXIF fields — checking for mandatory field gaps…",
            ),
        ]

        for _aid, _aname, _, _ in agent_configs:
            await broadcast_update(
                ws_session_id,
                BriefUpdate(
                    type="AGENT_UPDATE",
                    session_id=ws_session_id,
                    agent_id=_aid,
                    agent_name=_aname,
                    message=f"{_aname} queued — waiting for turn…",
                    data={
                        "status": "queued",
                        "thinking": f"{_aname} queued — waiting for turn…",
                    },
                ),
            )

        def _humanise_task(task_desc: str) -> str:
            """Map a raw working-memory task description to a friendly action string."""
            low = task_desc.lower()
            for keyword, phrase in _PIPELINE_TASK_PHRASES.items():
                if keyword in low:
                    return phrase
            return task_desc[:1].upper() + task_desc[1:] + "…"

        _pipeline_completed: list[int] = [0]
        _total_supported = sum(
            1
            for _id, _, _, _ in agent_configs
            if MimeRegistry.is_supported(_id, mime)
        )

        async def make_heartbeat(
            agent_id: str,
            agent_name: str,
            target_memory: WorkingMemory,
            done_event: asyncio.Event,
            deep_namespace: str | None = None,
        ):
            """Stream live working-memory progress to the WebSocket client."""
            def _coerce_session_uuid(value: Any) -> UUID:
                if isinstance(value, UUID):
                    return value
                if isinstance(value, str):
                    return UUID(value)
                artifact_id = getattr(value, "artifact_id", None)
                if isinstance(artifact_id, UUID):
                    return artifact_id
                if isinstance(artifact_id, str):
                    return UUID(artifact_id)
                raise ValueError("Unable to determine working-memory session UUID")

            last_thinking = ""
            last_done = -1
            last_broadcast_time = 0.0
            task_start_time = 0.0
            _CYCLING_SUBTEXTS = [
                "analysing evidence", "cross-referencing patterns", "evaluating signals",
                "processing data", "running forensic checks", "validating results",
                "scanning for anomalies", "building analysis",
            ]
            _cycle_index = 0
            wm_agent_id = deep_namespace if deep_namespace else agent_id
            broadcast_id = agent_id
            phase_label = "deep" if deep_namespace else "initial"

            while not done_event.is_set():
                try:
                    await asyncio.wait_for(done_event.wait(), timeout=0.2)
                    break
                except TimeoutError:
                    pass
                try:
                    _wm_session = _coerce_session_uuid(
                        session_id if session_id else evidence_artifact
                    )
                    wm_state = await target_memory.get_state(
                        session_id=_wm_session,
                        agent_id=wm_agent_id,
                    )
                    if not wm_state:
                        await broadcast_update(
                            ws_session_id,
                            BriefUpdate(
                                type="AGENT_UPDATE",
                                session_id=ws_session_id,
                                agent_id=broadcast_id,
                                agent_name=agent_name,
                                message=f"⏳ {agent_name} — loading ML models…",
                                data={
                                    "status": "running",
                                    "phase": phase_label,
                                    "thinking": f"⏳ {agent_name} — loading ML models…",
                                },
                            ),
                        )
                        await asyncio.sleep(0.1)
                        continue
                    tasks_list = wm_state.tasks
                    completed_t = [t for t in tasks_list if t.status.value == "COMPLETE"]
                    in_progress_t = [t for t in tasks_list if t.status.value == "IN_PROGRESS"]
                    total = len(tasks_list)
                    done = len(completed_t)
                    thinking = ""
                    last_error = getattr(wm_state, "last_tool_error", None)
                    if last_error:
                        thinking = f"⚠️ {last_error}"
                        try:
                            await target_memory.update_state(
                                session_id=_wm_session,
                                agent_id=wm_agent_id,
                                updates={"last_tool_error": None},
                            )
                        except Exception:
                            logger.debug("Working memory update failed", exc_info=True)
                    elif in_progress_t:
                        task_obj = in_progress_t[0]
                        friendly = _humanise_task(task_obj.description)
                        sub_info = getattr(task_obj, "sub_task_info", None)
                        if sub_info:
                            friendly = f"{friendly.rstrip('…')} [{sub_info}]"
                        progress_frac = f" ({done + 1}/{total})" if total > 0 else ""
                        now = time.monotonic()
                        if task_start_time == 0 or friendly != last_thinking:
                            task_start_time = now
                        elapsed_s = int(now - task_start_time)
                        if elapsed_s >= 6:
                            subtext = _CYCLING_SUBTEXTS[_cycle_index % len(_CYCLING_SUBTEXTS)]
                            _cycle_index += 1
                            thinking = f"{friendly.rstrip('…')}{progress_frac} — {subtext} ({elapsed_s}s)…"
                        else:
                            thinking = friendly.rstrip("…") + progress_frac + "…"
                    elif done > 0 and done >= total and total > 0:
                        thinking = "✅ Finalising findings…"
                    elif done > 0:
                        thinking = f"🔄 Cross-validating results… ({done}/{total} tasks complete)"
                    elif total > 0:
                        thinking = f"⚙️ Initialising {total} analysis tasks…"
                    else:
                        thinking = ""
                    now = time.monotonic()
                    if thinking and ((thinking != last_thinking) or (done != last_done) or (now - last_broadcast_time >= 4.0)):
                        last_thinking = thinking
                        last_done = done
                        last_broadcast_time = now
                        await broadcast_update(
                            ws_session_id,
                            BriefUpdate(
                                type="AGENT_UPDATE",
                                session_id=ws_session_id,
                                agent_id=broadcast_id,
                                agent_name=agent_name,
                                message=thinking,
                                data={
                                    "status": "running", "phase": phase_label,
                                    "thinking": thinking, "tools_done": done, "tools_total": total,
                                },
                            ),
                        )
                except Exception as e:
                    logger.debug("Heartbeat error", error=str(e))

        async def run_single_agent(agent_id, agent_name, AgentClass, thinking_phrase):
            if not MimeRegistry.is_supported(agent_id, mime):
                file_cat = "image" if mime.startswith("image/") else "video" if mime.startswith("video/") else "audio" if mime.startswith("audio/") else (mime.split("/")[-1] if "/" in mime else "this file type")
                skip_msg = f"{agent_name} is not applicable for {file_cat} files. Skipping."
                await broadcast_update(ws_session_id, BriefUpdate(
                    type="AGENT_COMPLETE", session_id=ws_session_id, agent_id=agent_id, agent_name=agent_name,
                    message=skip_msg, data={"status": "skipped", "confidence": 0.0, "findings_count": 0, "error": f"Not applicable for {file_cat} files"}
                ))
                return AgentLoopResult(agent_id=agent_id, findings=[], reflection_report={}, react_chain=[]), None

            await broadcast_update(ws_session_id, BriefUpdate(
                type="AGENT_UPDATE", session_id=ws_session_id, agent_id=agent_id, agent_name=agent_name,
                message=thinking_phrase, data={"status": "running", "thinking": thinking_phrase}
            ))

            agent = None
            try:
                _agent_session_id = session_id or evidence_artifact.artifact_id
                if isinstance(_agent_session_id, str):
                    try:
                        _agent_session_id = UUID(_agent_session_id)
                    except Exception:
                        pass

                agent_kwargs = {
                    "agent_id": agent_id, "session_id": _agent_session_id, "evidence_artifact": evidence_artifact,
                    "config": pipeline.config, "working_memory": pipeline.working_memory, "episodic_memory": pipeline.episodic_memory,
                    "custody_logger": pipeline.custody_logger, "evidence_store": pipeline.evidence_store, "inter_agent_bus": pipeline.inter_agent_bus
                }
                agent = AgentClass(**agent_kwargs)
                heartbeat_done = asyncio.Event()
                heartbeat_task = asyncio.create_task(make_heartbeat(agent_id, agent_name, agent.working_memory, heartbeat_done))

                base_budget = float(pipeline.config.investigation_timeout)
                agent_timeout = min(240, max(150, base_budget * 0.40)) if agent_id in ("Agent1", "Agent3") else min(240, max(120, base_budget * 0.35))
                
                try:
                    findings = await asyncio.wait_for(agent.run_investigation(), timeout=agent_timeout)
                finally:
                    heartbeat_done.set()
                    try:
                        await asyncio.wait_for(heartbeat_task, timeout=2.0)
                    except Exception:
                        heartbeat_task.cancel()

                if pipeline.config.llm_enable_post_synthesis and pipeline.config.llm_api_key and pipeline.config.llm_provider != "none" and findings:
                    await broadcast_update(ws_session_id, BriefUpdate(
                        type="AGENT_UPDATE", session_id=ws_session_id, agent_id=agent_id, agent_name=agent_name,
                        message="🤖 Groq synthesising tool findings into forensic narrative…",
                        data={"status": "running", "thinking": "🤖 Groq synthesising tool findings into forensic narrative…"}
                    ))

                _NOT_APPLICABLE_TYPES = {"Format not supported", "Not Applicable", "File type not applicable"}
                is_unsupported = bool(findings) and all(getattr(f, "finding_type", "") in _NOT_APPLICABLE_TYPES for f in findings)
                if is_unsupported:
                    mime_label = getattr(evidence_artifact, "mime_type", None) or evidence_artifact.metadata.get("original_filename", os.path.basename(evidence_file_path))
                    clean_text = f"{agent_name} does not support {mime_label}. {agent_name} skipped forensic analysis."
                    for f in findings: f.reasoning_summary = clean_text

                serialized_chain = [(s.model_dump(mode="json") if hasattr(s, "model_dump") else s.dict() if hasattr(s, "dict") else s) for s in getattr(agent, "_react_chain", [])]
                reflection_report = getattr(agent, "_reflection_report", None)
                result = AgentLoopResult(
                    agent_id=agent_id, findings=[f.model_dump(mode="json") for f in findings],
                    reflection_report=reflection_report.model_dump(mode="json") if reflection_report else {},
                    react_chain=serialized_chain
                )
            except TimeoutError:
                result = AgentLoopResult(agent_id=agent_id, findings=[], reflection_report={}, react_chain=[], error=f"Timeout after {agent_timeout:.0f}s")
            except Exception as e:
                result = AgentLoopResult(agent_id=agent_id, findings=[], reflection_report={}, react_chain=[], error=str(e))

            confidence = 0.0
            finding_summary = f"{agent_name} analysis complete."
            if result.findings:
                _NA_FLAGS = ("ela_not_applicable", "ghost_not_applicable", "noise_fingerprint_not_applicable", "prnu_not_applicable")
                def _is_na(f):
                    m = f.get("metadata") or {}
                    return any(m.get(k) for k in _NA_FLAGS) or str(m.get("verdict", "")).upper() == "NOT_APPLICABLE" or str(f.get("finding_type", "")).lower() in ("not applicable", "file type not applicable")
                
                confidences = [f.get("confidence_raw", 0.5) for f in result.findings if not _is_na(f)]
                if confidences:
                    cs = sorted(confidences)
                    mid = len(cs) // 2
                    confidence = cs[mid] if len(cs) % 2 == 1 else (cs[mid-1] + cs[mid]) / 2
                else: confidence = 0.5

                _PRIORITY_TOOLS = {"agent1": ["ela_full_image", "jpeg_ghost_detect", "noise_fingerprint", "copy_move_detect", "frequency_domain_analysis"], "agent2": ["anti_spoofing_detect", "audio_splice_detect", "speaker_diarize"], "agent3": ["object_detection", "lighting_consistency", "vector_contraband_search"], "agent4": ["optical_flow_analysis", "face_swap_detection", "deepfake_frequency_check"], "agent5": ["exif_extract", "hex_signature_scan", "gps_timezone_validate", "steganography_scan"]}
                priority_tools = _PRIORITY_TOOLS.get(agent_id.lower(), [])
                finding_summaries, priority_summaries = [], []
                for f in result.findings:
                    s = f.get("reasoning_summary")
                    if s:
                        finding_summaries.append(s)
                        if (f.get("metadata") or {}).get("tool_name") in priority_tools: priority_summaries.append(s)
                best = max(priority_summaries or finding_summaries or [""], key=len)
                if best: finding_summary = best[:800]
            elif result.error: finding_summary = f"Error: {result.error[:120]}"

            _agent_err = getattr(agent, "_tool_error_count", 0) if agent else 0
            _agent_ok = getattr(agent, "_tool_success_count", 0) if agent else 0
            tool_error_rate = round(_agent_err / (_agent_err + _agent_ok), 3) if (_agent_err + _agent_ok) > 0 else 0.0

            final_confidence = getattr(agent, "_agent_confidence", confidence)
            final_error_rate = getattr(agent, "_agent_error_rate", tool_error_rate)

            agent_verdict, section_flags = None, []
            if result.findings:
                seen_sections = set()
                for f in result.findings:
                    meta = f.get("metadata") or {}
                    if agent_verdict is None: agent_verdict = meta.get("agent_verdict")
                    sid = meta.get("section_id")
                    if sid and sid not in seen_sections:
                        seen_sections.add(sid)
                        section_flags.append({"id": sid, "label": meta.get("section_label", sid), "flag": meta.get("section_flag", "info"), "key_signal": meta.get("section_key_signal", "")})

            if agent_verdict is None:
                if result.findings:
                    sevs = [_assign_severity_tier(f).upper() for f in result.findings]
                    tot = sum(1 for s in sevs if s != "INFO") or 1
                    crit, hi, med = sevs.count("CRITICAL"), sevs.count("HIGH"), sevs.count("MEDIUM")
                    rat = (crit + hi) / tot
                    agent_verdict = "MANIPULATED" if crit > 0 and rat >= 0.50 else "LIKELY_MANIPULATED" if crit > 0 or rat >= 0.30 else "INCONCLUSIVE" if rat >= 0.10 or (med / tot) >= 0.40 or (final_confidence < 0.50 and tot > 1) else "AUTHENTIC"
                else: agent_verdict = "INCONCLUSIVE" if result.error else "AUTHENTIC"

            findings_preview = []
            for f in result.findings:
                m = f.get("metadata") or {}
                tool = m.get("tool_name") or f.get("finding_type")
                s = f.get("reasoning_summary", "")
                if not s: continue
                if tool and s.lower().startswith(tool.lower() + ":"): s = s[len(tool)+1:].strip()
                sev = _assign_severity_tier(f)
                tv = "NOT_APPLICABLE" if any(m.get(fl) for fl in ("ela_not_applicable", "ghost_not_applicable", "noise_fingerprint_not_applicable", "prnu_not_applicable", "gan_not_applicable")) else "ERROR" if m.get("court_defensible") is False else "FLAGGED" if sev in ("CRITICAL", "HIGH", "MEDIUM") else "CLEAN"
                findings_preview.append({"tool": tool, "summary": s[:320], "confidence": f.get("confidence_raw", 0.5), "flag": m.get("section_flag", "info"), "severity": sev, "verdict": tv, "key_signal": m.get("section_key_signal", ""), "section": m.get("section_label", ""), "elapsed_s": m.get("elapsed_s") or (round(float(m.get("latency_ms", 0))/1000, 1) if m.get("latency_ms") else None), "degraded": m.get("degraded"), "fallback_reason": m.get("fallback_reason")})

            await broadcast_update(ws_session_id, BriefUpdate(
                type="AGENT_COMPLETE", session_id=ws_session_id, agent_id=agent_id, agent_name=agent_name, message=finding_summary,
                data={"status": "skipped" if is_unsupported else "error" if result.error else "complete", "confidence": final_confidence, "findings_count": len(result.findings), "error": result.error, "tool_error_rate": final_error_rate, "agent_verdict": agent_verdict, "section_flags": section_flags, "findings_preview": [] if is_unsupported else findings_preview, "tools_ran": sum(1 for f in result.findings if not any((f.get("metadata") or {}).get(k) for k in ("ela_not_applicable", "ghost_not_applicable", "noise_fingerprint_not_applicable", "prnu_not_applicable", "gan_not_applicable")) and (f.get("metadata") or {}).get("court_defensible") is not False), "tools_skipped": sum(1 for f in result.findings if any((f.get("metadata") or {}).get(k) for k in ("ela_not_applicable", "ghost_not_applicable", "noise_fingerprint_not_applicable", "prnu_not_applicable", "gan_not_applicable"))), "tools_failed": sum(1 for f in result.findings if (f.get("metadata") or {}).get("court_defensible") is False), "degraded": any((f.get("metadata") or {}).get("degraded") for f in result.findings), "completed_at": datetime.now(UTC).isoformat()}
            ))

            _pipeline_completed[0] += 1
            idx = _pipeline_completed[0]
            tot = _total_supported or len(agent_configs)
            pl_msg = {1: "🔬 First agent reporting — analysis underway…", 2: "🔬 Two agents reporting — forensic scan in progress…", 3: "🔬 Three agents reporting — cross-modal validation running…"}.get(idx, f"🔬 {idx} of {tot} agents reporting findings…" if idx < tot else f"✅ All {tot} applicable agents have reported — awaiting decision…")
            await broadcast_update(ws_session_id, BriefUpdate(type="AGENT_UPDATE", session_id=ws_session_id, agent_id=None, agent_name=None, message=pl_msg, data={"status": "running", "thinking": pl_msg}))
            return result, agent

        for _id, _name, _Class, _ph in agent_configs:
            sup = MimeRegistry.is_supported(_id, mime, evidence_artifact.file_path)
            ph = _ph if sup else "🔍 Checking file type compatibility…"
            await broadcast_update(ws_session_id, BriefUpdate(type="AGENT_UPDATE", session_id=ws_session_id, agent_id=_id, agent_name=_name, message=ph, data={"status": "running", "thinking": ph}))

        tasks = [run_single_agent(aid, aname, AClass, ph) for aid, aname, AClass, ph in agent_configs]
        p_msg = f"⚙️ {_total_supported} forensic agent{'s' if _total_supported != 1 else ''} scanning evidence in parallel…"
        await broadcast_update(ws_session_id, BriefUpdate(type="AGENT_UPDATE", session_id=ws_session_id, agent_id=None, agent_name=None, message=p_msg, data={"status": "running", "thinking": p_msg}))

        _TICKER_PHRASES = ["🔬 Forensic tools running — extracting pixel-level artifacts…", "⚡ Cross-validating signals across all forensic domains…", "🧠 Pattern recognition models analysing evidence…", "📊 Aggregating forensic findings across active agents…", "🔬 Analysis in progress — building forensic evidence chain…", "🔍 Running advanced statistical anomaly detection…", "⚙️ Tool results queuing — synthesis pipeline active…"]
        async def _ticker(done: asyncio.Event):
            idx = 0
            while not done.is_set():
                try: await asyncio.wait_for(done.wait(), timeout=9.0)
                except TimeoutError: pass
                if done.is_set(): break
                ph = _TICKER_PHRASES[idx % len(_TICKER_PHRASES)]; idx += 1
                await broadcast_update(ws_session_id, BriefUpdate(type="AGENT_UPDATE", session_id=ws_session_id, agent_id=None, agent_name=None, message=ph, data={"status": "running", "thinking": ph}))

        t_done = asyncio.Event()
        t_task = asyncio.create_task(_ticker(t_done))
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        t_done.set()
        try:
            await asyncio.wait_for(t_task, timeout=1.0)
        except Exception:
            t_task.cancel()

        results, deep_pass_coroutines = [], []
        for i, r in enumerate(raw_results):
            aid, aname = agent_configs[i][0], agent_configs[i][1]
            if isinstance(r, BaseException):
                results.append(AgentLoopResult(agent_id=aid, findings=[], reflection_report={}, react_chain=[], error=str(r)))
                await broadcast_update(ws_session_id, BriefUpdate(type="AGENT_COMPLETE", session_id=ws_session_id, agent_id=aid, agent_name=aname, message=f"Error: {str(r)[:80]}", data={"status": "error", "confidence": 0.0, "findings_count": 0, "error": str(r)[:120], "tool_error_rate": 1.0}))
            elif isinstance(r, tuple) and len(r) == 2:
                res, ainst = r; results.append(res)
                if ainst and len(ainst.deep_task_decomposition) > 0 and (res.findings and not all((f.get("finding_type", "") if isinstance(f, dict) else f.finding_type).lower() in ("file type not applicable", "format not supported") for f in res.findings)):
                    deep_pass_coroutines.append((aid, aname, ainst, res))
            else: results.append(AgentLoopResult(agent_id=aid, findings=[], reflection_report={}, react_chain=[], error="Invalid result"))

        await broadcast_update(ws_session_id, BriefUpdate(type="PIPELINE_PAUSED", session_id=ws_session_id, agent_id=None, agent_name=None, message="Initial analysis complete. Ready for deep analysis.", data={"status": "awaiting_decision", "deep_analysis_pending": bool(deep_pass_coroutines), "agents_completed": len(results)}))
        pipeline._awaiting_user_decision = True
        await pipeline.deep_analysis_decision_event.wait()
        pipeline._awaiting_user_decision = False

        if pipeline.run_deep_analysis_flag and deep_pass_coroutines:
            await broadcast_update(ws_session_id, BriefUpdate(type="AGENT_UPDATE", session_id=ws_session_id, agent_id=None, agent_name=None, message=f"🔬 Deep analysis starting — {len(deep_pass_coroutines)} agent(s) loading heavy ML models…", data={"status": "running", "thinking": "Deep analysis starting…"}))
            a1_event = asyncio.Event()
            for aid, _an, ainst, _ar in deep_pass_coroutines:
                if aid in ("Agent3", "Agent5") and hasattr(ainst, "_agent1_context_event"): ainst._agent1_context_event = a1_event

            async def run_deep(aid, aname, ainst, ires):
                p_err, p_ok = getattr(ainst, "_tool_error_count", 0), getattr(ainst, "_tool_success_count", 0)
                await broadcast_update(ws_session_id, BriefUpdate(type="AGENT_UPDATE", session_id=ws_session_id, agent_id=aid, agent_name=aname, message={"Agent1": "🔬 Loading Gemini vision + ELA anomaly deep pass…", "Agent2": "🎙️ Running heavy audio ML models…", "Agent3": "👁️ Running Gemini scene analysis…", "Agent4": "🎬 Running deepfake frequency check…", "Agent5": "📊 Running ML metadata anomaly scoring…"}.get(aid, "🔬 Loading deep analysis…"), data={"status": "running"}))
                d_done = asyncio.Event(); d_task = asyncio.create_task(make_heartbeat(aid, aname, ainst.working_memory, d_done, deep_namespace=f"{aid}_deep"))
                try:
                    df_raw = await asyncio.wait_for(ainst.run_deep_investigation(), timeout=min(300, max(180, float(pipeline.config.investigation_timeout)*0.5)) if aid == "Agent1" else 240)
                except Exception as e: df_raw = []; logger.error(f"Deep pass fail: {aid} {e}")
                finally:
                    d_done.set()
                    try:
                        await asyncio.wait_for(d_task, timeout=2.0)
                    except Exception:
                        d_task.cancel()
                df_serial = [(f.model_dump(mode="json") if hasattr(f, "model_dump") else f) for f in df_raw]
                ires.findings = [(f.model_dump(mode="json") if hasattr(f, "model_dump") else f) for f in ainst._findings]
                conf = sorted(f.get("confidence_raw", 0.5) for f in df_serial)
                conf = conf[len(conf)//2] if len(conf)%2==1 else (conf[len(conf)//2-1]+conf[len(conf)//2])/2 if conf else 0.5
                best_d = max([f["reasoning_summary"] for f in df_serial if f.get("reasoning_summary")] or [f"{aname} deep analysis complete."], key=len)
                await broadcast_update(ws_session_id, BriefUpdate(type="AGENT_COMPLETE", session_id=ws_session_id, agent_id=aid, agent_name=aname, message=f"🔬 Deep — {best_d[:900]}", data={"status": "complete", "confidence": getattr(ainst, "_agent_confidence", conf), "findings_count": len(df_serial), "tool_error_rate": getattr(ainst, "_agent_error_rate", 0.0), "completed_at": datetime.now(UTC).isoformat()}))

            async def run_a1_deep():
                a1_t = next((t for t in deep_pass_coroutines if t[0] == "Agent1"), None)
                if a1_t:
                    await run_deep(*a1_t)
                    gem = getattr(a1_t[2], "_gemini_vision_result", {})
                    if not gem:
                        for f in getattr(a1_t[2], "_findings", []):
                            if "gemini" in getattr(f, "metadata", {}).get("tool_name", "").lower(): gem = f.metadata; break
                    if gem:
                        for aid, _, ainst, _ in deep_pass_coroutines:
                            if aid in ("Agent3", "Agent5") and hasattr(ainst, "inject_agent1_context"): ainst.inject_agent1_context(gem)
                a1_event.set()

            d_tasks = [run_a1_deep()] + [run_deep(aid, aname, ainst, ires) for aid, aname, ainst, ires in deep_pass_coroutines if aid != "Agent1"]
            await asyncio.gather(*d_tasks, return_exceptions=True)

        async def a_step(msg): await broadcast_update(ws_session_id, BriefUpdate(type="AGENT_UPDATE", session_id=ws_session_id, message=f"🔮 {msg}", data={"status": "deliberating", "thinking": f"🔮 {msg}"}))
        if pipeline.arbiter: pipeline.arbiter._step_hook = a_step
        await broadcast_update(ws_session_id, BriefUpdate(type="AGENT_UPDATE", session_id=ws_session_id, agent_id=None, agent_name=None, message="🔮 Council Arbiter deliberating — synthesising all findings…", data={"status": "deliberating", "thinking": "🔮 Council Arbiter deliberating — synthesising all findings…"}))
        return results

    pipeline._run_agents_concurrent = instrumented_run
    return await pipeline.run_investigation(evidence_file_path=evidence_file_path, case_id=case_id, investigator_id=investigator_id, original_filename=original_filename, session_id=UUID(session_id))


async def run_investigation_task(
    session_id: str,
    pipeline: ForensicCouncilPipeline,
    evidence_file_path: str,
    case_id: str,
    investigator_id: str,
    original_filename: str | None = None,
):
    """Background task to run investigation with improved timing."""
    error_msg = None
    timeout = min(settings.investigation_timeout, 600)
    from api.routes._session_state import clear_session_websockets

    try:
        ws_connected = False
        for _ in range(20):
            if get_session_websockets(session_id):
                ws_connected = True
                break
            await asyncio.sleep(0.1)

        await set_active_pipeline_metadata(session_id, {"status": "running", "brief": "Initialising forensic pipeline...", "case_id": case_id, "investigator_id": investigator_id, "file_path": evidence_file_path, "original_filename": original_filename, "created_at": datetime.now(UTC).isoformat()})
        await broadcast_update(session_id, BriefUpdate(type="AGENT_UPDATE", session_id=session_id, message="🚀 Initialising forensic pipeline — loading specialist agents…", data={"status": "starting"}))

        task = asyncio.create_task(_wrap_pipeline_with_broadcasts(pipeline, session_id, evidence_file_path, case_id, investigator_id, original_filename))
        deadline = time.monotonic() + float(timeout)
        
        while not task.done():
            rem = deadline - time.monotonic()
            if rem <= 0:
                task.cancel(); raise TimeoutError(f"Pipeline computation exceeded {timeout}s budget")
            done, _ = await asyncio.wait([task], timeout=min(5.0, rem))
            if task in done: break
            if getattr(pipeline, "_awaiting_user_decision", False):
                start = time.monotonic()
                try: await asyncio.wait_for(pipeline.deep_analysis_decision_event.wait(), timeout=3600.0)
                except TimeoutError:
                    pipeline.run_deep_analysis_flag = False
                    pipeline.deep_analysis_decision_event.set()
                deadline += (time.monotonic() - start)
                pipeline._awaiting_user_decision = False

        report = task.result()
        await broadcast_update(session_id, BriefUpdate(type="PIPELINE_COMPLETE", session_id=session_id, message="Investigation concluded.", data={"report_id": str(report.report_id)}))
        pipeline._final_report = report
        await set_final_report(session_id, report)
        await set_active_pipeline_metadata(session_id, {"status": "completed", "brief": "Investigation complete.", "case_id": case_id, "investigator_id": investigator_id, "file_path": evidence_file_path, "original_filename": original_filename, "created_at": datetime.now(UTC).isoformat(), "completed_at": datetime.now(UTC).isoformat(), "report_id": str(report.report_id)})
        increment_investigations_completed()

        try:
            from core.session_persistence import get_session_persistence
            persistence = await get_session_persistence()
            await persistence.save_report(session_id=session_id, case_id=case_id, investigator_id=investigator_id, report_data=report.model_dump(mode="json"))
            await persistence.update_session_status(session_id, "completed")
        except Exception as e: logger.error(f"DB persistence fail: {e}")

    except asyncio.CancelledError:
        _active_pipelines.pop(session_id, None); clear_session_websockets(session_id); raise
    except Exception as e:
        error_msg = str(e); logger.error(f"Investigation failed: {e}", exc_info=True)
        increment_investigations_failed()
        await broadcast_update(session_id, BriefUpdate(type="ERROR", session_id=session_id, message="Internal error. Please try again.", data={"error": error_msg}))
    finally:
        if error_msg:
            pipeline._error = error_msg
            try:
                await set_active_pipeline_metadata(session_id, {"status": "error", "brief": error_msg, "case_id": case_id, "investigator_id": investigator_id, "file_path": evidence_file_path, "original_filename": original_filename, "error": error_msg})
            except Exception:
                pass
        try:
            if os.path.exists(evidence_file_path): os.unlink(evidence_file_path)
        except Exception:
            pass
        _active_pipelines.pop(session_id, None); clear_session_websockets(session_id)
        cutoff = datetime.now(UTC).timestamp() - 86_400
        stale = [sid for sid, (_, cat) in list(_final_reports.items()) if cat.timestamp() < cutoff]
        for sid in stale: _final_reports.pop(sid, None)

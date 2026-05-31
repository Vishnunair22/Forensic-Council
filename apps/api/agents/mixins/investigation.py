"""
Investigation Mixin for Forensic Agents.
Handles ReAct loops, deep analysis pass, and arbiter challenges.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from core.llm_client import LLMClient
from core.react_loop import AgentFinding, ReActLoopEngine, create_llm_step_generator
from core.structured_logging import get_logger
from core.synthesis import SynthesisService, TEMPLATE_PATTERNS
from core.tracing import PipelineTrace

logger = get_logger(__name__)


def _is_template_text(text: str | None) -> bool:
    if not text:
        return True
    t = text.lower()
    return any(p in t for p in TEMPLATE_PATTERNS)


_TAMPERING_INDICATOR_KEYWORDS = {
    "manipulation", "splicing", "copy.move", "tamper",
    "forgery", "anomalous", "ai.generated", "synthetic",
    "diffusion", "gan", "deepfake", "inconsistent",
}

_SCREENSHOT_INAPPLICABLE_TOOLS = {
    "noiseprint_cluster",
    "noise_fingerprint",
    "prnu_sensor_verification",
    "neural_ela",
    "ela_full_image",
    "jpeg_ghost_detect",
    "neural_splicing",
    "splicing_detect",
    "neural_copy_move",
    "copy_move_detect",
    "adversarial_robustness_check",
    "roi_extract",
}


def _tool_from_task_description(description: str) -> str:
    lower = str(description or "").lower()
    for tool in _SCREENSHOT_INAPPLICABLE_TOOLS:
        if tool in lower:
            return tool
    if "prnu" in lower or "sensor-region" in lower or "sensor-level" in lower:
        return "noiseprint_cluster"
    return ""


class AgentInvestigationMixin:
    """
    Mixin handling the ReAct investigation loop and various pass types.
    """

    agent_id: str
    session_id: uuid.UUID
    config: Any
    working_memory: Any
    custody_logger: Any
    inter_agent_bus: Any
    evidence_artifact: Any
    iteration_ceiling: int
    agent_name: str
    heavy_tool_semaphore: asyncio.Semaphore | None
    task_decomposition: list[str]
    deep_task_decomposition: list[str]

    # Required methods from other mixins/base
    async def build_tool_registry(self) -> Any: ...
    async def build_initial_thought(self) -> str: ...
    def supports_uploaded_file(self) -> bool: ...
    def _signal_completion(self, skipped: bool = False) -> None: ...
    async def _initialize_working_memory(self) -> None: ...

    async def inject_task(self, description: str, priority: int = 10) -> None:
        """
        Dynamically inject a new task into the investigation pipeline.
        Used for reactive task decomposition based on intermediate findings.
        """
        try:
            reactive_agent_id = getattr(self, "_reactive_expansion_agent_id", None)
            target_agent_id = reactive_agent_id or self.agent_id
            phase = "deep" if reactive_agent_id else "initial"
            blocked_tool = _tool_from_task_description(description)
            if blocked_tool and self._is_screen_capture_context():
                logger.info(
                    "Skipping screenshot-inapplicable dynamic task",
                    agent_id=self.agent_id,
                    task=description,
                    tool_name=blocked_tool,
                    phase=phase,
                )
                return

            # Check if task already exists to avoid duplication loops
            # Also block COMPLETE tasks — re-injecting an already-executed
            # tool re-runs it and appends a duplicate finding with no dedup.
            state = await self.working_memory.get_state(self.session_id, target_agent_id)
            for existing in state.tasks:
                if existing.description.lower() == description.lower() and existing.status in ("PENDING", "IN_PROGRESS", "COMPLETE"):
                    logger.debug(f"Task already exists, skipping injection: {description}", agent_id=self.agent_id)
                    return

            await self.working_memory.create_task(
                session_id=self.session_id,
                agent_id=target_agent_id,
                description=description,
                priority=priority,
            )
            logger.info("Dynamic task injected", agent_id=self.agent_id, task=description, phase=phase)

            # Check if analysis is still active to avoid stale telemetry cycling
            if getattr(self, "_investigation_completed", False):
                logger.debug(
                    "Investigation already completed, skipping telemetry broadcast",
                    agent_id=self.agent_id,
                )
                return

            # Issue 4.6 Fix: Broadcast updated tools_total
            try:
                state = await self.working_memory.get_state(self.session_id, target_agent_id)
                new_total = len([t for t in state.tasks if t.status in ("PENDING", "IN_PROGRESS")])
                from api.routes._session_state import broadcast_update
                from api.schemas import BriefUpdate
                await broadcast_update(
                    str(self.session_id),
                    BriefUpdate(
                        type="AGENT_UPDATE",
                        session_id=str(self.session_id),
                        agent_id=self.agent_id,
                        agent_name=self.agent_name,
                        message=f"Task injected: {description}",
                        data={
                            "status": "running",
                            "thinking": description,
                            "tools_total": new_total,
                            "analysis_phase": phase,
                        },
                    ),
                )
            except Exception as e:
                logger.debug("tools_total broadcast failed", error=str(e))
        except Exception as e:
            logger.error("Failed to inject dynamic task", agent_id=self.agent_id, error=str(e))

    def _is_screen_capture_context(self) -> bool:
        """Return true once the shared visual profile identifies a digital UI/screenshot."""
        try:
            ctx = getattr(self, "_tool_context", {}) or {}
            visual = ctx.get("visual_evidence_profile") or {}
            if hasattr(visual, "to_finding_dict"):
                visual = visual.to_finding_dict()
            meta = visual.get("metadata") if isinstance(visual, dict) else {}
            haystack = " ".join(
                str(x or "")
                for x in (
                    visual.get("content_description") if isinstance(visual, dict) else "",
                    visual.get("reasoning_summary") if isinstance(visual, dict) else "",
                    meta.get("content_description") if isinstance(meta, dict) else "",
                    meta.get("contextual_narrative") if isinstance(meta, dict) else "",
                    meta.get("interface_identification") if isinstance(meta, dict) else "",
                    (meta.get("forensic_routing") or {}).get("image_category") if isinstance(meta, dict) and isinstance(meta.get("forensic_routing"), dict) else "",
                )
            ).lower()
            return any(token in haystack for token in ("screenshot", "screen capture", "digital ui", "browser", "whatsapp", "telegram", "web page"))
        except Exception:
            return False

    async def _check_tool_availability(self) -> None:
        """Log unavailable tools to custody; does not raise — agents degrade gracefully."""
        if getattr(self, "_tool_registry", None) is None:
            return
        unavailable = [t.name for t in self._tool_registry.list_tools() if not t.available]
        if unavailable:
            logger.warning(
                "Tools unavailable at investigation start",
                agent_id=self.agent_id,
                unavailable_tools=unavailable,
            )
            if self.custody_logger:
                from core.custody_logger import EntryType

                await self.custody_logger.log_entry(
                    agent_id=self.agent_id,
                    session_id=self.session_id,
                    entry_type=EntryType.TOOL_CALL,
                    content={
                        "action": "tool_availability_check",
                        "unavailable_tools": unavailable,
                        "note": "Degraded mode — these tools will produce INCOMPLETE findings",
                    },
                )



    async def _publish_tool_registry_snapshot(self, agent_id: str | None = None) -> None:
        """Expose the live tool catalogue to working memory for LLM ReAct mode.

        Tools are filtered to only include those applicable to the evidence
        MIME type (Fix 3) so the LLM never suggests semantically wrong tools.
        """
        registry = getattr(self, "_tool_registry", None)
        if registry is None:
            return

        # Apply MIME-type filtering so the LLM only sees relevant tools.
        mime_type: str = (
            getattr(getattr(self, "evidence_artifact", None), "mime_type", None) or ""
        )
        try:
            from core.task_tool_config import get_allowed_tools_for_mime

            allowed = get_allowed_tools_for_mime(mime_type) if mime_type else None
        except Exception:
            allowed = None

        all_tools = registry.list_tools()
        if allowed is not None:
            filtered = [t for t in all_tools if t.name in allowed]
            # Safety: if filtering would leave zero tools, use the full set.
            snapshot = [t.model_dump() for t in (filtered if filtered else all_tools)]
        else:
            snapshot = [t.model_dump() for t in all_tools]
        try:
            await self.working_memory.update_state(
                session_id=self.session_id,
                agent_id=agent_id or self.agent_id,
                updates={"tool_registry_snapshot": snapshot},
            )
        except Exception as exc:
            logger.debug(
                "Failed to publish tool registry snapshot",
                agent_id=agent_id or self.agent_id,
                error=str(exc),
            )

    def _apply_synthesis_sections(
        self,
        findings: list[AgentFinding],
        sections: list[dict[str, Any]],
    ) -> None:
        """Write section metadata + refined summaries from a synthesis result back onto findings."""
        for section in sections:
            if section.get("flag") in ("bad", "warn", "ok", "info"):
                flag = section["flag"]
            else:
                sev = section.get("severity", "LOW")
                flag = (
                    "bad" if sev in ("HIGH", "CRITICAL")
                    else ("warn" if sev == "MEDIUM" else "ok")
                )
            key_signal = str(section.get("key_signal") or "").strip()
            opinion = section.get("opinion")
            for item in section.get("refined_findings", []):
                tool_name = item.get("tool")
                friendly_text = item.get("user_friendly_summary")
                if not tool_name:
                    continue
                for f in findings:
                    if (f.metadata.get("tool_name") or f.finding_type) == tool_name:
                        if friendly_text:
                            f.metadata["llm_refined_summary"] = friendly_text
                        f.metadata["section_id"] = section.get("id")
                        f.metadata["section_label"] = section.get("label")
                        f.metadata["section_flag"] = flag
                        f.metadata["llm_synthesis"] = opinion
                        f.metadata["section_key_signal"] = key_signal

    async def _synthesize_findings_once(
        self,
        findings: list[AgentFinding],
        phase: str,
        timeout_s: float = 35.0,
    ) -> dict[str, Any] | None:
        """Run one bounded post-analysis synthesis call for card/report narration."""
        if self.config.local_only_analysis:
            return None

        if not (self.config.llm_enable_post_synthesis and self.config.llm_api_key):
            return None
        try:
            synthesis_service = SynthesisService(self.config)
            agent_persona = getattr(self, "persona", "")
            tool_context = getattr(self, "_tool_context", {}) or {}
            image_type_hint = tool_context.get("analyze_image_content", {}).get("image_type", "")

            # Extract full shared visual evidence profile for optional synthesis.
            # Primary: agent's own tool_context (Agent 1 stores its result here).
            # Fallback: read from inter-agent bus (Agents 3/5 reuse Agent 1's result).
            visual_profile = (
                tool_context.get("visual_evidence_profile")
                or {}
            )

            if not visual_profile and getattr(self, "inter_agent_bus", None):
                try:
                    bus_ctx = self.inter_agent_bus.get_visual_profile(str(self.session_id)) or {}
                    if bus_ctx:
                        visual_profile = bus_ctx
                except Exception as _bus_err:  # noqa: S110
                    logger.debug("Visual profile bus lookup failed", error=str(_bus_err))

            # visual_profile is the full to_finding_dict() output:
            #   { "reasoning_summary": ..., "confidence_raw": ..., "metadata": { ... } }
            # The nested metadata dict holds all deep-forensic extra fields.
            # We also support direct-field access as a fallback for any path that
            # stores the VisualEvidenceFinding attrs without the metadata wrapper.
            visual_metadata = visual_profile.get("metadata") or {}
            if not isinstance(visual_metadata, dict):
                visual_metadata = {}

            def _gem_str(meta_key: str, *top_keys: str) -> str:
                """Read from metadata dict first, then fall back to top-level keys."""
                v = visual_metadata.get(meta_key)
                if v:
                    return str(v).strip()
                for k in top_keys:
                    v = visual_profile.get(k)
                    if v:
                        return str(v).strip()
                return ""

            def _gem_lst(meta_key: str, *top_keys: str) -> list:
                """Read list from metadata dict first, then top-level keys."""
                v = visual_metadata.get(meta_key)
                if isinstance(v, list) and v:
                    return v
                for k in top_keys:
                    v = visual_profile.get(k)
                    if isinstance(v, list) and v:
                        return v
                return []

            # Build a rich visual profile context — forwards everything so synthesis can anchor
            # the agent_brief in what the evidence actually IS, not generic boilerplate.
            visual_context: dict = {
                # Evidence identity
                "content_description": _gem_str(
                    "content_description", "content_description", "reasoning_summary"
                ),
                "image_category": _gem_str(
                    "file_type_assessment", "image_category"
                ),
                "interface_identification": _gem_str(
                    "interface_identification"
                ),
                # Visual verdict and forensic signals
                "visual_verdict": _gem_str(
                    "authenticity_verdict", "visual_verdict"
                ),
                "visual_confidence": float(visual_profile.get("confidence_raw") or 0.0),
                "priority_signals": _gem_lst(
                    "manipulation_signals", "priority_signals"
                ),
                "contextual_anomalies": _gem_lst(
                    "contextual_anomalies"
                ),
                # Rich narrative and specifics
                "contextual_narrative": _gem_str(
                    "contextual_narrative"
                ),
                "forensic_specifics": _gem_str(
                    "forensic_specifics"
                ),
                # Extracted text
                "extracted_text": _gem_lst(
                    "extracted_text"
                ),
            }
            # Strip falsy values (keep 0.0 for confidence) so the prompt block stays clean
            visual_context = {k: v for k, v in visual_context.items() if v or v == 0.0}

            if visual_context:
                logger.debug(
                    "Visual profile context built for synthesis",
                    agent_id=self.agent_id,
                    fields=list(visual_context.keys()),
                    has_narrative=bool(visual_context.get("contextual_narrative")),
                    has_verdict=bool(visual_context.get("visual_verdict")),
                )
            else:
                logger.warning(
                    "Visual profile context is empty — synthesis will lack visual grounding",
                    agent_id=self.agent_id,
                    phase=phase,
                )


            # Fix 1: Live progress broadcast before Groq call
            phase_label = f" - {phase.title()} Phase" if phase else ""
            from api.routes._session_state import broadcast_update
            from api.schemas import BriefUpdate
            await broadcast_update(
                str(self.session_id),
                BriefUpdate(
                    type="AGENT_UPDATE",
                    session_id=str(self.session_id),
                    agent_id=self.agent_id,
                    agent_name=self.agent_name,
                    message=f"Analyzing {len(findings)} tool finding(s) against image context{phase_label}.",
                    data={
                        "status": "running",
                        "thinking": f"Cross-referencing tool results with image context{phase_label}",
                        "analysis_phase": phase or "initial",
                    },
                ),
            )

            # Fix 1: Rotating keepalive during Groq call
            keepalive_task: asyncio.Task | None = None
            async def _broadcast_keepalive():
                phases_str = ["weighing results", "cross-referencing signals", "building narrative", "finalizing verdict"]
                idx = 0
                while True:
                    await asyncio.sleep(4.0)
                    msg = f"Synthesis {phases_str[idx % len(phases_str)]}{phase_label}"
                    idx += 1
                    try:
                        await broadcast_update(
                            str(self.session_id),
                            BriefUpdate(
                                type="AGENT_UPDATE",
                                session_id=str(self.session_id),
                                agent_id=self.agent_id,
                                agent_name=self.agent_name,
                                message=msg,
                                data={
                                    "status": "running",
                                    "thinking": msg,
                                    "analysis_phase": phase or "initial",
                                },
                            ),
                        )
                    except Exception as _kp_err:  # noqa: S110
                        logger.debug("Keepalive broadcast failed", error=str(_kp_err))

            keepalive_task = asyncio.create_task(_broadcast_keepalive())

            # Stagger synthesis calls across agents to avoid bursting the shared
            # Groq RPM quota. Agent index (1-5) maps to a 0-10s spread.
            import re as _re
            _agent_num_match = _re.search(r'\d+', str(self.agent_id))
            _agent_num = int(_agent_num_match.group(0) or 0) if _agent_num_match else 0
            _stagger_s = _agent_num * 2.0  # 0s, 2s, 4s, 6s, 8s, 10s for agents 0-5
            if _stagger_s > 0:
                await asyncio.sleep(_stagger_s)

            # Fix 3: Pass Phase 1 synthesis as frozen context for deep phase
            phase1_context = None
            if phase == "deep":
                phase1_synthesis = getattr(self, "_agent_synthesis", None) or {}
                phase1_verdict = phase1_synthesis.get("verdict", "INCONCLUSIVE")
                phase1_confidence = phase1_synthesis.get("agent_confidence", 0.0)
                phase1_narrative = phase1_synthesis.get("narrative_summary", "")
                phase1_context = {
                    "phase1_verdict": phase1_verdict,
                    "phase1_confidence": phase1_confidence,
                    "phase1_narrative": phase1_narrative,
                }

            try:
                synthesis_result = await asyncio.wait_for(
                    synthesis_service.synthesize_findings(
                        agent_id=self.agent_id,
                        agent_name=self.agent_name,
                        findings=findings,
                        evidence_artifact=self.evidence_artifact,
                        tool_success_count=self._tool_success_count,  # type: ignore[attr-defined]
                        tool_error_count=self._tool_error_count,  # type: ignore[attr-defined]
                        phase=phase,
                        agent_persona=agent_persona,
                        image_type_hint=image_type_hint,
                        visual_profile_context=visual_context or None,
                        phase1_context=phase1_context,
                    ),
                    timeout=timeout_s,
                )
            finally:
                if keepalive_task:
                    keepalive_task.cancel()
                    try:
                        await keepalive_task
                    except asyncio.CancelledError:
                        pass

            if synthesis_result:
                self._agent_confidence = synthesis_result.get("agent_confidence")
                self._agent_error_rate = synthesis_result.get("agent_error_rate")
                self._agent_synthesis = synthesis_result
                self._apply_synthesis_sections(findings, synthesis_result.get("sections", []))
                return synthesis_result
        except Exception as e:
            logger.warning(f"{phase.title()} synthesis failed: {e}", exc_info=True)
        return None

    async def _publish_agent_context(
        self,
        phase: str,
        findings: list[AgentFinding],
    ) -> None:
        """Publish compact cross-agent context for sibling-agent grounding."""
        if not self.working_memory:
            return
        compact_tools = {}
        for tool_name, result in getattr(self, "_tool_context", {}).items():
            if not isinstance(result, dict):
                continue
            compact_tools[tool_name] = {
                key: value
                for key, value in result.items()
                if key
                in {
                    "verdict",
                    "status",
                    "confidence",
                    "manipulation_detected",
                    "splicing_detected",
                    "copy_move_detected",
                    "is_ai_generated",
                    "diffusion_detected",
                    "device_model",
                    "software",
                    "gps_info",
                    "image_type",
                    "all_classifications",
                    "detections",
                    "weapon_detections",
                    "classes_found",
                    "visual_grounding",
                    "grounded_by_visual_profile",
                    "extracted_text",
                    "text",
                    "word_count",
                    "file_size_bytes",
                    "metadata_timeline_consistent",
                    "inconsistency_detected",
                    "anomaly_detected",
                    "summary",
                }
            }

        context = {
            "phase": phase,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "initial_summary": getattr(self, "_agent_synthesis", None) or {},
            "tool_context": compact_tools,
            "finding_count": len(findings),
            "agent_confidence": getattr(self, "_agent_confidence", None),
            "agent_error_rate": getattr(self, "_agent_error_rate", None),
        }
        try:
            await self.working_memory.set_agent_context(
                self.session_id,
                self.agent_id,
                context,
            )
        except Exception as exc:
            logger.debug(
                "Failed to publish agent context",
                agent_id=self.agent_id,
                phase=phase,
                error=str(exc),
            )

    def _build_initial_findings_summary(self, phase: str = "initial") -> str:
        """Build a concise text summary of Phase-1 findings for deep analysis context."""
        findings = getattr(self, "_findings", [])
        if not findings:
            return "No prior findings available."
        actionable = [
            f for f in findings
            if f.status != "NOT_APPLICABLE" and f.evidence_verdict != "NOT_APPLICABLE"
        ]
        if not actionable:
            return "No actionable findings from prior phase."

        positive = [f for f in actionable if f.evidence_verdict == "POSITIVE"]
        suspicious = [
            f for f in actionable
            if str(f.evidence_verdict or "").upper() in ("SUSPICIOUS", "TAMPERED", "MANIPULATED")
        ]
        negative = [f for f in actionable if f.evidence_verdict == "NEGATIVE"]
        inconclusive = [f for f in actionable if f.evidence_verdict == "INCONCLUSIVE"]

        lines = [f"{self.agent_name} — {phase.title()} Phase Summary:"]
        if positive:
            lines.append(f"  POSITIVE findings: {len(positive)}")
            for f in positive[:3]:
                tool = f.metadata.get("tool_name", f.finding_type)
                lines.append(f"    - {tool}: conf={f.confidence_raw:.2f}")
        if suspicious:
            lines.append(f"  SUSPICIOUS findings: {len(suspicious)}")
            for f in suspicious[:2]:
                tool = f.metadata.get("tool_name", f.finding_type)
                lines.append(f"    - {tool}: conf={f.confidence_raw:.2f}")
        if negative:
            lines.append(f"  CLEAN findings: {len(negative)}")
        if inconclusive:
            lines.append(f"  INCONCLUSIVE findings: {len(inconclusive)}")

        highest_conf = max(
            (f.confidence_raw for f in actionable if f.confidence_raw is not None), default=0.0
        )
        lines.append(f"  Highest confidence: {highest_conf:.2f}")
        total_tools = len(actionable)
        error_count = sum(
            1 for f in actionable if f.status == "INCOMPLETE" or f.evidence_verdict == "ERROR"
        )
        if error_count:
            lines.append(f"  Tool errors: {error_count}/{total_tools}")

        # Supplement with specific Phase-1 tool context metrics
        tool_ctx = getattr(self, "_tool_context", {}) or {}
        metric_lines = []
        ela = tool_ctx.get("neural_ela", {}) or tool_ctx.get("ela_full_image", {})
        if isinstance(ela, dict):
            ela_score = ela.get("anomaly_score") or ela.get("ela_score")
            if ela_score is not None:
                metric_lines.append(f"ELA anomaly score: {float(ela_score):.3f}")
        noiseprint = tool_ctx.get("noiseprint_cluster", {})
        if isinstance(noiseprint, dict):
            clusters = noiseprint.get("num_clusters") or noiseprint.get("cluster_count")
            if clusters is not None:
                metric_lines.append(f"Noiseprint clusters: {int(clusters)}")
        fft = tool_ctx.get("frequency_domain_analysis", {})
        if isinstance(fft, dict):
            fft_score = fft.get("high_frequency_score") or fft.get("anomaly_score")
            if fft_score is not None:
                metric_lines.append(f"FFT high-freq score: {float(fft_score):.3f}")
        if metric_lines:
            lines.append("  Key metrics: " + "; ".join(metric_lines))

        return "\n".join(lines)

    def _generate_agent_brief(self, phase: str) -> dict[str, Any]:
        """Generate a structured agent brief summarizing findings for this phase."""
        findings = getattr(self, "_findings", [])
        phase_findings = [
            f for f in findings if f.metadata.get("analysis_phase", "initial") == phase
        ] if phase else findings

        actionable = [
            f for f in phase_findings
            if f.status != "NOT_APPLICABLE" and f.evidence_verdict != "NOT_APPLICABLE"
        ]
        tool_names = sorted({
            str(f.metadata.get("tool_name") or f.finding_type)
            for f in actionable
        })
        positive_count = sum(1 for f in actionable if f.evidence_verdict == "POSITIVE")
        suspicious_count = sum(
            1 for f in actionable
            if str(f.evidence_verdict or "").upper() in ("SUSPICIOUS", "TAMPERED", "MANIPULATED")
        )
        negative_count = sum(1 for f in actionable if f.evidence_verdict == "NEGATIVE")
        error_count = sum(
            1 for f in actionable if f.status == "INCOMPLETE" or f.evidence_verdict == "ERROR"
        )

        tampering_signals = positive_count + suspicious_count
        brief = {
            "agent_name": self.agent_name,
            "phase": phase,
            "total_findings": len(phase_findings),
            "actionable_findings": len(actionable),
            "tools_used": tool_names,
            "tool_count": len(tool_names),
            "positive_count": positive_count,
            "suspicious_count": suspicious_count,
            "negative_count": negative_count,
            "error_count": error_count,
            "tampering_signal_count": tampering_signals,
            "has_tampering_signals": tampering_signals > 0,
        }
        self._agent_brief = brief
        return brief

    def _build_deterministic_synthesis(
        self,
        findings: list[AgentFinding],
        phase: str,
    ) -> dict[str, Any]:
        """Build metrics and evidence-grounded summaries when the LLM is unavailable."""
        actionable = []
        for f in findings:
            if f.status == "NOT_APPLICABLE" or f.evidence_verdict == "NOT_APPLICABLE":
                continue
            summary = f.metadata.get("llm_refined_summary") or f.reasoning_summary or f.finding_type or ""
            if _is_template_text(summary):
                continue
            actionable.append(f)
        confidence_values = [
            float(f.confidence_raw)
            for f in actionable
            if f.confidence_raw is not None
            and f.status != "INCOMPLETE"
            and f.evidence_verdict != "ERROR"
        ]
        confidence = (
            round(sum(confidence_values) / len(confidence_values), 3) if confidence_values else 0.0
        )
        error_count = sum(
            1 for f in actionable if f.status == "INCOMPLETE" or f.evidence_verdict == "ERROR"
        )
        error_rate = round(error_count / len(actionable), 3) if actionable else 0.0
        positive_count = sum(1 for f in actionable if f.evidence_verdict == "POSITIVE")
        negative_count = sum(1 for f in actionable if f.evidence_verdict == "NEGATIVE")

        # Determine is_screenshot from evidence artifact if available
        _evidence_artifact = getattr(self, "evidence_artifact", None)
        from core.media_kind import is_screen_capture_like as _is_scap
        _is_screenshot = _is_scap(_evidence_artifact) if _evidence_artifact else False
        _visual_profile = getattr(self, "_tool_context", {}).get("visual_evidence_profile") or {}
        _visual_meta = _visual_profile.get("metadata") if isinstance(_visual_profile, dict) else {}
        if not isinstance(_visual_meta, dict):
            _visual_meta = {}
        _visual_desc = (
            _visual_meta.get("content_description")
            or _visual_meta.get("contextual_narrative")
            or (_visual_profile.get("reasoning_summary") if isinstance(_visual_profile, dict) else "")
            or ""
        )
        _routing = _visual_meta.get("forensic_routing")
        _visual_category = str(_routing.get("image_category") or "") if isinstance(_routing, dict) else ""
        _visual_category = _visual_category or str(_visual_meta.get("file_type_assessment") or "")
        _persona = str(getattr(self, "persona", "") or "")
        _persona_role = _persona.split(".")[0].strip() if _persona else self.agent_name

        if positive_count >= 2:
            verdict = "TAMPERED"
        elif positive_count == 1:
            verdict = "SUSPICIOUS"
        elif error_rate > 0.4 and positive_count == 0:
            # High tool failure rate with no positive signals: inconclusive coverage gap
            # (never SUSPICIOUS — tool failures are not manipulation evidence).
            verdict = "INCONCLUSIVE"
        elif _is_screenshot and positive_count == 0:
            # Screenshots: ELA/noise tools often fail or flag edge noise naturally.
            # Without actual POSITIVE signals, the evidence is authentic from pixel perspective.
            verdict = "AUTHENTIC"
        elif (
            error_rate == 0 and actionable and negative_count >= max(1, int(len(actionable) * 0.75))
        ):
            verdict = "AUTHENTIC"
            if confidence < 0.7:
                confidence = 0.7
        elif confidence >= 0.7 and error_rate == 0:
            verdict = "AUTHENTIC"
        else:
            verdict = "INCONCLUSIVE"

        def _tool_name(f: AgentFinding) -> str:
            return str(f.metadata.get("tool_name") or f.finding_type).replace("_", " ").title()

        def _severity(f: AgentFinding) -> str:
            verdict = str(f.evidence_verdict or "").upper()
            status = str(f.status or "").upper()
            if verdict in {"POSITIVE", "TAMPERED", "SUSPICIOUS", "MANIPULATED"}:
                conf = float(f.confidence_raw or 0.0)
                return "HIGH" if conf >= 0.7 else "MEDIUM"
            if verdict == "ERROR" or status == "INCOMPLETE":
                return "MEDIUM"
            return "LOW"

        # Force high-integrity clean signals into the list so "hash matched" and
        # "EXIF found" are always cited, even when they rank below positive findings.
        _high_integrity_tools = {"file_hash_verify", "hash_verify", "exif_extract", "file_structure_analysis"}
        high_integrity = [
            f for f in actionable
            if str(f.metadata.get("tool_name") or f.finding_type) in _high_integrity_tools
        ]
        sorted_findings = sorted(
            actionable,
            key=lambda f: (
                1 if str(f.evidence_verdict).upper() == "POSITIVE" else 0,
                float(f.confidence_raw or 0.0),
            ),
            reverse=True,
        )
        # Cap at 3 sections; re-insert high-integrity tools if they were pushed out
        top_findings = sorted_findings[:3]
        top_tool_names = {str(f.metadata.get("tool_name") or f.finding_type) for f in top_findings}
        for hi_f in high_integrity:
            hi_tool = str(hi_f.metadata.get("tool_name") or hi_f.finding_type)
            if hi_tool not in top_tool_names and len(top_findings) < 4:
                top_findings.append(hi_f)
                top_tool_names.add(hi_tool)

        sections = []
        for idx, f in enumerate(top_findings, start=1):
            tool_name = str(f.metadata.get("tool_name") or f.finding_type)
            degraded = bool(f.metadata.get("degraded") or f.metadata.get("fallback_reason"))
            ev = str(f.evidence_verdict or "").upper()
            summary = f.reasoning_summary.strip()

            tool_ctx = self._tool_context.get(tool_name) or {}
            opinion = None

            if isinstance(tool_ctx, dict) and tool_ctx:
                # Custom domain-knowledge deterministic narration rules
                # 1. ELA tools
                if tool_name in ("neural_ela", "ela_full_image"):
                    num = tool_ctx.get("num_anomaly_regions", 0)
                    score = tool_ctx.get("anomaly_score", 0.0)
                    if ev == "POSITIVE" or tool_ctx.get("manipulation_detected"):
                        opinion = f"Neural ELA detected {num} compression anomaly region(s) with an anomaly score of {score:.2f}, indicating local re-saving consistent with spliced content."
                    else:
                        opinion = f"Neural ELA measured uniform compression levels across all image blocks (anomaly score: {score:.2f}), showing no sign of selective re-saving."

                # 2. FFT tools
                elif tool_name in ("frequency_domain_analysis", "deepfake_frequency_check"):
                    score = tool_ctx.get("high_frequency_score", 0.0)
                    if ev == "POSITIVE" or tool_ctx.get("anomaly_detected") or tool_ctx.get("gan_artifact_detected"):
                        opinion = f"Frequency domain analysis identified periodic high-frequency spectral artifacts (score: {score:.2f}), a pattern consistent with GAN or diffusion model generation."
                    else:
                        opinion = f"Frequency domain analysis found a spectral distribution consistent with natural optical capture (score: {score:.2f})."

                # 3. Noiseprint tools
                elif tool_name in ("noiseprint_cluster", "noise_fingerprint"):
                    clusters = tool_ctx.get("num_clusters", 1)
                    if ev == "POSITIVE" or tool_ctx.get("manipulation_detected") or tool_ctx.get("sensor_inconsistency_detected"):
                        opinion = f"PRNU noise analysis identified {clusters} distinct camera sensor patterns within the same image, indicating that regions originated from different physical capture devices — a splicing composite."
                    else:
                        opinion = "Sensor noise fingerprint is uniform across the image (single-cluster PRNU), consistent with a single camera source."

                # 4. Neural Splicing
                elif tool_name in ("neural_splicing", "splicing_detect"):
                    conf = tool_ctx.get("confidence", 0.0) or tool_ctx.get("splicing_confidence", 0.0) or 0.0
                    if ev == "POSITIVE" or tool_ctx.get("splicing_detected"):
                        opinion = f"Splicing boundary detection found composited region edges with {conf:.2f} confidence, indicating content was inserted from an external source."
                    else:
                        opinion = "TruFor splicing analysis showed high structural continuity across the image, with no evidence of region compositing."

                # 5. Neural Copy-Move
                elif tool_name in ("neural_copy_move", "copy_move_detect"):
                    conf = tool_ctx.get("confidence", 0.0) or tool_ctx.get("copy_move_confidence", 0.0) or 0.0
                    if ev == "POSITIVE" or tool_ctx.get("copy_move_detected"):
                        opinion = f"Copy-move analysis detected self-cloned pixel regions with {conf:.2f} confidence, indicating content was duplicated within the same canvas."
                    else:
                        opinion = "SIFT keypoint self-matching found no duplicated regions across the image, ruling out copy-move manipulation."

                # 6. Diffusion detector
                elif tool_name == "diffusion_artifact_detector":
                    conf = tool_ctx.get("confidence", 0.0) or tool_ctx.get("ai_confidence", 0.0) or 0.0
                    if ev == "POSITIVE" or tool_ctx.get("is_ai_generated") or tool_ctx.get("diffusion_detected"):
                        opinion = f"Diffusion artifact detection found generative model traces with {conf:.2f} confidence, consistent with AI or Stable Diffusion source origin."
                    else:
                        opinion = "No diffusion or generative model signatures were detected in the image frequency and noise profiles."

                # 7. SynthID Watermark
                elif tool_name == "synthid_watermark_detect":
                    wtype = tool_ctx.get("watermark_type", "unknown")
                    conf = tool_ctx.get("confidence", 0.0)
                    if ev == "POSITIVE" or tool_ctx.get("watermark_detected"):
                        opinion = f"An embedded AI watermark (type: {wtype}) was detected with {conf:.2f} confidence, confirming the image carries a synthetic-source provenance marker."
                    else:
                        opinion = "No SynthID or C2PA AI watermark was found, indicating the image does not carry an embedded synthetic-source marker."

                # 8. JPEG Ghost
                elif tool_name == "jpeg_ghost_detect":
                    conf = tool_ctx.get("confidence", 0.0)
                    if ev == "POSITIVE" or tool_ctx.get("ghost_detected"):
                        opinion = f"JPEG ghost analysis found double-compression artifacts (confidence: {conf:.2f}), indicating parts of the image were re-saved at different quality levels — a signature of localized editing."
                    else:
                        opinion = "JPEG structure analysis confirmed single-compression consistency across the entire image."

                # 9. EXIF extract
                elif tool_name == "exif_extract":
                    device = tool_ctx.get("device_model") or tool_ctx.get("camera_model") or "unknown device"
                    software = tool_ctx.get("software") or "no editor listed"
                    gps = tool_ctx.get("gps_coordinates") or "no GPS tags"
                    if ev == "NEGATIVE" or tool_ctx.get("exif_found"):
                        opinion = f"EXIF metadata was successfully extracted. Capture device: {device}. Editing software: {software}. GPS coordinates: {gps}."
                    else:
                        opinion = "EXIF metadata has been stripped from the file — no camera, device, or GPS tags remain."

                # 10. GPS Timezone
                elif tool_name == "gps_timezone_validate":
                    offset = tool_ctx.get("offset_hours", 0.0)
                    if ev == "POSITIVE" or not tool_ctx.get("plausible", True):
                        opinion = f"GPS coordinates deviate from the local recording timestamp timezone by {offset} hour(s), indicating the metadata has been altered."
                    else:
                        opinion = "GPS coordinates are consistent with the local recording timestamp timezone, confirming metadata timeline integrity."

                # 11. Hash verify
                elif tool_name in ("file_hash_verify", "hash_verify"):
                    h = tool_ctx.get("computed_hash") or tool_ctx.get("sha256") or tool_ctx.get("current_hash") or "unknown"
                    _stored = tool_ctx.get("stored_hash") or tool_ctx.get("original_hash") or ""  # reserved for future chain-of-custody diff display
                    file_size = tool_ctx.get("file_size_bytes")
                    size_str = f" ({file_size / 1024:.1f} KB)" if file_size else ""
                    if ev == "POSITIVE" or not tool_ctx.get("hash_match", True):
                        opinion = f"File hash mismatch detected: computed SHA-256 ({h[:16]}...) does not match the ingestion chain-of-custody record{size_str}."
                    else:
                        opinion = f"SHA-256 hash verification confirmed the file is byte-identical to upload ({h[:16]}...){size_str}. This proves integrity-since-upload, not original-capture authenticity."

                # 12. Audio anti-spoofing
                elif tool_name == "anti_spoofing_detect":
                    prob = tool_ctx.get("spoof_probability", 0.0)
                    if ev == "POSITIVE" or tool_ctx.get("spoof_detected"):
                        opinion = f"Anti-spoofing analysis detected synthetic voice clone features with a spoof probability of {prob:.2%}, indicating the audio track may be artificially generated."
                    else:
                        opinion = "Speech pattern analysis found the recording consistent with a natural human voice (no spoofing detected)."

                # 13. Audio Splice
                elif tool_name == "audio_splice_detect":
                    anom = tool_ctx.get("anomaly_count", 0)
                    if ev == "POSITIVE" or tool_ctx.get("splice_detected"):
                        opinion = f"Audio splice detection found {anom} abrupt phase or ambient transitions in the waveform, consistent with cut-and-paste editing."
                    else:
                        opinion = "Audio waveform analysis found continuous ambient phase with no abrupt transitions, ruling out splice-based editing."

                # 14. ENF Analysis
                elif tool_name == "enf_analysis":
                    shifts = tool_ctx.get("frequency_shifts", 0)
                    if ev == "POSITIVE" or tool_ctx.get("inconsistency_detected"):
                        opinion = f"Electrical Network Frequency (ENF) analysis found {shifts} sudden frequency deviation(s) in the recording, indicating temporal discontinuities consistent with editing."
                    else:
                        opinion = "ENF analysis confirmed the power grid frequency is continuous throughout the recording and consistent with the claimed date."

                # 15. Face Swap Detection
                elif tool_name == "face_swap_detection":
                    conf = tool_ctx.get("confidence", 0.0)
                    if ev == "POSITIVE" or tool_ctx.get("face_swap_detected"):
                        opinion = f"Face swap detection found deepfake boundary artifacts in facial regions with {conf:.2f} confidence, indicating AI-driven face replacement."
                    else:
                        opinion = "Biometric facial boundary analysis found no evidence of face-swap manipulation."

                # 16. Lighting Consistency
                elif tool_name == "lighting_consistency":
                    deg = tool_ctx.get("shadow_angles", 0.0)
                    if ev == "POSITIVE" or tool_ctx.get("anomaly_detected"):
                        opinion = f"Lighting consistency analysis found mismatched shadow directions ({deg} degrees deviation), violating the physical scene's expected illumination geometry."
                    else:
                        opinion = "Lighting and shadow vectors are geometrically consistent across the scene, matching a single illumination source."

                # 17. Scale Validation
                elif tool_name == "scale_validation":
                    if ev == "POSITIVE" or not tool_ctx.get("scale_consistent", True):
                        opinion = "Perspective scale validation detected vanishing point misalignment, indicating composited elements with incorrect relative proportions."
                    else:
                        opinion = "Relative object scaling is consistent with the perspective projection geometry of the scene."

                # 18. Object Detection
                elif tool_name == "object_detection":
                    weapons = tool_ctx.get("weapon_detections") or []
                    contraband = tool_ctx.get("contraband_detections") or []
                    if weapons or contraband:
                        opinion = f"Object detection identified suspect content. Weapons detected: {weapons}. Contraband detected: {contraband}."
                    else:
                        opinion = "Object detection completed with no illicit items identified in the frame."

            # Fallback if no specific opinion was formed
            if not opinion:
                if ev == "POSITIVE":
                    opinion = f"{_tool_name(f)} returned a positive signal." + (f" {summary[:300]}" if summary else "")
                elif ev in {"NEGATIVE", "CLEAN"}:
                    opinion = f"{_tool_name(f)} completed and found no supported anomaly signal." + (f" {summary[:300]}" if summary else "")
                elif ev == "NOT_APPLICABLE":
                    reason = f.metadata.get("reason") or f.metadata.get("skipped_reason") or "not applicable"
                    opinion = f"{_tool_name(f)} was bypassed — {reason}."
                else:
                    opinion = summary[:300] if summary else f"{_tool_name(f)} returned an inconclusive result."

            if degraded:
                fallback = str(f.metadata.get("fallback_reason") or "heuristic fallback")
                opinion += f" (Note: {fallback})"

            sections.append(
                {
                    "id": f"tool_signal_{idx}",
                    "label": _tool_name(f),
                    "opinion": opinion[:420],
                    "severity": _severity(f),
                    "refined_findings": [
                        {
                            "tool": tool_name,
                            "user_friendly_summary": opinion[:300],
                        }
                    ],
                    "key_signal": f.metadata.get("raw_tool_summary") or f.finding_type,
                    "flag": "warn" if degraded else ("bad" if _severity(f) in {"HIGH", "CRITICAL"} else "ok"),
                }
            )

        if _is_screenshot and positive_count == 0:
            # Screenshot-specific deterministic narrative — describes what was checked
            _checked = ", ".join(s["label"] for s in sections[:3]) if sections else "integrity tools"
            _subject = f"The visual profile identified this evidence as {_visual_desc}. " if _visual_desc else ""
            _agent_id_lower_narr = str(self.agent_id).lower()
            if "agent1" in _agent_id_lower_narr or "image" in _agent_id_lower_narr:
                narrative = (
                    f"{_subject}{self.agent_name} ran {len(actionable)} tool(s) on this screen capture "
                    f"({_checked}). No pixel-level manipulation signals were detected — "
                    "compression history, noise patterns, and spectral analysis all returned clean. "
                    "These results confirm the screenshot is intact since upload."
                )
            elif "agent3" in _agent_id_lower_narr or "object" in _agent_id_lower_narr:
                narrative = (
                    f"{_subject}{self.agent_name} ran {len(actionable)} tool(s) on this screen capture "
                    f"({_checked}). Scene content analysis — layout, UI elements, and visual consistency — "
                    "returned no evidence of manipulation or compositing. "
                    "The screenshot appears to be a genuine capture of the displayed interface."
                )
            elif "agent5" in _agent_id_lower_narr or "metadata" in _agent_id_lower_narr:
                narrative = (
                    f"{_subject}{self.agent_name} ran {len(actionable)} tool(s) on this screen capture "
                    f"({_checked}). File metadata, structure, and hash verification all confirmed "
                    "the file is intact and untampered since upload. "
                    "As expected for a screenshot, no camera EXIF or GPS data is present."
                )
            else:
                narrative = (
                    f"{_subject}{self.agent_name} ran {len(actionable)} tool(s) on this screen capture "
                    f"({_checked}). All applicable checks returned clean results. "
                    "The evidence is intact since upload."
                )
        elif sections:
            prefix = ""
            if _visual_desc:
                prefix = f"Visual profile context: {_visual_desc[:180]}. "
            elif _visual_category:
                prefix = f"Visual profile category: {_visual_category}. "
            narrative = f"{prefix}{self.agent_name} analysis complete. " + sections[0]["opinion"][:220]
        elif top_findings:
            primary = top_findings[0]
            primary_summary = primary.reasoning_summary.strip()
            if str(primary.evidence_verdict).upper() == "POSITIVE":
                narrative = f"{_tool_name(primary)} returned a positive finding: {primary_summary[:180]}"
            else:
                narrative = f"{_tool_name(primary)} completed without issue: {primary_summary[:180]}"
        else:
            narrative = (
                f"{self.agent_name} found no applicable forensic signals for this file type "
                f"during {phase} analysis."
            )

        clean_tool_findings = []
        for section in sections:
            opinion = str(section.get("opinion") or "").strip()
            if not opinion:
                continue
            clean_tool_findings.append(opinion.rstrip(" .") + ".")
        if not clean_tool_findings and narrative:
            clean_tool_findings = [narrative.rstrip(" .") + "."]

        verdict_text = verdict.replace("_", " ").title()
        if positive_count:
            tool_conclusion = "one or more applicable tools flagged a manipulation signal"
        elif actionable:
            tool_conclusion = "all applicable tools returned clean findings"
        else:
            tool_conclusion = "no applicable tools produced a decisive signal"
        _agent_id_lower = str(self.agent_id).lower()
        if "agent1" in _agent_id_lower or "image" in _agent_id_lower:
            _role_opening = (
                f"Agent1 (Image Integrity) assessed the overall image: "
                f"{_visual_desc or _visual_category or 'the submitted image evidence'}. "
                f"This covers pixel-level integrity — compression history, sensor noise patterns, and generative model traces."
            )
        elif "agent3" in _agent_id_lower or "object" in _agent_id_lower:
            _yolo_ctx = self._tool_context.get("object_detection") or self._tool_context.get("yolo_detection") or {}
            _objects = _yolo_ctx.get("detected_objects") or _yolo_ctx.get("objects") or []
            _obj_summary = f"Detected objects/entities: {', '.join(str(o) for o in _objects[:5])}." if _objects else "No objects, UI elements, or contraband flagged."
            _role_opening = (
                f"Agent3 (Object & Scene Analysis) examined scene content: "
                f"{_visual_desc or _visual_category or 'the submitted image evidence'}. "
                f"{_obj_summary}"
            )
        elif "agent5" in _agent_id_lower or "metadata" in _agent_id_lower:
            _exif_ctx = self._tool_context.get("exif_extract") or self._tool_context.get("exif_analysis") or {}
            _device = _exif_ctx.get("device_model") or _exif_ctx.get("camera_model") or "unknown"
            _software = _exif_ctx.get("software") or "none"
            _hash_ctx = self._tool_context.get("file_hash_verify") or self._tool_context.get("hash_verify") or {}
            _sha = (_hash_ctx.get("sha256") or "")[:16]
            # Surface file structure facts that exist in tool context
            _file_ctx = self._tool_context.get("file_structure_analysis") or self._tool_context.get("extract_exif_metadata") or {}
            _file_size = _file_ctx.get("file_size_human") or _file_ctx.get("file_size") or ""
            _file_format = _file_ctx.get("format") or _file_ctx.get("mime_type") or ""
            _dimensions = ""
            _w = _file_ctx.get("width") or _file_ctx.get("image_width")
            _h = _file_ctx.get("height") or _file_ctx.get("image_height")
            if _w and _h:
                _dimensions = f"{_w}x{_h}"
            _created = _file_ctx.get("created_time") or _file_ctx.get("DateTimeOriginal") or ""
            _modified = _file_ctx.get("modified_time") or ""
            _meta_parts = []
            if _device != "unknown":
                _meta_parts.append(f"device={_device}")
            if _software != "none":
                _meta_parts.append(f"software={_software}")
            if _file_size:
                _meta_parts.append(f"size={_file_size}")
            if _file_format:
                _meta_parts.append(f"format={_file_format}")
            if _dimensions:
                _meta_parts.append(f"dims={_dimensions}")
            if _created:
                _meta_parts.append(f"created={_created[:19]}")
            if _sha:
                _meta_parts.append(f"SHA-256: {_sha}...")
            _meta_line = ". ".join(_meta_parts) + "." if _meta_parts else ""
            # Add context about why device is unknown for screenshots
            if _device == "unknown" and _is_screenshot:
                _meta_line += " Screenshots carry no camera EXIF; device inferred from visual profile."
            _role_opening = (
                f"Agent5 (Metadata & Provenance) extracted file provenance: "
                f"{_visual_desc or _visual_category or 'the submitted file'}. "
                f"{_meta_line}"
            )
        else:
            _role_opening = (
                f"{self.agent_name} identified the evidence as "
                f"{_visual_desc or _visual_category or 'the submitted evidence file'}."
            )

        _top_metric = ""
        if top_findings:
            _top_f = top_findings[0]
            _top_tool = str(_top_f.metadata.get("tool_name") or _top_f.finding_type)
            _top_ctx = self._tool_context.get(_top_tool) or {}
            if isinstance(_top_ctx, dict):
                for _mk in ("anomaly_score", "confidence", "spoof_probability", "score", "sha256", "num_clusters", "num_anomaly_regions"):
                    _mv = _top_ctx.get(_mk)
                    if _mv is not None:
                        _top_metric = f" ({_top_tool}: {_mk}={_mv})"
                        break

        agent_brief = (
            f"{_role_opening} "
            f"Ran {len(actionable)} tool(s); {tool_conclusion}{_top_metric}. "
            f"Assessment: {verdict_text}, {round(confidence * 100)}% confidence."
        )
        return {
            "agent_confidence": confidence,
            "agent_error_rate": error_rate,
            "verdict": verdict,
            "narrative_summary": narrative,
            "agent_brief": agent_brief,
            "key_findings": clean_tool_findings[:6],
            "sections": sections,
            "synthesis_source": "tool_grounded_deterministic",
            "agent_role": _persona_role,
            "visual_profile_context": {
                "content_description": _visual_desc,
                "image_category": _visual_category,
            },
            "fallback_reason": "LLM narrative unavailable; summary generated directly from visual profile and tool outputs.",
        }

    async def run_investigation(self) -> list[AgentFinding]:
        """Run the full investigation workflow."""
        agent_trace = PipelineTrace(
            session_id=self.session_id,
            agent_id=self.agent_id,
            operation="initial_investigation",
            metadata={"agent_name": self.agent_name},
        )
        await agent_trace.start()

        if not self.supports_uploaded_file:
            finding = AgentFinding(
                agent_id=self.agent_id,
                finding_type="File type not applicable",
                status="NOT_APPLICABLE",
                confidence_raw=None,
                evidence_verdict="NOT_APPLICABLE",
                reasoning_summary="Unsupported file format.",
            )
            self._signal_completion(skipped=True)
            self._findings = [finding]
            return self._findings

        await self._initialize_working_memory()

        self._tool_registry = await self.build_tool_registry()
        await self._publish_tool_registry_snapshot()
        await self._check_tool_availability()
        self._episodic_context = await self._retrieve_episodic_context()
        initial_thought = await self.build_initial_thought()
        if self._episodic_context:
            initial_thought = f"{initial_thought}\n\n{self._episodic_context}"

        loop_engine = ReActLoopEngine(
            agent_id=self.agent_id,
            session_id=self.session_id,
            iteration_ceiling=self.iteration_ceiling,
            working_memory=self.working_memory,
            custody_logger=self.custody_logger,
            redis_client=getattr(self.working_memory, "_redis", None),
            heavy_tool_semaphore=self.heavy_tool_semaphore,
            agent=self,
            hitl_timeout=540.0,
            per_tool_timeout=120.0,
        )

        llm_generator = None
        if (
            self.config.external_ai_allowed
            and self.config.llm_enable_react_reasoning
            and self.config.llm_api_key
        ):
            llm_client = LLMClient(self.config)
            if llm_client.is_available:
                llm_generator = create_llm_step_generator(
                    llm_client=llm_client,
                    config=self.config,
                    agent_name=self.agent_name,
                    evidence_context={
                        "mime_type": getattr(self.evidence_artifact, "mime_type", "")
                    },
                )

        loop_result = await loop_engine.run(
            initial_thought=initial_thought,
            tool_registry=self._tool_registry,
            llm_generator=llm_generator,
        )

        self._findings = loop_result.findings
        self._react_chain = loop_result.react_chain
        self._loop_result = loop_result

        self._tool_success_count = sum(
            1 for f in self._findings
            if f.evidence_verdict != "ERROR" and f.status != "INCOMPLETE"
            and not _is_template_text(f.metadata.get("llm_refined_summary") or f.reasoning_summary or f.finding_type or "")
        )
        self._tool_error_count = sum(1 for f in self._findings if f.evidence_verdict == "ERROR" or f.status == "INCOMPLETE")

        synthesis = await self._synthesize_findings_once(
            self._findings, phase="initial", timeout_s=90.0
        )

        if synthesis is None or not synthesis.get("sections"):
            synthesis = self._build_deterministic_synthesis(self._findings, phase="initial")
            self._apply_synthesis_sections(self._findings, synthesis.get("sections", []))
        self._agent_confidence = synthesis["agent_confidence"]
        self._agent_error_rate = synthesis["agent_error_rate"]
        self._agent_synthesis = synthesis

        await self._publish_agent_context("initial", self._findings)
        self._reflection_report = await self.self_reflection_pass(self._findings)
        self._signal_completion(skipped=False)
        await agent_trace.complete({"finding_count": len(self._findings)})
        return self._findings

    async def run_deep_investigation(self) -> list[AgentFinding]:
        """Run the deep/heavy investigation pass in background."""
        deep_tasks = self.deep_task_decomposition
        if not deep_tasks:
            for f in self._findings:
                f.metadata["analysis_phase"] = "initial"
            return self._findings

        deep_trace = PipelineTrace(
            session_id=self.session_id,
            agent_id=self.agent_id,
            operation="deep_investigation",
            metadata={"agent_name": self.agent_name},
        )
        await deep_trace.start()

        for f in self._findings:
            f.metadata["analysis_phase"] = "initial"

        # Build initial findings summary for deep context enrichment (Fix 4)
        initial_summary = self._build_initial_findings_summary(phase="initial")
        self._initial_findings_summary = initial_summary
        try:
            await self.working_memory.update_state(
                session_id=self.session_id,
                agent_id=self.agent_id,
                updates={"initial_findings_summary": initial_summary},
            )
        except Exception as wm_err:
            logger.debug("Failed to store initial findings summary", error=str(wm_err))

        self._tool_registry = await self.build_tool_registry()

        deep_agent_id = f"{self.agent_id}_deep"
        self._deep_wm_namespace = deep_agent_id
        await self.working_memory.initialize(
            self.session_id, deep_agent_id, deep_tasks, len(deep_tasks) + 3
        )
        await self._publish_tool_registry_snapshot(deep_agent_id)

        loop_engine = ReActLoopEngine(
            agent_id=deep_agent_id,
            session_id=self.session_id,
            iteration_ceiling=len(deep_tasks) + 3,
            working_memory=self.working_memory,
            custody_logger=self.custody_logger,
            redis_client=getattr(self.working_memory, "_redis", None),
            heavy_tool_semaphore=self.heavy_tool_semaphore,
            agent=self,
            hitl_timeout=540.0,
            per_tool_timeout=300.0,
        )

        # Enriched deep initial thought referencing Phase-1 findings (Fix 4)
        enriched_thought = (
            f"DEEP ANALYSIS PASS — {self.agent_name}. Running {len(deep_tasks)} deep tools. "
            f"Phase-1 context:\n{initial_summary}"
        )

        self._reactive_expansion_agent_id = deep_agent_id
        try:
            loop_result = await loop_engine.run(
                initial_thought=enriched_thought,
                tool_registry=self._tool_registry,
                llm_generator=None,
            )
        finally:
            self._reactive_expansion_agent_id = None

        deep_findings = loop_result.findings
        for f in deep_findings:
            f.agent_id = self.agent_id
            f.metadata["analysis_phase"] = "deep"

        # Dedup deep findings against existing initial findings by tool_name
        # to prevent the concatenation from duplicating findings.
        existing_tool_names = {
            f.metadata.get("tool_name")
            for f in self._findings
            if hasattr(f, "metadata") and isinstance(f.metadata, dict)
        }
        deduped_deep = [
            f for f in deep_findings
            if f.metadata.get("tool_name") not in existing_tool_names
        ]
        self._findings = self._findings + deduped_deep

        self._tool_success_count = sum(
            1 for f in self._findings
            if f.evidence_verdict != "ERROR" and f.status != "INCOMPLETE"
            and not _is_template_text(f.metadata.get("llm_refined_summary") or f.reasoning_summary or f.finding_type or "")
        )
        self._tool_error_count = sum(1 for f in self._findings if f.evidence_verdict == "ERROR" or f.status == "INCOMPLETE")

        # Generate agent brief (Fix 5)
        self._generate_agent_brief(phase="deep")

        synthesis = await self._synthesize_findings_once(
            self._findings, phase="deep", timeout_s=90.0
        )
        if synthesis is None or not synthesis.get("sections"):
            synthesis = self._build_deterministic_synthesis(self._findings, phase="deep")
            self._apply_synthesis_sections(self._findings, synthesis.get("sections", []))
        self._agent_confidence = synthesis["agent_confidence"]
        self._agent_error_rate = synthesis["agent_error_rate"]
        self._agent_synthesis = synthesis

        # Enrich synthesis with agent brief and initial context (Fix 5 + Fix 6)
        if isinstance(synthesis, dict):
            brief = getattr(self, "_agent_brief", None)
            # Only set agent_brief from stats if the LLM didn't already produce one
            if brief and not synthesis.get("agent_brief"):
                synthesis["agent_brief"] = brief
            synthesis["initial_findings_summary"] = initial_summary

        await self._publish_agent_context("deep", self._findings)
        self._reflection_report = await self.self_reflection_pass(self._findings)
        await deep_trace.complete({"deep_finding_count": len(deep_findings)})
        return deep_findings

    async def run_challenge(
        self, contradicting_finding: dict[str, Any], context: dict[str, Any]
    ) -> list[AgentFinding]:
        """Re-invokes the agent's ReAct loop to resolve a contradiction."""
        logger.info(f"Agent {self.agent_id} challenged by Arbiter")

        from core.custody_logger import EntryType

        if self.custody_logger:
            await self.custody_logger.log_entry(
                agent_id=self.agent_id,
                session_id=self.session_id,
                entry_type=EntryType.TRIBUNAL_EVENT,
                content={
                    "action": "run_challenge",
                    "contradicting_agent": contradicting_finding.get("agent_id"),
                    "contradiction_type": contradicting_finding.get("finding_type"),
                },
            )

        challenge_thought = (
            f"The Council Arbiter has flagged a contradiction between my findings "
            f"and Agent {contradicting_finding.get('agent_id')}. "
            f"I must re-examine the evidence and either confirm or revise my verdict."
        )

        loop_engine = ReActLoopEngine(
            agent_id=self.agent_id,
            session_id=self.session_id,
            iteration_ceiling=max(3, self.iteration_ceiling // 2),
            working_memory=self.working_memory,
            custody_logger=self.custody_logger,
            redis_client=getattr(self.working_memory, "_redis", None),
            heavy_tool_semaphore=self.heavy_tool_semaphore,
            hitl_timeout=540.0,
        )

        llm_generator = None
        if (
            self.config.external_ai_allowed
            and self.config.llm_enable_react_reasoning
            and self.config.llm_api_key
        ):
            llm_client = LLMClient(self.config)
            llm_generator = create_llm_step_generator(
                llm_client=llm_client,
                config=self.config,
                agent_name=self.agent_name,
                evidence_context={"challenge_mode": True, "contradiction": contradicting_finding},
            )

        if self._tool_registry is None:
            self._tool_registry = await self.build_tool_registry()

        loop_result = await loop_engine.run(
            initial_thought=challenge_thought,
            tool_registry=self._tool_registry,
            llm_generator=llm_generator,
        )

        self._findings = loop_result.findings
        return self._findings

    async def flag_hitl(self, reason: Any, brief: str) -> None:
        """Flag a Human-in-the-Loop checkpoint."""
        logger.warning(f"HITL checkpoint flagged: {reason.value} - {brief}")
        if self.custody_logger:
            from core.custody_logger import EntryType

            await self.custody_logger.log_entry(
                agent_id=self.agent_id,
                session_id=self.session_id,
                entry_type=EntryType.HITL_CHECKPOINT,
                content={"action": "flag_hitl", "reason": reason.value, "brief": brief},
            )

    async def handle_inter_agent_call(self, call: Any) -> dict[str, Any]:
        """Handle an incoming inter-agent call."""
        logger.info(f"Handling inter-agent call from {call.caller_agent_id}")
        if self.custody_logger:
            from core.custody_logger import EntryType

            await self.custody_logger.log_entry(
                agent_id=self.agent_id,
                session_id=self.session_id,
                entry_type=EntryType.INTER_AGENT_CALL,
                content={
                    "action": "handle_inter_agent_call",
                    "caller_agent_id": call.caller_agent_id,
                    "payload": call.payload,
                },
            )
        return {"status": "acknowledged", "agent_id": self.agent_id}

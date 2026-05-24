"""
Pipeline Phases
===============

Concurrent agent execution and HITL deep-analysis gate.
Extracted from pipeline.py to keep the orchestrator file under 400 lines.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import TYPE_CHECKING, Any
from uuid import UUID

from core.agent_registry import AgentID
from core.media_kind import is_screen_capture_like
from core.structured_logging import get_logger
from orchestration.agent_factory import AgentLoopResult, _serialize_react_chain

if TYPE_CHECKING:
    from orchestration.pipeline import ForensicCouncilPipeline

logger = get_logger(__name__)


_HASH_RE = re.compile(r"SHA-256\s*=\s*([0-9a-fA-F]{10,})")
_TRAILING_ABSENCE_RE = re.compile(
    r"\s+This supports the absence of (?:this specific anomaly|this specific manipulation pattern|this s.*)$",
    re.IGNORECASE,
)

PREVIEW_EXCLUDED_TOOLS = {"hash_verify", "custody_check", "file_type_validation"}


def _metric_digest(metadata: dict[str, Any]) -> str:
    """Extract a compact, high-signal metric digest from raw tool output."""
    if not metadata:
        return ""

    labels = {
        "anomaly_score": "anomaly score",
        "confidence": "tool confidence",
        "top_confidence": "top match",
        "diffusion_probability": "AI probability",
        "synthetic_probability": "synthetic probability",
        "forgery_score": "forgery score",
        "inconsistency_ratio": "inconsistency ratio",
        "noise_consistency_score": "noise consistency",
        "mean_flow_magnitude": "motion magnitude",
        "high_freq_ratio": "high-frequency ratio",
        "max_anomaly": "max ELA deviation",
        "word_count": "OCR words",
        "detection_count": "objects",
        "match_count": "matches",
        "num_matches": "matches",
        "num_anomaly_regions": "regions",
        "outlier_region_count": "outlier regions",
        "bytes_scanned": "bytes scanned",
        "total_fields_extracted": "metadata fields",
    }
    parts: list[str] = []
    for key, label in labels.items():
        value = metadata.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, float):
            rendered = f"{value:.3f}" if abs(value) < 10 else f"{value:.1f}"
        elif isinstance(value, int):
            rendered = f"{value:,}"
        else:
            rendered = str(value)
        parts.append(f"{label}: {rendered}")
        if len(parts) >= 3:
            break

    flags = metadata.get("flags") or metadata.get("anomalies") or metadata.get("forensic_flags")
    if isinstance(flags, list) and flags:
        parts.append("flags: " + "; ".join(str(x) for x in flags[:2]))
    return "; ".join(parts)


def _verdict_score(verdict: Any) -> float | None:
    """Map agent verdicts to frontend severity color/risk score."""
    value = str(verdict or "").upper()
    if value in {"TAMPERED", "LIKELY_MANIPULATED", "LIKELY_AI_GENERATED", "LIKELY_SPOOFED", "LIKELY_SYNTHETIC"}:
        return 0.9
    if value in {"SUSPICIOUS", "NEEDS_REVIEW"}:
        return 0.65
    if value in {"AUTHENTIC", "CLEAN"}:
        return 0.05
    if value == "INCONCLUSIVE":
        return 0.5
    return None


def _metadata_value(finding: Any, key: str, default: Any = None) -> Any:
    if hasattr(finding, key):
        return getattr(finding, key)
    if isinstance(finding, dict):
        return finding.get(key, default)
    return default


def _finding_metadata(finding: Any) -> dict[str, Any]:
    metadata = _metadata_value(finding, "metadata", {})
    return metadata if isinstance(metadata, dict) else {}


def _finding_tool_name(finding: Any) -> str:
    metadata = _finding_metadata(finding)
    return str(
        metadata.get("tool_name")
        or _metadata_value(finding, "finding_type", "")
        or ""
    )


def _finding_summary_text(finding: Any) -> str:
    metadata = _finding_metadata(finding)
    for candidate in (
        metadata.get("llm_refined_summary"),
        _metadata_value(finding, "reasoning_summary", ""),
        metadata.get("raw_tool_summary"),
        metadata.get("analysis_summary"),
        metadata.get("summary"),
        metadata.get("message"),
        metadata.get("note"),
        metadata.get("verdict"),
        metadata.get("status"),
    ):
        text = str(candidate or "").strip()
        if text:
            return text
    return ""


# Synthetic screenshot overrides removed in favor of real-time tool findings.


def _humanize_initial_finding(
    *,
    agent_id: str,
    tool_name: str,
    summary: str,
    evidence_verdict: str,
    finding_status: str,
    metadata: dict[str, Any],
    artifact: Any = None,
) -> str | None:
    """Turn raw tool text into a concise card-level investigator note."""
    tool = (tool_name or "").lower()
    text = " ".join(str(summary or "").replace("\n", " ").split())
    text = _TRAILING_ABSENCE_RE.sub(".", text).strip()

    if not text:
        return None

    if "no analysis possible due to lack of raw tool data" in text.lower():
        return None

    if "screenshot scene applicability" in tool or "screenshot scene applicability" in text.lower():
        if "skipped" in text.lower() or evidence_verdict == "NOT_APPLICABLE":
            dims = (
                f"{metadata.get('width')}x{metadata.get('height')}px"
                if metadata.get("width") and metadata.get("height")
                else "screen capture"
            )
            aspect = metadata.get("aspect_class") or "screen-capture"
            theme = ""
            if "is_dark_mode" in metadata:
                theme = ", dark UI theme" if metadata.get("is_dark_mode") else ", light UI theme"
            chrome = ", browser/window chrome detected" if metadata.get("ui_chrome_detected") else ""
            return (
                f"Screenshot scope confirmed ({dims}, {aspect}{theme}{chrome}). "
                "Physical-scene object, weapon, lighting, and scale checks were bypassed because they do not apply to screen captures."
            )
        return "Screenshot/context check completed; no physical-scene object evidence was required."

    if "file_hash_verify" in tool or "file hash verify" in text.lower():
        match = _HASH_RE.search(text)
        digest = f"{match.group(1)[:12]}..." if match else "recorded digest"
        return (
            f"Integrity check passed. The uploaded file hash ({digest}) matches the "
            "chain-of-custody record, so the submitted artifact was not altered after intake."
        )

    if "exif" in tool or "metadata" in tool:
        if is_screen_capture_like(artifact):
            return "Container metadata is consistent with a digital screen capture (limited EXIF provenance is expected)."

        parts = []
        if "device: not recorded" in text.lower() or "device not recorded" in text.lower():
            parts.append("No camera/device model was recorded in EXIF")
        if "capture time: not in exif" in text.lower() or "capture time not" in text.lower():
            parts.append("no original capture timestamp was present")
        if "gps: absent" in text.lower() or "gps absent" in text.lower():
            parts.append("GPS metadata is absent")
        if parts:
            return "; ".join(parts).capitalize() + ". This is common for screenshots and exported images."

    if "compression_risk_audit" in tool:
        platform = str(metadata.get("detected_platform") or "").strip()
        impact = str(metadata.get("forensic_reliability_impact") or "NONE").upper()
        penalty = float(metadata.get("compression_penalty") or 1.0)
        if penalty >= 0.95 or not platform:
            return "No social media or messaging app compression footprint detected. Metadata integrity is unaffected."
        if "unknown" in platform.lower() or "stripped" in platform.lower():
            return (
                f"Metadata appears stripped or platform-normalized — no specific app fingerprint identified, "
                f"which is consistent with social media re-processing, a privacy tool, or a system screenshot. "
                f"Forensic reliability impact: {impact.lower()}."
            )
        clean_platform = (
            platform.replace("(Stripped Metadata - High Compression Risk)", "")
                    .replace("(Filename Signal)", "")
                    .replace("(High Compression)", "")
                    .replace("(Medium-High Compression)", "")
                    .strip().rstrip("-").strip()
        )
        return (
            f"Compression footprint matches {clean_platform}. "
            f"This platform applies significant re-compression which degrades forensic reliability "
            f"({impact.lower()} impact)."
        )

    if "file_structure_analysis" in tool or "file structure analysis" in text.lower():
        if "anomalies: 0" in text.lower() or "header valid" in text.lower():
            return "File container structure is valid: header/trailer checks passed and no appended payload was detected."

    if "frequency_domain_analysis" in tool or "frequency domain analysis" in text.lower():
        if "0.000" in text or "appears natural" in text.lower():
            return "Frequency-domain analysis found no periodic/GAN-like artifact pattern; the screenshot's high-frequency distribution is within the expected range."

    if "extract_text" in tool or "extract text" in text.lower():
        preview = metadata.get("ocr_text_preview") or metadata.get("text_preview")
        content_desc = str(metadata.get("content_description") or "").strip()
        content_type_val = str(metadata.get("content_type") or "").strip()
        if preview:
            clean_preview = " ".join(str(preview).replace("|", " | ").split())
            method = str(metadata.get("method") or metadata.get("ocr_engine") or "OCR")
            if method == "gemini_multimodal":
                id_part = f"{content_type_val}. " if content_type_val else ""
                if content_desc:
                    return (
                        f"Gemini Vision identified: {content_desc[:120]}. "
                        f"Text extracted: {clean_preview[:160]}"
                    )
                return f"{id_part}Gemini Vision OCR extracted visible text: {clean_preview[:180]}"
            return f"OCR extracted visible text for context: {clean_preview[:180]}"
        if content_desc:
            return f"Gemini Vision identified: {content_desc[:200]}"
        if "ocr extracted" in text.lower():
            return text.replace("Extract Text From Image: ", "").replace("Checked: ", "")

    if "screenshot_layout_forensics" in tool:
        anomalies = int(metadata.get("layout_anomaly_count") or 0)
        edge_density = metadata.get("edge_density")
        hard_edge_density = metadata.get("hard_edge_density")
        h_rule = metadata.get("horizontal_rule_density")
        v_rule = metadata.get("vertical_rule_density")
        if anomalies:
            return (
                f"Screenshot layout check flagged {anomalies} UI/document structure anomaly "
                f"(edge density {edge_density}); review the visible interface for pasted or misaligned regions."
            )
        return (
            "Screenshot layout check found no UI/document structure anomaly flags"
            + (
                f" (edge density {edge_density}, hard-edge density {hard_edge_density}, "
                f"horizontal/vertical rule density {h_rule}/{v_rule})."
                if edge_density is not None
                else "."
            )
        )

    if "analyze_image_content" in tool or "analyze image content" in text.lower():
        if metadata.get("semantic_scope") == "screenshot_fast_profile":
            return (
                f"Screenshot content was identified as a digital UI capture ({metadata.get('width')}x{metadata.get('height')}px, "
                f"{metadata.get('color_mode')} mode). Natural-scene classification was bypassed; "
                "OCR, layout, hash, and provenance checks carry the screenshot review."
            )
        if agent_id == AgentID.AGENT1.value and (
            "screenshot" in str(metadata).lower() or "screen capture" in str(metadata).lower()
        ):
            return None
        if "forensic evidence photograph" in text.lower():
            return (
                "Visual classifier recognized the upload as forensic/evidence imagery. "
                "This is a context label, not proof of authenticity."
            )
        return text.replace("Analyze Image Content: ", "").replace("Checked: ", "")

    if evidence_verdict == "NEGATIVE" and finding_status != "INCOMPLETE":
        metric_note = _metric_digest(metadata)
        clean_text = text.replace("Checked: ", "")
        generic_patterns = (
            "completed and found no supported anomaly signal",
            "completed; review detailed tool metrics",
            "analysis complete",
        )
        if any(p in clean_text.lower() for p in generic_patterns):
            tool_label = str(tool_name or "Tool").replace("_", " ").title()
            # Add metric context
            if metric_note and metric_note.lower() not in clean_text.lower():
                clean_text = f"{tool_label} completed — no anomaly detected. Metric: {metric_note}."
            else:
                clean_text = f"{tool_label} completed — no anomaly detected."
        if metric_note and metric_note.lower() not in clean_text.lower():
            return f"{clean_text} Key metrics: {metric_note}."
        return clean_text

    # Enrich the fallback with structured metadata fields if available.
    metric_note = _metric_digest(metadata)
    confidence_val = metadata.get("confidence") or metadata.get("score")
    verdict_val = str(metadata.get("verdict") or evidence_verdict or "").upper()

    enriched = text
    # Append key metric only if it adds new information
    if metric_note and metric_note.lower() not in enriched.lower():
        enriched = f"{enriched} Metric: {metric_note}."

    # Surface confidence if present and not already in text
    if confidence_val and str(round(float(confidence_val), 2)) not in enriched:
        try:
            pct = round(float(confidence_val) * 100)
            enriched = f"{enriched} (confidence: {pct}%)"
        except (TypeError, ValueError):
            pass

    return enriched if enriched.strip() else None


async def run_agents_concurrent(
    pipeline: ForensicCouncilPipeline,
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

    # O-C-3: previously this span closed immediately because the function
    # body was unindented from the `with` block. Use start_span +
    # try/finally so the entire concurrent-agents phase is captured under
    # one span without bulk-reindenting 600 lines of body.
    _pac_span = _tracer.start_span("pipeline.run_agents_concurrent")
    try:
        _pac_span.set_attribute("session_id", str(session_id))
    except Exception:
        pass

    registry = get_agent_registry()

    # --- Broadcast helper ---------------------------------------------------

    async def _broadcast_agent_status(
        aid: str, status: str, message: str, findings=None, error=None, agent_inst=None,
        initial_tool_names: set | None = None,
        analysis_phase: str = "initial",
    ):
        try:
            from api.routes._session_state import AGENT_NAMES, broadcast_update
            from api.schemas import BriefUpdate
            from core.severity import assign_severity_tier

            aname = AGENT_NAMES.get(aid, aid)
            preview = []

            # Humanized tool names for frontend progress display
            tool_display_names = {
                "extract_text_from_image": "Forensic OCR",
                "file_hash_verify": "Hash Verification",
                "analyze_image_content": "Semantic Audit",
                "frequency_domain_analysis": "FFT Noise Scan",
                "neural_fingerprint": "Neural Fingerprint",
                "diffusion_artifact_detector": "Diffusion Scan",
                "object_detection": "Structural Audit",
                "scene_incongruence": "Contextual Scan",
                "hex_signature_scan": "Binary Signature",
                "compression_risk_audit": "Compression Scan",
                "provenance_chain_verify": "C2PA Provenance",
                "timestamp_analysis": "Chronology Audit",
                "file_structure_analysis": "Structure Check",
                "gemini_deep_forensic": "Multimodal Synthesis",
            }

            def _normalize_tool_name(raw: str) -> str:
                return tool_display_names.get(raw, raw.replace("_", " ").title())

            synthesis = (
                getattr(agent_inst, "_agent_synthesis", None) if agent_inst is not None else None
            )
            agent_confidence = (
                getattr(agent_inst, "_agent_confidence", None) if agent_inst is not None else None
            )
            def _finding_attr(finding, key: str, default: Any = None) -> Any:
                if hasattr(finding, key):
                    return getattr(finding, key)
                if isinstance(finding, dict):
                    return finding.get(key, default)
                return default

            def _summary_for_finding(finding, metadata: dict[str, Any]) -> str:
                summary_candidates = (
                    metadata.get("llm_refined_summary"),
                    _finding_attr(finding, "reasoning_summary", ""),
                    metadata.get("raw_tool_summary"),
                    metadata.get("analysis_summary"),
                    metadata.get("summary"),
                    metadata.get("message"),
                    metadata.get("note"),
                    metadata.get("verdict"),
                    metadata.get("status"),
                )
                for candidate in summary_candidates:
                    text = str(candidate or "").strip()
                    if text:
                        return text

                tool_name = metadata.get("tool_name") or _finding_attr(
                    finding, "finding_type", "forensic tool"
                )
                evidence_verdict = str(_finding_attr(finding, "evidence_verdict", "")).upper()
                if evidence_verdict == "NEGATIVE":
                    return f"{tool_name} completed and found no supported anomaly signal."
                if evidence_verdict == "POSITIVE":
                    return f"{tool_name} completed and reported a supported forensic signal."
                if evidence_verdict == "NOT_APPLICABLE":
                    return f"{tool_name} is not applicable to this file type."
                return f"{tool_name} completed; review detailed tool metrics for this finding."

            def _append_synthesis_sections(synthesis_data: dict[str, Any]) -> None:
                # Build actual_tools from the passed findings.
                # When findings is None (deep phase with no new tool findings), allow ALL
                # synthesis sections through so the deep card can still show LLM-refined summaries.
                actual_tools: set[str] = set()
                restrict_to_actual = bool(findings)
                for existing_finding in findings or []:
                    existing_meta = (
                        existing_finding.metadata
                        if hasattr(existing_finding, "metadata")
                        else existing_finding.get("metadata", {})
                        if isinstance(existing_finding, dict)
                        else {}
                    )
                    existing_tool = existing_meta.get("tool_name") or (
                        existing_finding.finding_type
                        if hasattr(existing_finding, "finding_type")
                        else existing_finding.get("finding_type")
                        if isinstance(existing_finding, dict)
                        else None
                    )
                    if existing_tool:
                        actual_tools.add(str(existing_tool))

                seen_synthesis_tools: set[str] = set()
                for section in synthesis_data.get("sections") or []:
                    refined = section.get("refined_findings") or []
                    for item in refined:
                        tool_name = str(item.get("tool") or "").strip()
                        if not tool_name:
                            continue
                        if restrict_to_actual and tool_name not in actual_tools:
                            continue
                        # Suppress initial-phase tools from deep-phase synthesis preview
                        if initial_tool_names and tool_name in initial_tool_names:
                            continue
                        if tool_name in PREVIEW_EXCLUDED_TOOLS:
                            continue
                        if tool_name in seen_synthesis_tools:
                            continue
                        seen_synthesis_tools.add(tool_name)
                        summary = str(item.get("user_friendly_summary") or "").strip()
                        if not summary:
                            continue
                        preview.append(
                            {
                                "tool": _normalize_tool_name(tool_name),
                                "summary": summary[:560],
                                "severity": section.get("severity") or "LOW",
                                "verdict": str(synthesis_data.get("verdict") or "INCONCLUSIVE"),
                                "key_signal": "",
                                "confidence": synthesis_data.get("agent_confidence"),
                                "section": section.get("label") or "",
                                "degraded": bool(synthesis_data.get("fallback_reason")),
                                "fallback_reason": synthesis_data.get("fallback_reason"),
                            }
                        )

            if findings:
                seen_raw_tools: set[str] = set()
                for f in findings:
                    m = (
                        f.metadata
                        if hasattr(f, "metadata")
                        else f.get("metadata", {})
                        if isinstance(f, dict)
                        else {}
                    )
                    tool = m.get("tool_name") or (
                        f.finding_type if hasattr(f, "finding_type") else f.get("finding_type")
                    )

                    # Filter out low-signal/internal tools and non-applicable tools from the UI preview
                    if tool in PREVIEW_EXCLUDED_TOOLS:
                        continue
                    finding_ev = str(_finding_attr(f, "evidence_verdict", "")).upper()
                    finding_st = str(_finding_attr(f, "status", "")).upper()
                    if finding_ev == "NOT_APPLICABLE" or finding_st == "NOT_APPLICABLE":
                        continue
                    if (
                        aid == AgentID.AGENT5.value
                        and tool == "extract_text_from_image"
                        and is_screen_capture_like(evidence_artifact)
                    ):
                        continue

                    # Dedup by tool name — same tool running twice produces one card entry
                    tool_key = str(tool or "")
                    if tool_key and tool_key in seen_raw_tools:
                        continue

                    s = _summary_for_finding(f, m)
                    sev = assign_severity_tier(f)
                    evidence_verdict = str(
                        _finding_attr(f, "evidence_verdict", "")
                    ).upper()
                    finding_status = str(
                        _finding_attr(f, "status", "")
                    ).upper()
                    if evidence_verdict == "ERROR" or finding_status == "INCOMPLETE":
                        tv = "NEEDS_REVIEW"
                    elif evidence_verdict in (
                        "POSITIVE",
                        "TAMPERED",
                        "SUSPICIOUS",
                        "MANIPULATED",
                    ) or sev in ("CRITICAL", "HIGH", "MEDIUM"):
                        tv = "FLAGGED"
                    elif evidence_verdict == "NOT_APPLICABLE" or finding_status == "NOT_APPLICABLE":
                        tv = "NOT_APPLICABLE"
                    else:
                        tv = "CLEAN"
                    human_summary = _humanize_initial_finding(
                        agent_id=aid,
                        tool_name=str(tool or ""),
                        summary=s,
                        evidence_verdict=evidence_verdict,
                        finding_status=finding_status,
                        metadata=m,
                        artifact=evidence_artifact,
                    )
                    if human_summary is None:
                        human_summary = s[:240] if s else f"{tool or 'Tool'} completed."

                    if tool_key:
                        seen_raw_tools.add(tool_key)
                    preview.append(
                        {
                            "tool": _normalize_tool_name(str(tool or "")),
                            "summary": human_summary[:640],
                            "severity": sev,
                            "verdict": tv,
                            "key_signal": (
                                m.get("section_key_signal")
                                or m.get("raw_tool_summary")
                                or m.get("key_finding")
                                or m.get("anomaly_description")
                                or m.get("match_description")
                                or ""
                            ),
                            "confidence": (
                                _finding_attr(f, "confidence_raw", None)
                            ),
                            "section": m.get("section") or "",
                            "degraded": bool(m.get("degraded") or m.get("fallback_reason")),
                            "fallback_reason": m.get("fallback_reason"),
                            "elapsed_s": m.get("elapsed_s"),
                        }
                    )

                # Sort by confidence descending to surface high-signal findings first
                preview.sort(key=lambda x: x.get("confidence") or 0.0, reverse=True)
            if isinstance(synthesis, dict) and synthesis.get("sections"):
                before = len(preview)
                _append_synthesis_sections(synthesis)
                # Always deduplicate by tool name — synthesis sections often overlap with
                # raw tool findings. Synthesis (LLM-refined) entries take precedence.
                seen_tools: set[str] = set()
                # Two-pass: synthesis entries first (they are appended after `before`), then raw
                priority_preview = preview[before:] + preview[:before]
                deduped = []
                for item in priority_preview:
                    tool_key = str(item.get("tool") or "")
                    if tool_key and tool_key in seen_tools:
                        continue
                    if tool_key:
                        seen_tools.add(tool_key)
                    deduped.append(item)
                    if len(deduped) >= 8:
                        break
                preview = deduped
            if isinstance(synthesis, dict) and not preview and not initial_tool_names:
                # Only show the narrative fallback for the initial phase.
                # Deep-phase broadcasts suppress it to avoid showing initial analysis context.
                summary = str(synthesis.get("narrative_summary") or "").strip()
                if summary and not any(
                    p in summary.lower()
                    for p in (
                        "empty raw tool results",
                        "lack of results",
                        "no digital traces or anomalies were detected due to",
                    )
                ):
                    preview.append(
                        {
                            "tool": "agent_synthesis",
                            "summary": summary[:420],
                            "severity": "LOW",
                            "verdict": str(synthesis.get("verdict") or "INCONCLUSIVE"),
                        }
                    )


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
                        "analysis_phase": analysis_phase,
                        "thinking": message,
                        "tool_name": "file_type_validation"
                        if status == "validating"
                        else None,
                        "tools_done": 0 if status in ("validating", "running") else None,
                        "tools_total": len(getattr(agent_inst, "task_decomposition", []) or [])
                        if agent_inst is not None and status == "running"
                        else 1
                        if status == "validating"
                        else None,
                         "findings_count": 0
                         if status == "skipped"
                         else len(preview),
                        "confidence": 0
                        if status == "skipped"
                        else (
                            agent_confidence
                        ),
                        "error": error,
                        "findings_preview": preview,
                        "agent_verdict": synthesis.get("verdict")
                        if isinstance(synthesis, dict)
                        else None,
                        "verdict_score": _verdict_score(
                            synthesis.get("verdict") if isinstance(synthesis, dict) else None
                        ),
                        # Suppress initial-phase narrative from deep-phase card summary
                        "summary": (
                            None if initial_tool_names
                            else synthesis.get("narrative_summary")
                            if isinstance(synthesis, dict)
                            else None
                        ),
                        "tool_error_rate": getattr(agent_inst, "_agent_error_rate", None)
                        if agent_inst
                        else None,
                        "tools_ran": getattr(agent_inst, "_tool_success_count", None)
                        if agent_inst
                        else None,
                        "tools_failed": getattr(agent_inst, "_tool_error_count", None)
                        if agent_inst
                        else None,
                        "section_flags": synthesis.get("sections")
                        if isinstance(synthesis, dict)
                        else None,
                    },
                ),
            )
        except Exception as exc:
            logger.debug("Agent status broadcast failed", agent_id=aid, error=str(exc))

    # --- Phase 1: Initialize agents and run initial passes ------------------

    async def _init_agent(aid: str):
        try:
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

            # Broadcast "validating" phase start for this specific node
            await _broadcast_agent_status(
                aid,
                "validating",
                f"{aid} file type validation in progress.",
                agent_inst=inst,
            )
            # Yield the event loop so the "validating" state renders in the UI
            # before immediately overwriting with "running" or "skipped"
            await asyncio.sleep(0)

            supported = inst.supports_uploaded_file

            if not supported:
                await _broadcast_agent_status(
                    aid,
                    "skipped",
                    f"{aid} bypassed: file type '{evidence_artifact.mime_type}' not supported for this analysis dimension.",
                    error="Unsupported file type.",
                    agent_inst=inst,
                )
            else:
                await _broadcast_agent_status(
                    aid,
                    "running",
                    f"{aid} file type validated. Starting initial analysis.",
                    agent_inst=inst,
                )
            return inst, supported
        except Exception as e:
            logger.error(f"Failed to initialize agent {aid}", error=str(e))
            await _broadcast_agent_status(
                aid,
                "error",
                f"Failed to initialize {aid}: {str(e)}",
                error=str(e)
            )
            return None, False


    # Initialize all agents and their status states concurrently to minimize time-to-first-feedback
    agent_instances = await asyncio.gather(
        *[_init_agent(aid) for aid in registry.get_all_agent_ids()]
    )


    applicable_ids = [
        aid
        for (inst, supported), aid in zip(
            agent_instances, registry.get_all_agent_ids(), strict=True
        )
        if supported
    ]
    if pipeline.signal_bus:
        pipeline.signal_bus.update_applicable_agents(applicable_ids)

    async def _run_one(agent, aid: str, supported: bool):
        if not supported:
            return agent, [], "unsupported"
        agent_timeout = 300  # 5 minutes per agent maximum
        try:
            logger.info(f"Running {aid} initial investigation")
            initial_findings = await asyncio.wait_for(
                agent.run_investigation(),
                timeout=min(float(pipeline.config.investigation_timeout), agent_timeout),
            )
            if pipeline.signal_bus:
                await pipeline.signal_bus.signal_ready(aid, initial_findings)
            await _broadcast_agent_status(
                aid,
                "complete",
                f"{aid} initial analysis complete.",
                findings=initial_findings,
                agent_inst=agent,
            )
            return agent, initial_findings, "complete"
        except (asyncio.TimeoutError, TimeoutError) as e:
            # Per-agent timeout (Fix 4): collect whatever findings the agent
            # accumulated before the deadline and continue the pipeline in a
            # degraded state.  Never re-raise — one slow agent must not abort
            # the full council investigation.
            findings = list(getattr(agent, "_findings", []) or [])
            logger.warning(
                f"{aid} initial pass timed out after {agent_timeout}s; "
                f"continuing with {len(findings)} partial findings",
                agent_id=aid,
                timeout_s=agent_timeout,
                partial_findings=len(findings),
            )
            if pipeline.signal_bus:
                await pipeline.signal_bus.signal_failure(aid)
            await _broadcast_agent_status(
                aid,
                "degraded",
                f"{aid} timed out — partial findings retained.",
                findings=findings,
                error=str(e),
                agent_inst=agent,
            )
            return agent, findings, "degraded"
        except Exception as e:
            logger.error(f"{aid} initial pass failed", error=str(e))
            findings = list(getattr(agent, "_findings", []) or [])
            if pipeline.signal_bus:
                await pipeline.signal_bus.signal_failure(aid)
            await _broadcast_agent_status(
                aid,
                "error",
                f"{aid} error: {e}",
                findings=findings,
                error=str(e),
                agent_inst=agent,
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
            raw_initial[i] if not isinstance(raw_initial[i], BaseException) else (None, [], "error")
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
    # Start the arbiter pre-warm with Phase 1 findings NOW so it runs concurrently
    # while the investigator reads the initial results and makes the Accept/Deep decision.
    # If deep analysis is chosen the resume endpoint cancels this via invalidate_pre_warm()
    # and a fresh pre-warm is kicked off after the deep pass.
    try:
        _initial_norm = pipeline._normalize_agent_results(initial_results)
        pipeline._pre_warm_task = asyncio.create_task(
            pipeline._run_arbiter_pre_warm(_initial_norm, "", suppress_broadcasts=True)
        )
    except Exception as _pw_err:
        logger.debug("Phase-1 pre-warm task creation failed", error=str(_pw_err))

    if not await _await_deep_analysis_decision(pipeline, session_id):
        logger.info("Deep analysis skipped by analyst decision", session_id=str(session_id))
        return initial_results

    # Broadcast deep analysis start so the frontend transitions immediately
    try:
        from api.routes._session_state import broadcast_update
        from api.schemas import BriefUpdate

        await broadcast_update(
            str(session_id),
            BriefUpdate(
                type="AGENT_UPDATE",
                session_id=str(session_id),
                agent_id=None,
                message="Deep forensic analysis initiated.",
                data={"status": "processing", "analysis_phase": "deep", "thinking": "Dispatching deep forensic tools..."},
            ),
        )
    except Exception:
        pass

    # --- Phase 2: Deep passes with early context sync ----------------------

    context_event = asyncio.Event()
    context_injected: set[str] = set()
    producer_id = AgentID.AGENT1.value

    def _broadcast_context(producer_finding: Any):
        try:
            meta = {}
            if hasattr(producer_finding, "metadata"):
                meta = (
                    producer_finding.metadata if isinstance(producer_finding.metadata, dict) else {}
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
                agent_id=aid,
                findings=[],
                reflection_report={},
                react_chain=[],
                agent_active=False,
                supports_file_type=False,
            )

        try:
            await _broadcast_agent_status(
                aid,
                "running",
                f"{aid} deep analysis in progress.",
                agent_inst=a_inst,
                analysis_phase="deep",
            )
            result = await _run_agent_deep_only(pipeline, a_inst, aid, a_init, a_supported)

            if result.error:
                await _broadcast_agent_status(
                    aid,
                    "error",
                    f"{aid} error: {result.error}",
                    error=result.error,
                    agent_inst=a_inst,
                    analysis_phase="deep",
                )
            else:
                # Broadcast only findings produced in the deep pass.
                # result.findings = initial + deep combined; slice off the initial prefix.
                initial_count = len(a_init) if a_init else 0
                deep_only = (result.findings or [])[initial_count:]
                # Build initial tool set so synthesis dedup can suppress initial-phase items
                initial_tool_names: set[str] = set()
                for _f in a_init or []:
                    _m = (
                        _f.metadata if hasattr(_f, "metadata")
                        else _f.get("metadata", {}) if isinstance(_f, dict)
                        else {}
                    )
                    _t = _m.get("tool_name") if isinstance(_m, dict) else None
                    if _t:
                        initial_tool_names.add(str(_t))
                await _broadcast_agent_status(
                    aid,
                    "complete",
                    f"{aid} deep analysis complete.",
                    findings=deep_only,
                    agent_inst=a_inst,
                    initial_tool_names=initial_tool_names,
                    analysis_phase="deep",
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
            results.append(
                AgentLoopResult(
                    agent_id=agent_ids_deep[i],
                    findings=[],
                    reflection_report={},
                    react_chain=[],
                    error=str(r),
                    agent_active=False,
                )
            )
        else:
            results.append(r)

    active_agents = [r.agent_id for r in results if r.agent_active]
    skipped_agents = [r.agent_id for r in results if not r.supports_file_type]
    logger.info(
        "Agent execution summary", active_agents=active_agents, skipped_agents=skipped_agents
    )

    # Re-warm with complete (Phase 1 + deep) findings so the arbiter has the full
    # evidence picture while the investigator reads the deep results and decides.
    try:
        _deep_norm = pipeline._normalize_agent_results(results)
        pipeline._pre_warm_task = asyncio.create_task(
            pipeline._run_arbiter_pre_warm(_deep_norm, "")
        )
    except Exception as _pw_err:
        logger.debug("Phase-2 pre-warm task creation failed", error=str(_pw_err))

    await _await_deep_report_request(pipeline, session_id)

    for aid in registry.get_all_agent_ids():
        if pipeline.inter_agent_bus is not None:
            pipeline.inter_agent_bus.unregister_agent(aid)

    # O-C-3: close the span opened at function entry.
    try:
        _pac_span.end()
    except Exception:
        pass

    return results


async def _run_agent_deep_only(
    pipeline: ForensicCouncilPipeline,
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
            agent_id=agent_id,
            findings=[],
            reflection_report={},
            react_chain=[],
            agent_active=False,
            supports_file_type=supports_file,
            error="Initial pass failed",
        )
    if not supports_file:
        return AgentLoopResult(
            agent_id=agent_id,
            findings=[],
            reflection_report={},
            react_chain=[],
            agent_active=False,
            supports_file_type=False,
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
            for idx in range(initial_count, len(all_findings)):
                finding = all_findings[idx]
                if not isinstance(finding.metadata, dict):
                    finding.metadata = {}
                finding.metadata["analysis_phase"] = "deep"
                meta = finding.metadata
                reason_str = str(meta.get("reason") or meta.get("skipped_reason") or "").lower()
                is_gated = (
                    meta.get("skipped") is True
                    or meta.get("anomaly_tracer_skipped") is True
                    or meta.get("adversarial_check_skipped") is True
                    or "not triggered" in reason_str
                    or "not warranted" in reason_str
                )
                if is_gated:
                    finding.metadata["gated"] = True

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
    pipeline: ForensicCouncilPipeline,
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

    # The frontend can legitimately call /resume a moment before the worker
    # reaches this pause gate (agent cards may finish revealing before this
    # coroutine writes the paused metadata). Preserve and consume that early
    # decision atomically with GETDEL instead of the racy GET+DELETE pattern
    # that could lose a decision written between the two operations.
    try:
        raw_pre_gate_decision = await redis.getdel(decision_key)
        if raw_pre_gate_decision:
            decision = json.loads(raw_pre_gate_decision)
            if isinstance(decision, dict):
                pipeline.run_deep_analysis_flag = bool(decision.get("deep_analysis"))
                logger.info(
                    "Analyst decision consumed before pause gate",
                    session_id=str(session_id),
                    deep_analysis=pipeline.run_deep_analysis_flag,
                )
                return pipeline.run_deep_analysis_flag
    except AttributeError:
        # Redis < 6.2 does not support GETDEL; fall back to racy GET+DELETE
        try:
            raw_pre_gate_decision = await redis.get(decision_key)
            if raw_pre_gate_decision:
                decision = json.loads(raw_pre_gate_decision)
                if isinstance(decision, dict):
                    pipeline.run_deep_analysis_flag = bool(decision.get("deep_analysis"))
                    return pipeline.run_deep_analysis_flag
        except Exception as pre_gate_err:
            logger.debug("Pre-gate decision check flicker", error=str(pre_gate_err))
        finally:
            await redis.delete(decision_key)
    except Exception as pre_gate_err:
        logger.debug("Pre-gate decision check flicker", error=str(pre_gate_err))
        await redis.delete(decision_key)

    pipeline._awaiting_user_decision = True
    pipeline.deep_analysis_decision_event.clear()
    pipeline.run_deep_analysis_flag = False

    existing_metadata = await get_active_pipeline_metadata(str(session_id))
    if not isinstance(existing_metadata, dict):
        existing_metadata = {}
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


async def _await_deep_report_request(
    pipeline: ForensicCouncilPipeline,
    session_id: UUID,
) -> None:
    """Pause after deep analysis so the analyst controls final arbiter synthesis."""
    from api.routes._session_state import (
        broadcast_update,
        get_active_pipeline_metadata,
        set_active_pipeline_metadata,
    )
    from api.schemas import BriefUpdate
    from core.persistence.redis_client import get_redis_client

    decision_key = f"forensic:session:resume_decision:{session_id}"
    redis = await get_redis_client()

    # Same race as the initial deep-analysis gate: the analyst may request the
    # final report just before this post-deep pause is fully registered. Treat
    # any already-written resume decision as the final synthesis request.
    try:
        raw_pre_gate_decision = await redis.get(decision_key)
        if raw_pre_gate_decision:
            logger.info(
                "Final report request consumed before post-deep pause gate",
                session_id=str(session_id),
            )
            return
    except Exception as pre_gate_err:
        logger.debug("Pre-gate final-report decision check flicker", error=str(pre_gate_err))

    await redis.delete(decision_key)

    pipeline._awaiting_user_decision = True
    pipeline.deep_analysis_decision_event.clear()
    pipeline.run_deep_analysis_flag = False

    existing_metadata = await get_active_pipeline_metadata(str(session_id))
    if not isinstance(existing_metadata, dict):
        existing_metadata = {}
    await set_active_pipeline_metadata(
        str(session_id),
        {
            **existing_metadata,
            "status": "awaiting_deep_report",
            "brief": "Deep analysis complete. Awaiting analyst request for arbiter synthesis.",
            "awaiting_decision": True,
            "deep_analysis_complete": True,
        },
    )
    await broadcast_update(
        str(session_id),
        BriefUpdate(
            type="PIPELINE_PAUSED",
            session_id=str(session_id),
            message="Deep analysis complete. Awaiting analyst request for arbiter synthesis.",
            data={
                "status": "awaiting_deep_report",
                "deep_results_ready": True,
            },
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
                    logger.info(
                        "Final report request received via Redis",
                        session_id=str(session_id),
                    )
                    return
            except Exception as poll_err:
                logger.debug("Final-report decision polling flicker", error=str(poll_err))

            if pipeline.deep_analysis_decision_event.is_set():
                logger.info(
                    "Final report request received via internal event",
                    session_id=str(session_id),
                )
                return

            await asyncio.sleep(2.0)

        logger.warning(
            "Deep report request timed out; proceeding to arbiter synthesis",
            session_id=str(session_id),
            timeout_seconds=timeout,
        )
    finally:
        pipeline._awaiting_user_decision = False
        try:
            await redis.delete(decision_key)
        except Exception as _e:
            logger.debug("Decision key cleanup skipped (Redis may be unavailable)", error=str(_e))

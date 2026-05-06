"""
Synthesis Service for Forensic Council.
Post-analysis Groq synthesis to produce structured forensic narratives.
"""

import json
from typing import Any

from core.config import Settings
from core.llm_client import LLMClient
from core.media_kind import is_screen_capture_like
from core.react_loop import AgentFinding
from core.structured_logging import get_logger

logger = get_logger(__name__)

# ── Per-agent tool groups ─────────────────────────────────────────────
_TOOL_GROUPS: dict[str, list[dict[str, Any]]] = {
    "Agent1": [
        {
            "id": "pixel_integrity",
            "label": "Pixel-Level Integrity",
            "tools": [
                "ela_full_image",
                "ela_anomaly_classify",
                "jpeg_ghost_detect",
                "noise_fingerprint",
                "neural_ela",
                "noiseprint_cluster",
            ],
            "desc": "Compression-artifact and noise-consistency checks — primary manipulation signal for JPEG images.",
        },
        {
            "id": "spectral",
            "label": "Spectral & GAN Analysis",
            "tools": [
                "frequency_domain_analysis",
                "deepfake_frequency_check",
                "diffusion_artifact_detector",
            ],
            "desc": "FFT-based analysis for GAN/Diffusion artifacts and 2026-era frequency anomalies.",
        },
        {
            "id": "structural",
            "label": "Structural Manipulation",
            "tools": ["copy_move_detect", "splicing_detect"],
            "desc": "Copy-move and splice detection — regions cloned from within or outside the image.",
        },
        {
            "id": "chain_of_custody",
            "label": "Chain of Custody",
            "tools": ["file_hash_verify", "adversarial_robustness_check", "neural_fingerprint"],
            "desc": "File integrity since ingestion and anti-forensics evasion robustness.",
        },
        {
            "id": "content",
            "label": "Content Analysis",
            "tools": ["analyze_image_content", "extract_text_from_image", "extract_evidence_text"],
            "desc": "Semantic image classification and OCR text extraction.",
        },
    ],
    "Agent2": [
        {
            "id": "voice_authenticity",
            "label": "Voice Authenticity",
            "tools": ["anti_spoofing_detect", "voice_clone_detect"],
            "desc": "Deepfake and AI synthetic speech detection.",
        },
        {
            "id": "temporal_integrity",
            "label": "Temporal Integrity",
            "tools": ["audio_splice_detect", "enf_analysis", "background_noise_analysis"],
            "desc": "Splicing, ENF frequency jumps, and noise-floor consistency.",
        },
        {
            "id": "prosody_codec",
            "label": "Prosody & Codec Analysis",
            "tools": ["prosody_analyze", "codec_fingerprinting"],
            "desc": "Vocal prosody (jitter/shimmer) and multi-generation codec re-encoding detection.",
        },
        {
            "id": "multimodal",
            "label": "Multimodal Consistency",
            "tools": ["audio_visual_sync", "inter_agent_call"],
            "desc": "AV sync verification and collaborative cross-agent flags.",
        },
    ],
    "Agent3": [
        {
            "id": "screenshot_context",
            "label": "Screenshot Context",
            "tools": [
                "screenshot_scene_applicability",
                "screenshot_layout_forensics",
            ],
            "desc": "Screen-capture scope, UI/document structure, and layout anomaly checks.",
        },
        {
            "id": "scene_semantics",
            "label": "Scene Semantics",
            "tools": [
                "object_detection",
                "scene_incongruence",
                "contraband_database",
                "vector_contraband_search",
            ],
            "desc": "Object and scene semantic consistency — identifying contextually inappropriate items.",
        },
        {
            "id": "physical_consistency",
            "label": "Physical Consistency",
            "tools": [
                "lighting_consistency",
                "lighting_correlation_initial",
                "shadow_validation",
                "scale_validation",
            ],
            "desc": "Lighting, shadow, and geometric vanishing-point physics validation.",
        },
    ],
    "Agent4": [
        {
            "id": "temporal",
            "label": "Temporal Flow",
            "tools": [
                "optical_flow_analyze",
                "optical_flow_analysis",
                "vfi_error_map",
                "frame_consistency_analysis",
                "interframe_forgery_detector",
                "thumbnail_coherence",
            ],
            "desc": "Frame-to-frame flow and motion-ghosting forgery detection.",
        },
        {
            "id": "biometric",
            "label": "Biometric Forgery",
            "tools": ["face_swap_detection"],
            "desc": "DeepFace face-swap detection.",
        },
        {
            "id": "device",
            "label": "Device & Container",
            "tools": [
                "av_file_identity",
                "mediainfo_profile",
                "video_metadata",
                "rolling_shutter_validation",
            ],
            "desc": "Container metadata and sensor-specific rolling shutter validation.",
        },
    ],
    "Agent5": [
        {
            "id": "metadata_integrity",
            "label": "Metadata & Fabrication",
            "tools": [
                "exif_extract",
                "extract_deep_metadata",
                "metadata_anomaly_scorer",
                "metadata_anomaly_score",
                "exif_isolation_forest",
                "timestamp_analysis",
                "gps_timezone_validate",
                "astro_grounding",
            ],
            "desc": "EXIF/XMP integrity and probabilistic fabrication detection.",
        },
        {
            "id": "binary_sig",
            "label": "Binary Signatures",
            "tools": [
                "file_hash_verify",
                "file_structure_analysis",
                "hex_signature_scan",
                "compression_risk_audit",
                "c2pa_validator",
                "provenance_chain_verify",
                "av_file_identity",
                "mediainfo_profile",
            ],
            "desc": "Binary-level anomalies, chimeric signatures, and C2PA provenance manifests.",
        },
        {
            "id": "hidden_data",
            "label": "Embedded Data",
            "tools": ["steganography_scan"],
            "desc": "Hidden payloads and software watermark detection.",
        },
    ],
}

TEMPLATE_PATTERNS = [
    "analysis complete",
    "no significant indicators",
    "waiting for results",
    "ready for review",
    "connected to engine",
    "initializing",
    "scanning evidence",
    "investigation is queued",
    "connected. waiting for this agent's first backend signal",
    "opening live investigation stream",
    "image appears authentic",
    "advanced neural analysis confirms",
    "matches the expected",
    "empty raw tool results",
    "no anomalies detected due to",
]


BAD_SYNTHESIS_PHRASES = (
    "expected hash",
    "matches the expected",
    "expected content",
    "advanced neural analysis confirms",
    "image appears authentic",
    "empty raw tool results",
    "lack of results",
    "no digital traces or anomalies were detected due to",
)


class SynthesisService:
    def __init__(self, config: Settings):
        self.config = config

    def _is_template_finding(self, text: str) -> bool:
        if not text:
            return True
        t = text.lower()
        return any(p in t for p in TEMPLATE_PATTERNS)

    async def synthesize_findings(
        self,
        agent_id: str,
        agent_name: str,
        findings: list[AgentFinding],
        evidence_artifact: Any,
        tool_success_count: int,
        tool_error_count: int,
        phase: str = "initial",
    ) -> dict[str, Any]:
        """
        Synthesize findings using Groq to produce a structured forensic narrative.
        """
        # --- Pre-filter template findings and deduplicate ---
        unique_findings = []
        seen_summaries = set()
        for f in findings:
            summary = f.metadata.get("llm_refined_summary") or f.reasoning_summary or f.finding_type or ""
            # Use a slightly fuzzy key for deduplication
            norm_summary = summary.lower().strip()
            dedup_key = f"{f.metadata.get('tool_name')}:{norm_summary[:100]}"
            if dedup_key not in seen_summaries:
                unique_findings.append(f)
                seen_summaries.add(dedup_key)

        findings = unique_findings
        if not findings:
            return {}

        llm_client = LLMClient(self.config)
        agent_key = agent_id.replace("_deep", "").replace("_metadata", "").split("_")[0]
        # Normalize agent_key to Agent1, Agent2, etc.
        if "Agent1" in agent_id:
            agent_key = "Agent1"
        elif "Agent2" in agent_id:
            agent_key = "Agent2"
        elif "Agent3" in agent_id:
            agent_key = "Agent3"
        elif "Agent4" in agent_id:
            agent_key = "Agent4"
        elif "Agent5" in agent_id:
            agent_key = "Agent5"

        tool_groups = _TOOL_GROUPS.get(agent_key, [])

        # Calculate pre-synthesis stats
        total_calls = tool_success_count + tool_error_count
        _not_applicable_keys = (
            "ela_not_applicable",
            "ghost_not_applicable",
            "noise_fingerprint_not_applicable",
            "prnu_not_applicable",
        )

        # Filter out findings that are not court-defensible or are marked as not-applicable
        defensible_scores = [
            f.confidence_raw
            for f in findings
            if f.metadata.get("court_defensible", True)
            and not any(f.metadata.get(k) for k in _not_applicable_keys)
        ]
        # Filter out None values and ensure they are floats for safe averaging
        valid_defensible = [float(s) for s in defensible_scores if s is not None]
        pre_confidence = (
            round(sum(valid_defensible) / len(valid_defensible), 3) if valid_defensible else 0.75
        )
        pre_error_rate = round(tool_error_count / total_calls, 3) if total_calls > 0 else 0.0

        # Build sections for prompt
        target_findings = findings
        grouped_sections_data = []
        screenshot_like = is_screen_capture_like(evidence_artifact)

        for grp in tool_groups:
            grp_findings = [
                f for f in target_findings if f.metadata.get("tool_name", "") in grp["tools"]
            ]
            if not grp_findings:
                continue

            tools_summary = []
            for f in grp_findings:
                is_tool_limitation = (
                    f.status in {"INCOMPLETE", "NOT_APPLICABLE", "ABSTAIN"}
                    or f.evidence_verdict in {"ERROR", "NOT_APPLICABLE"}
                    or f.metadata.get("available") is False
                    or bool(f.metadata.get("degraded"))
                    or bool(f.metadata.get("metadata_incomplete"))
                )
                tools_summary.append(
                    {
                        "tool": f.metadata.get("tool_name", "unknown"),
                        "finding_type": f.finding_type,
                        "confidence": round(f.confidence_raw, 3)
                        if f.confidence_raw is not None
                        else 0.5,
                        "verdict": "TOOL_LIMITATION" if is_tool_limitation else f.status,
                        "status": f.status,
                        "evidence_verdict": f.evidence_verdict,
                        "tool_limitation": is_tool_limitation,
                        "tool_summary": f.reasoning_summary,
                        "court_statement": getattr(f, "court_statement", None),
                        "data": self._compact_metrics(f),
                    }
                )

            grouped_sections_data.append(
                {"id": grp["id"], "label": grp["label"], "findings": tools_summary}
            )

        # Construct Groq Synthesis Prompt
        prompt = f"""
[SYSTEM: FORENSIC ANALYST SYNTHESIS]
You are a Senior Forensic Analyst at the National Cyber Forensics Institute.
Your task is to synthesize raw tool findings from {agent_name} into a cohesive, technical, and court-defensible narrative.

[EVIDENCE CONTEXT]
Filename: {evidence_artifact.file_path}
MIME: {evidence_artifact.mime_type}
Agent: {agent_name} ({agent_id})

[RAW TOOL RESULTS]
{json.dumps(grouped_sections_data, indent=2, default=str)}

[INSTRUCTIONS]
1. For each group, provide a 1-2 sentence "Forensic Opinion" that synthesizes the raw tool data into an actionable technical conclusion. Reference specific metric values.
2. Determine an overall 'verdict' for this agent: AUTHENTIC, SUSPICIOUS, or TAMPERED.
3. [EXECUTIVE SUMMARY]: The 'narrative_summary' MUST be 2-3 sentences, 60-80 words. Format: Sentence 1 — what forensic tests were applied and what was found. Sentence 2 — the primary forensic signal (with metric if available). Sentence 3 — what the verdict means for the integrity of this evidence. It MUST mention the primary technical indicator by name.
4. [USER-FRIENDLY FINDINGS]: For each tool, write a 'user_friendly_summary' that is a specific, factual sentence. BAD example: "Neural Ela found a forensic warning signal at 85% confidence." GOOD example: "Error Level Analysis detected pixel re-compression artifacts in the upper-left quadrant — a pattern consistent with content pasting over an original background." Translate every metric into forensic meaning. Avoid jargon like 'ELA', 'FFT', 'PRNU' — spell them out.
5. Use objective, technical language for the 'narrative_summary' and 'opinion', but accessible, specific language for 'user_friendly_summary'. Never write generic phrases like "found a forensic warning signal at X% confidence", "signal detected", or "produced a positive result".
6. Tool failures, unavailable tools, degraded fallbacks, NOT_APPLICABLE results, and INCOMPLETE findings are coverage limitations only. Do NOT treat them as evidence of tampering or authenticity. Mention them as limitations and base SUSPICIOUS/TAMPERED verdicts only on successful POSITIVE forensic signals.
7. For screenshots, do not claim camera authenticity. State what was actually checked: OCR text, screenshot layout, hash since intake, file structure, compression/platform footprints, timestamps, and any Gemini visual findings.
8. Never say "expected hash", "expected content", "advanced neural analysis confirms authenticity", or "empty raw tool results". A hash only proves the uploaded artifact has not changed after intake.

Return ONLY a JSON object in this format:
{{
  "verdict": "AUTHENTIC|SUSPICIOUS|TAMPERED|INCONCLUSIVE",
  "narrative_summary": "2-3 sentence executive summary, 60-80 words, specific and forensically grounded.",
  "sections": [
    {{
      "id": "group_id",
      "label": "Group Label",
      "opinion": "Synthesized technical opinion referencing specific metric values.",
      "severity": "LOW|MEDIUM|HIGH|CRITICAL",
      "refined_findings": [
        {{
          "tool": "tool_name",
          "user_friendly_summary": "Specific, factual finding in plain English — what was measured and what it means for authenticity."
        }}
      ]
    }}
  ]
}}
"""
        try:
            raw = await llm_client.generate_synthesis(
                system_prompt="You are a Senior Forensic Analyst. Return ONLY valid JSON.",
                user_content=prompt,
                max_tokens=1200,
                json_mode=True,
            )
            if not raw:
                raise ValueError("LLM returned empty response")
            try:
                response = json.loads(raw.strip())
                if raw.strip().startswith("```"):
                    cleaned = raw.split("```", 2)[-1].lstrip("json").strip()
                    if cleaned.endswith("```"):
                        cleaned = cleaned[:-3].strip()
                    response = json.loads(cleaned)
            except json.JSONDecodeError:
                brace_start = raw.find("{")
                brace_end = raw.rfind("}")
                if brace_start >= 0 and brace_end > brace_start:
                    response = json.loads(raw[brace_start : brace_end + 1])
                else:
                    raise ValueError("Invalid LLM response format")
            if not isinstance(response, dict):
                raise ValueError("Invalid LLM response format")

            groq_verdict = response.get("verdict", "INCONCLUSIVE").upper()
            positive_count = sum(
                1
                for group in grouped_sections_data
                for finding in group.get("findings", [])
                if str(finding.get("evidence_verdict")).upper() == "POSITIVE"
                and not finding.get("tool_limitation")
            )
            limitation_count = sum(
                1
                for group in grouped_sections_data
                for finding in group.get("findings", [])
                if finding.get("tool_limitation")
            )
            if positive_count == 0 and groq_verdict in {"SUSPICIOUS", "TAMPERED"}:
                groq_verdict = "INCONCLUSIVE" if limitation_count else "AUTHENTIC"
            if positive_count > 0 and groq_verdict == "AUTHENTIC":
                groq_verdict = "SUSPICIOUS"
            response = self._ground_synthesis_response(
                response,
                grouped_sections_data,
                screenshot_like=screenshot_like,
                agent_name=agent_name,
            )
            calibrated_confidence = pre_confidence
            if screenshot_like and "object" in agent_name.lower():
                layout_rows = [
                    finding
                    for group in grouped_sections_data
                    for finding in group.get("findings", [])
                    if finding.get("tool") == "screenshot_layout_forensics"
                ]
                clean_layout = any(
                    str(row.get("evidence_verdict")).upper() == "NEGATIVE"
                    and not row.get("tool_limitation")
                    and int((row.get("data") or {}).get("layout_anomaly_count") or 0) == 0
                    for row in layout_rows
                )
                has_positive = positive_count > 0
                if clean_layout and not has_positive:
                    groq_verdict = "AUTHENTIC"
                    calibrated_confidence = max(calibrated_confidence, 0.78)
            return {
                "agent_confidence": round(calibrated_confidence, 3),
                "agent_error_rate": pre_error_rate,
                "verdict": groq_verdict,
                "narrative_summary": response.get("narrative_summary", ""),
                "sections": response.get("sections", []),
            }
        except Exception as e:
            logger.error(f"Groq synthesis failed: {e}")
            positive_count = sum(
                1
                for group in grouped_sections_data
                for finding in group.get("findings", [])
                if str(finding.get("evidence_verdict")).upper() == "POSITIVE"
                and not finding.get("tool_limitation")
            )
            fallback_verdict = "SUSPICIOUS" if positive_count else "AUTHENTIC"
            if pre_error_rate > 0.4:
                fallback_verdict = "INCONCLUSIVE"
            elif not positive_count and pre_confidence < 0.55:
                fallback_verdict = "INCONCLUSIVE"

            signal_rows: list[dict[str, Any]] = []
            for group in grouped_sections_data:
                for finding in group.get("findings", []):
                    signal_rows.append(
                        {
                            "group_id": group.get("id"),
                            "group_label": group.get("label"),
                            "tool": finding.get("tool", "unknown"),
                            "confidence": finding.get("confidence", 0.0),
                            "evidence_verdict": finding.get("evidence_verdict", "INCONCLUSIVE"),
                            "status": finding.get("status", "INCONCLUSIVE"),
                            "tool_limitation": finding.get("tool_limitation", False),
                            "data": finding.get("data", {}),
                        }
                    )
            signal_rows.sort(
                key=lambda item: (
                    0 if item.get("tool_limitation") else 1,
                    1 if str(item.get("evidence_verdict")).upper() == "POSITIVE" else 0,
                    float(item.get("confidence") or 0.0),
                ),
                reverse=True,
            )
            primary = signal_rows[0] if signal_rows else {}
            primary_tool = str(primary.get("tool") or "forensic tools").replace("_", " ")
            primary_verdict = str(primary.get("evidence_verdict") or "INCONCLUSIVE").lower()
            primary_conf = float(primary.get("confidence") or pre_confidence or 0.0)
            narrative = (
                f"{primary_tool.title()} is the strongest agent signal: {primary_verdict} "
                f"at {primary_conf:.0%} confidence across {len(findings)} applicable findings."
                if primary
                else f"{agent_name} produced no applicable forensic signal."
            )

            sections = []
            for group in grouped_sections_data:
                refined = []
                group_positive = False
                group_limited = False
                for finding in group.get("findings", []):
                    tool = finding.get("tool", "unknown")
                    data = finding.get("data", {}) if isinstance(finding.get("data"), dict) else {}
                    verdict = str(finding.get("evidence_verdict") or finding.get("status") or "INCONCLUSIVE")
                    conf = float(finding.get("confidence") or 0.0)
                    group_positive = group_positive or verdict.upper() == "POSITIVE"
                    group_limited = group_limited or bool(finding.get("tool_limitation"))
                    metric_bits = [
                        f"{k}={v}"
                        for k, v in list(data.items())[:3]
                        if isinstance(v, (bool, int, float, str))
                    ]
                    metric_text = f" Key metrics: {', '.join(metric_bits)}." if metric_bits else ""
                    if finding.get("tool_limitation"):
                        summary = (
                            f"{tool.replace('_', ' ').title()} did not produce a usable signal; "
                            f"this is a coverage limitation, not evidence of tampering.{metric_text}"
                        )
                    elif verdict.upper() == "POSITIVE":
                        summary = (
                            f"{tool.replace('_', ' ').title()} found a forensic warning signal "
                            f"at {conf:.0%} confidence.{metric_text}"
                        )
                    elif verdict.upper() == "NEGATIVE":
                        summary = (
                            f"{tool.replace('_', ' ').title()} found no supported anomaly "
                            f"at {conf:.0%} confidence.{metric_text}"
                        )
                    else:
                        summary = (
                            f"{tool.replace('_', ' ').title()} was inconclusive "
                            f"at {conf:.0%} confidence.{metric_text}"
                        )
                    refined.append({"tool": tool, "user_friendly_summary": summary})
                sections.append(
                    {
                        "id": group["id"],
                        "label": group["label"],
                        "opinion": (
                            f"{group['label']} completed with "
                            f"{len(group.get('findings', []))} model/tool result(s)."
                        ),
                        "severity": "MEDIUM" if group_positive or group_limited else "LOW",
                        "refined_findings": refined,
                    }
                )

            return {
                "agent_confidence": pre_confidence,
                "agent_error_rate": pre_error_rate,
                "verdict": fallback_verdict,
                "narrative_summary": narrative,
                "sections": self._ground_synthesis_response(
                    {"sections": sections},
                    grouped_sections_data,
                    screenshot_like=screenshot_like,
                    agent_name=agent_name,
                ).get("sections", sections),
                "synthesis_source": "tool_grounded_fallback",
            }

    def _ground_synthesis_response(
        self,
        response: dict[str, Any],
        grouped_sections_data: list[dict[str, Any]],
        *,
        screenshot_like: bool,
        agent_name: str,
    ) -> dict[str, Any]:
        """Replace vague/hallucinated LLM wording with tool-grounded summaries."""
        tool_rows: dict[str, dict[str, Any]] = {}
        for group in grouped_sections_data:
            for row in group.get("findings", []):
                tool = str(row.get("tool") or "")
                if tool:
                    tool_rows[tool] = row

        def _bad(text: str) -> bool:
            lower = str(text or "").lower()
            return not lower.strip() or any(phrase in lower for phrase in BAD_SYNTHESIS_PHRASES)

        sections = response.get("sections") if isinstance(response.get("sections"), list) else []
        for section in sections:
            refined = section.get("refined_findings") or []
            grounded_any = []
            for item in refined:
                tool = str(item.get("tool") or "")
                row = tool_rows.get(tool)
                if not row:
                    continue
                grounded = self._tool_grounded_summary(row, screenshot_like=screenshot_like)
                if grounded and (_bad(str(item.get("user_friendly_summary") or "")) or screenshot_like):
                    item["user_friendly_summary"] = grounded
                grounded_any.append(grounded or str(item.get("user_friendly_summary") or ""))
            opinion = str(section.get("opinion") or "")
            if _bad(opinion) and grounded_any:
                section["opinion"] = " ".join(x for x in grounded_any[:2] if x)[:420]

        narrative = str(response.get("narrative_summary") or "")
        if screenshot_like and "object" in agent_name.lower():
            scope_row = tool_rows.get("screenshot_scene_applicability", {})
            layout_row = tool_rows.get("screenshot_layout_forensics", {})
            layout_anomalies = int((scope_row.get("data") or {}).get("layout_anomaly_count") or
                                   (layout_row.get("data") or {}).get("layout_anomaly_count") or 0)
            verdict_text = "found no UI/document structure anomalies" if layout_anomalies == 0 else f"found {layout_anomalies} layout anomaly flag(s)"
            dims = ""
            scope_data = scope_row.get("data") or {}
            if scope_data.get("width") and scope_data.get("height"):
                dims = f" ({scope_data['width']}x{scope_data['height']}px)"
            response["verdict"] = "AUTHENTIC" if layout_anomalies == 0 else "SUSPICIOUS"
            # Build a meta-synthesis narrative — NOT a repetition of individual tool text
            response["narrative_summary"] = (
                f"Object and scene forensic tools were bypassed because this is a screen capture{dims}; "
                f"physical geometry checks (lighting, scale, weapons) do not apply. "
                f"Screenshot layout analysis {verdict_text}."
            )
        elif screenshot_like and _bad(narrative):
            useful = [
                self._tool_grounded_summary(row, screenshot_like=True)
                for row in tool_rows.values()
                if row.get("tool") in {"screenshot_layout_forensics", "extract_text_from_image", "file_structure_analysis", "compression_risk_audit"}
            ]
            useful = [u for u in useful if u]
            response["narrative_summary"] = (
                " ".join(useful[:2])[:260]
                if useful
                else f"{agent_name} completed screenshot-specific checks; review tool rows for exact OCR, layout, and provenance metrics."
            )
        return response

    def _tool_grounded_summary(self, row: dict[str, Any], *, screenshot_like: bool) -> str:
        tool = str(row.get("tool") or "")
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        verdict = str(row.get("evidence_verdict") or row.get("status") or "").upper()
        conf = float(row.get("confidence") or 0.0)

        def _hash_prefix() -> str:
            digest = str(data.get("current_hash") or data.get("computed_hash") or data.get("original_hash") or "")
            return f" ({digest[:12]}...)" if digest else ""

        if tool == "file_hash_verify":
            match = data.get("hash_matches") is True or data.get("hash_match") is True
            return (
                f"SHA-256 intake check {'matched' if match else 'did not match'} the chain-of-custody record{_hash_prefix()}. "
                "This verifies the submitted file has not changed after upload; it does not prove pre-upload authenticity."
            )
        if tool == "extract_text_from_image":
            words = int(data.get("word_count") or 0)
            method = str(data.get("method") or data.get("ocr_engine") or "OCR")
            preview = " ".join(
                str(data.get("text") or data.get("full_text") or data.get("ocr_text_preview") or "")
                .replace("|", " | ")
                .split()
            ).strip()
            if words > 0 or preview:
                return f"{method} extracted {words} word(s) from the screenshot. Visible text preview: {preview[:180]}"
            return (
                f"{method} did not extract readable text. Treat this as an OCR coverage limit"
                + (" for this screenshot." if screenshot_like else ".")
            )
        if tool == "frequency_domain_analysis":
            score = data.get("anomaly_score", 0)
            hfr = data.get("high_freq_ratio", None)
            return (
                f"Frequency scan measured anomaly score {float(score or 0):.3f}"
                + (f" and high-frequency ratio {float(hfr):.3f}" if isinstance(hfr, (int, float)) else "")
                + (". No frequency-domain manipulation pattern was detected." if verdict == "NEGATIVE" else ". Review as a frequency-domain warning signal.")
            )
        if tool == "neural_fingerprint":
            sim = data.get("top_similarity", data.get("similarity", data.get("confidence", conf)))
            return (
                f"Neural fingerprint generated a perceptual signature for comparison; top similarity was {float(sim or 0):.3f}. "
                + ("No high-confidence prior-media match was reported." if not data.get("match_found") else "A similar prior-media match was reported.")
            )
        if tool == "analyze_image_content":
            if row.get("tool_limitation") or verdict == "ERROR":
                err = str(data.get("error") or data.get("tool_error") or data.get("status") or "tool did not complete")
                return f"Semantic image classification did not produce a usable result ({err[:140]}). This is a coverage limit, not an authenticity signal."
            if data.get("semantic_scope") == "screenshot_fast_profile":
                return (
                    f"Screenshot semantic profile recorded {data.get('width')}x{data.get('height')}px "
                    f"({data.get('color_mode')} mode). Heavy scene classification was bypassed for the initial pass because screenshot authenticity is better assessed by OCR, layout, hash, and provenance checks."
                )
            image_type = data.get("image_type") or data.get("top_label") or data.get("label")
            return f"Semantic classifier labeled the visible content as {image_type or 'image content'}; this is context only, not proof of authenticity."
        if tool == "screenshot_scene_applicability":
            dims = f"{data.get('width')}x{data.get('height')}px" if data.get("width") and data.get("height") else "screen capture"
            aspect = data.get("aspect_class") or "screen-capture"
            theme = ""
            if "is_dark_mode" in data:
                theme = ", dark UI theme" if data.get("is_dark_mode") else ", light UI theme"
            chrome = ", browser/window chrome detected" if data.get("ui_chrome_detected") else ""
            return (
                f"Screenshot scope confirmed ({dims}, {aspect}{theme}{chrome}). "
                "Physical-scene object, weapon, lighting, and scale tools were bypassed because they do not apply to screen captures."
            )
        if tool == "screenshot_layout_forensics":
            anomalies = int(data.get("layout_anomaly_count") or 0)
            edge = data.get("edge_density")
            hard = data.get("hard_edge_density")
            h_rule = data.get("horizontal_rule_density")
            v_rule = data.get("vertical_rule_density")
            if anomalies:
                return (
                    f"Screenshot layout scan found {anomalies} UI/document structure warning(s), "
                    f"with edge density {edge}; review for pasted panels, misaligned chrome, or inconsistent document regions."
                )
            return (
                f"Screenshot layout scan found no UI/document structure anomaly flags "
                f"(edge density {edge}, hard-edge density {hard}, horizontal/vertical rule density {h_rule}/{v_rule})."
            )
        if tool == "exif_extract":
            fields = int(data.get("total_fields_extracted") or 0)
            if screenshot_like:
                return (
                    f"EXIF extraction found {fields} metadata field(s) and no camera/device capture record. "
                    "That is normal for many screenshots, but it means the original capture time/device cannot be proven from EXIF."
                )
            device = " ".join(
                str(x)
                for x in (data.get("device_model"), data.get("camera_make"), data.get("camera_model"))
                if x
            ).strip()
            captured = data.get("datetime_original") or "not recorded"
            return f"EXIF extraction found {fields} metadata field(s); device {device or 'not recorded'}, original capture time {captured}."
        if tool == "timestamp_analysis":
            issues = data.get("inconsistencies") if isinstance(data.get("inconsistencies"), list) else []
            return (
                f"Timestamp cross-check found {len(issues)} inconsistency(ies)"
                + (f": {'; '.join(str(x) for x in issues[:3])}." if issues else ". Filesystem chronology is internally consistent, but screenshot capture time may still be absent from EXIF.")
            )
        if tool == "hex_signature_scan":
            scanned = data.get("bytes_scanned", 0)
            software = data.get("software_signatures") if isinstance(data.get("software_signatures"), list) else []
            return (
                f"Hex signature scan reviewed {int(scanned or 0):,} bytes"
                + (f" and found software signatures: {', '.join(map(str, software[:3]))}." if software else " and found no embedded editing-software signature.")
            )
        if tool == "compression_risk_audit":
            raw_platform = data.get("detected_platform")
            platform = (
                "stripped or platform-normalized metadata"
                if str(raw_platform or "").lower() in {"", "unknown", "none"}
                else raw_platform
            )
            impact = data.get("forensic_reliability_impact") or "not specified"
            penalty = data.get("compression_penalty", 1.0)
            return (
                f"Compression/platform audit found {platform}; reliability impact {impact}, "
                f"penalty factor {float(penalty or 1.0):.2f}. This limits provenance strength but is not a manipulation signal by itself."
            )
        if tool == "file_structure_analysis":
            anomalies = data.get("anomalies") if isinstance(data.get("anomalies"), list) else []
            return (
                f"File structure check found valid header/trailer status with {len(anomalies)} anomaly flag(s)"
                + (f": {'; '.join(map(str, anomalies[:3]))}." if anomalies else " and no appended payload indicators.")
            )
        if tool == "neural_ela":
            score = data.get("ela_score") or data.get("anomaly_score") or data.get("ela_mean") or 0
            regions = data.get("anomaly_regions") or data.get("flagged_regions") or []
            region_text = f" across {len(regions)} region(s)" if regions else ""
            if verdict == "POSITIVE":
                return (
                    f"Error Level Analysis (ELA) measured a re-compression inconsistency score of {float(score):.3f}{region_text}. "
                    "This indicates that parts of the image were saved at different compression levels — a hallmark of content being pasted in from another source."
                )
            return (
                f"Error Level Analysis measured a re-compression score of {float(score):.3f} with no high-confidence inconsistency regions. "
                "Compression artifacts appear uniform across the image, with no evidence of selective pasting or manipulation."
            )
        if tool == "noiseprint_cluster":
            clusters = data.get("cluster_count") or data.get("num_clusters") or 0
            inconsistent = data.get("inconsistent_regions") or data.get("anomalous_clusters") or 0
            if verdict == "POSITIVE" or inconsistent:
                return (
                    f"Noiseprint++ sensor clustering found {clusters} noise-pattern cluster(s) with {inconsistent} inconsistent region(s). "
                    "Different noise textures in the same image suggest the pixels did not all come from the same camera sensor — a strong indicator of splicing."
                )
            return (
                f"Noiseprint++ sensor clustering found {clusters} cluster(s) with no statistically inconsistent noise regions. "
                "The sensor noise pattern is homogeneous across the image, consistent with a single capture device."
            )
        return ""

    def _compact_metrics(self, f: AgentFinding) -> dict[str, Any]:
        _SKIP_META = {
            "tool_name",
            "stub_warning",
            "llm_synthesis",
            "llm_reasoning",
            "synthesis_phase",
            "analysis_phase",
            "analysis_source",
            "backend",
        }
        out = {}
        for k, v in f.metadata.items():
            if k in _SKIP_META:
                continue
            if isinstance(v, (bool, int, float, str, list)):
                out[k] = v
        return out

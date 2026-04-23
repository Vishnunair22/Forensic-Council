"""
Synthesis Service for Forensic Council.
Post-analysis Groq synthesis to produce structured forensic narratives.
"""

import json
from typing import Any

from core.config import Settings
from core.llm_client import LLMClient
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


class SynthesisService:
    def __init__(self, config: Settings):
        self.config = config

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
{json.dumps(grouped_sections_data, indent=2)}

[INSTRUCTIONS]
1. For each group, provide a 1-2 sentence "Forensic Opinion" that synthesizes the raw tool data.
2. Determine an overall 'verdict' for this agent: AUTHENTIC, SUSPICIOUS, or TAMPERED.
3. [EXECUTIVE SUMMARY]: The 'narrative_summary' must be a concise (max 35 words), high-impact forensic conclusion. It MUST mention the primary technical indicator.
4. [USER-FRIENDLY FINDINGS]: For each tool in the group, translate the machine metrics into a 'user_friendly_summary'. Instead of "ELA 0.85 anomaly", say "Detected digital traces of editing in specific areas". Avoid jargon in these summaries.
5. Use objective, technical language for the 'narrative_summary' and 'opinion', but accessible language for 'user_friendly_summary'.
6. Tool failures, unavailable tools, degraded fallbacks, NOT_APPLICABLE results, and INCOMPLETE findings are coverage limitations only. Do NOT treat them as evidence of tampering or authenticity. Mention them as limitations and base SUSPICIOUS/TAMPERED verdicts only on successful POSITIVE forensic signals.

Return ONLY a JSON object in this format:
{{
  "verdict": "AUTHENTIC|SUSPICIOUS|TAMPERED|INCONCLUSIVE",
  "narrative_summary": "Telegraphic executive summary.",
  "sections": [
    {{
      "id": "group_id",
      "label": "Group Label",
      "opinion": "Synthesized technical opinion.",
      "severity": "LOW|MEDIUM|HIGH|CRITICAL",
      "refined_findings": [
        {{
          "tool": "tool_name",
          "user_friendly_summary": "Clear, jargon-free explanation of this specific signal."
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
                max_tokens=800,
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

            return {
                "agent_confidence": pre_confidence,
                "agent_error_rate": pre_error_rate,
                "verdict": response.get("verdict", "INCONCLUSIVE"),
                "narrative_summary": response.get("narrative_summary", ""),
                "sections": response.get("sections", []),
            }
        except Exception as e:
            logger.error(f"Groq synthesis failed: {e}")
            # Fallback logic
            fallback_verdict = "AUTHENTIC"
            if pre_confidence < 0.5 or pre_error_rate > 0.4:
                fallback_verdict = "SUSPICIOUS"
            elif pre_confidence < 0.7 or pre_error_rate > 0.2:
                fallback_verdict = "INCONCLUSIVE"

            return {
                "agent_confidence": pre_confidence,
                "agent_error_rate": pre_error_rate,
                "verdict": fallback_verdict,
                "narrative_summary": f"Automated synthesis failed. Agent reported {len(findings)} findings with {pre_confidence:.1%} average confidence.",
                "sections": [
                    {
                        "id": g["id"],
                        "label": g["label"],
                        "opinion": "Tool results available in raw findings list.",
                        "severity": "MEDIUM",
                    }
                    for g in grouped_sections_data
                ],
            }

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

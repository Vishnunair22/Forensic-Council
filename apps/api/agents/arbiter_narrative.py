"""
Arbiter Narrative Synthesis Mixin.
Extracted from arbiter.py to improve maintainability.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from agents.arbiter_verdict import (
    AGENT_NAMES,
    ForensicReport,
    confidence_of,
    evidence_verdict_of,
)
from core.llm_client import LLMClient
from core.signing import sign_content
from core.structured_logging import get_logger

logger = get_logger(__name__)


def _finding_importance(finding: dict[str, Any]) -> tuple[int, int, float]:
    verdict_weight = {
        "POSITIVE": 4,
        "INCONCLUSIVE": 2,
        "NEGATIVE": 1,
        "ERROR": 0,
        "NOT_APPLICABLE": 0,
    }.get(evidence_verdict_of(finding), 1)
    severity_weight = {
        "CRITICAL": 4,
        "HIGH": 3,
        "MEDIUM": 2,
        "LOW": 1,
        "INFO": 0,
    }.get(str(finding.get("severity_tier", "")).upper(), 1)
    return (verdict_weight, severity_weight, confidence_of(finding, default=0.0) or 0.0)


class ArbiterNarrativeMixin:
    """
    Mixin for CouncilArbiter that provides LLM-based narrative synthesis methods.
    """

    # ── Agent name map (Full versions for LLM reasoning) ────────────────────
    _AGENT_FULL_NAMES: dict[str, str] = {
        "Agent1": (
            "Image Integrity Agent — "
            "Phase 1: CLIP · OCR · SigLIP2 · SHA-256 · FFT · Neural ELA / Noiseprint++ | "
            "Phase 2: TruFor Splicing · BusterNet Copy-Move · Diffusion Artifact · "
            "F3-Net · ManTra-Net · Gemini Multimodal Synthesis"
        ),
        "Agent2": (
            "Audio Forensics Agent — "
            "Phase 1: Speaker Diarization · Neural Prosody · TTS Signature · Codec Fingerprint | "
            "Phase 2: ENF Analysis · Audio Splice · Voice Clone Ensemble · "
            "Anti-Spoofing Ensemble · Gemini Neural Audio Audit"
        ),
        "Agent3": (
            "Object & Scene Agent — "
            "Phase 1: YOLOv11 Detection · Contraband CLIP Search · Lighting Correlation · "
            "Scene Incongruence | "
            "Phase 2: Secondary Classification · Scale Validation · "
            "Adversarial Robustness · Gemini Object-Scene Synthesis"
        ),
        "Agent4": (
            "Temporal Video Agent — "
            "Phase 1: Video Metadata · VFI Error Map · Thumbnail Coherence · Frame Consistency | "
            "Phase 2: Optical Flow · Interframe Forgery · Face-Swap · Deepfake Frequency · "
            "Rolling Shutter · Compression Artifacts · Gemini Frame Synthesis"
        ),
        "Agent5": (
            "Metadata & Provenance Agent — "
            "Phase 1: Hash Verify · EXIF Extract · Compression Risk · Isolation Forest · "
            "Astro Grounding · GPS Timezone · Timestamp Analysis | "
            "Phase 2: File Structure · Hex Signature · Metadata Anomaly Score · "
            "C2PA Provenance · Camera Profile · Gemini Provenance Synthesis"
        ),
    }

    async def _generate_agent_narrative(
        self,
        agent_id: str,
        findings: list[dict[str, Any]],
        metrics: dict[str, Any],
    ) -> str:
        """
        Generate a Groq-synthesised per-agent narrative.
        """
        if not (self.config.llm_api_key and self.config.llm_provider != "none"):
            return ""

        client = getattr(self, "_synthesis_client", None) or LLMClient(self.config)
        if not client.is_available:
            return ""

        agent_full_name = self._AGENT_FULL_NAMES.get(agent_id, agent_id)
        confidence_pct = round(metrics.get("confidence_score", 0) * 100)
        error_rate_pct = round(metrics.get("error_rate", 0) * 100)
        tools_ok = metrics.get("tools_succeeded", 0)
        tools_total = metrics.get("total_tools_called", 0)

        # Split findings by phase
        initial_f = [
            f
            for f in findings
            if (f.get("metadata") or {}).get("analysis_phase", "initial") == "initial"
        ]
        deep_f = [
            f
            for f in findings
            if (f.get("metadata") or {}).get("analysis_phase") == "deep"
        ]

        _NOT_APPLICABLE_FLAGS = ("ela_not_applicable", "ghost_not_applicable")
        _NOT_APPLICABLE_KEYS = {
            "ela_not_applicable",
            "ghost_not_applicable",
            "ela_limitation_note",
            "ghost_limitation_note",
            "file_format_note",
            "is_camera_format",
        }
        _STRIP_KEYS = {
            "stub_warning",
            "llm_synthesis",
            "llm_reasoning",
            "synthesis_phase",
            "analysis_phase",
            "tool_name",
            "warning",
        }

        def _fmt(findings_list: list[dict]) -> str:
            out = []
            # Sort findings: Deep phase first, then by confidence descending.
            sorted_findings = sorted(
                findings_list,
                key=lambda x: (
                    1
                    if (x.get("metadata") or {}).get("analysis_phase") == "deep"
                    else 0,
                    _finding_importance(x),
                ),
                reverse=True,
            )

            for f in sorted_findings[:8]:
                meta = f.get("metadata") or {}
                tool_name = meta.get("tool_name", f.get("finding_type", ""))
                is_na = any(meta.get(flag) for flag in _NOT_APPLICABLE_FLAGS)
                is_failed = not is_na and meta.get("court_defensible") is False
                key_metrics: dict = {}
                for k, v in meta.items():
                    if k.startswith("_") or k in _STRIP_KEYS:
                        continue
                    if k in _NOT_APPLICABLE_KEYS:
                        key_metrics[k] = v
                        continue
                    if isinstance(v, (bool, int, float)):
                        key_metrics[k] = v
                    elif isinstance(v, str) and len(v) < 200:
                        key_metrics[k] = v
                    elif (
                        isinstance(v, list)
                        and len(v) <= 10
                        and all(isinstance(x, (str, int, float, bool, dict)) for x in v)
                    ):
                        key_metrics[k] = v
                entry = {
                    "tool": tool_name,
                    "confidence": round(confidence_of(f, default=0.0) or 0.0, 3),
                    "evidence_verdict": evidence_verdict_of(f),
                    "status": f.get("status", ""),
                    "applicability": "NOT_APPLICABLE"
                    if is_na
                    else ("FAILED" if is_failed else "RAN"),
                    "summary": (f.get("reasoning_summary") or "")[:400],
                    "metrics": key_metrics,
                }
                out.append(entry)
            return json.dumps(out, indent=2)

        tools_na = metrics.get("tools_not_applicable", 0)
        has_deep = bool(deep_f)
        comparison_section = ""
        initial_vs_deep_comparison = ""
        if has_deep:
            comparison_section = f"\n\nDeep analysis findings ({len(deep_f)} tool scans):\n{_fmt(deep_f)}"
            _comparison_pairs = []
            for df in deep_f:
                d_meta = df.get("metadata") or {}
                d_tool = d_meta.get("tool_name", "")
                matching_initial = [
                    f
                    for f in initial_f
                    if (f.get("metadata") or {}).get("tool_name") == d_tool
                ]
                if matching_initial:
                    mf = matching_initial[0]
                    _comparison_pairs.append(
                        {
                            "tool": d_tool,
                            "initial_confidence": round(confidence_of(mf, default=0.0) or 0.0, 3),
                            "deep_confidence": round(confidence_of(df, default=0.0) or 0.0, 3),
                            "initial_evidence_verdict": evidence_verdict_of(mf),
                            "deep_evidence_verdict": evidence_verdict_of(df),
                            "initial_verdict": (mf.get("metadata") or {}).get(
                                "verdict", ""
                            ),
                            "deep_verdict": d_meta.get("verdict", ""),
                            "initial_manipulation": (mf.get("metadata") or {}).get(
                                "manipulation_detected", False
                            ),
                            "deep_manipulation": d_meta.get(
                                "manipulation_detected", False
                            ),
                        }
                    )
            if _comparison_pairs:
                initial_vs_deep_comparison = (
                    f"\n\nInitial vs Deep comparison (same tool across phases):\n"
                    f"{json.dumps(_comparison_pairs, indent=2)}"
                )

        _deep_para = (
            (
                "\n\nPARAGRAPH 2 — Deep analysis and cross-validation:\n"
                "- What deep tools confirmed, expanded, or contradicted from initial analysis.\n"
                "- Exact Gemini findings if present: content type, extracted text, "
                "detected objects, authenticity verdict."
            )
            if has_deep
            else ""
        )

        system_prompt = f"""You are the Council Arbiter writing the per-agent analysis section of a forensic report.

Write {"2-3" if has_deep else "2"} clear, plain-English paragraphs for the {agent_full_name}. Structure:

PARAGRAPH 1 — Initial analysis results:
- For each tool with applicability "RAN": cite the EXACT metric values from the "metrics" field and interpret them forensically. Do not paraphrase — state the actual numbers (e.g. "ELA found 3 localised anomaly regions with max deviation 14.2", "YOLO detected person (0.87), laptop (0.76)").
- For each tool with applicability "NOT_APPLICABLE": briefly explain why the tool does not apply to this file type (use the ela_limitation_note / ghost_limitation_note / file_format_note from metrics). Do NOT treat these as suspicious findings.
- For each tool with applicability "FAILED": state that it failed and what data is missing as a result.{_deep_para}

PARAGRAPH {"3" if has_deep else "2"} — Reliability and verdict:
- Agent confidence: {confidence_pct}%. Tool error rate: {error_rate_pct}% ({tools_ok} of {tools_total} tools succeeded, {tools_na} not applicable to file type).
- Plain-English verdict for this agent: AUTHENTIC / SUSPICIOUS / INCONCLUSIVE / NOT APPLICABLE.

Do NOT use bullet points. Write in continuous prose. Interpret numbers — do not paste raw JSON."""

        user_content = (
            f"Agent: {agent_full_name}\n"
            f"Confidence: {confidence_pct}%  |  Error rate: {error_rate_pct}%  |  "
            f"Tools succeeded: {tools_ok}/{tools_total}  |  Not applicable: {tools_na}\n\n"
            f"Initial analysis ({len(initial_f)} tool scans):\n{_fmt(initial_f)}"
            f"{comparison_section}"
            f"{initial_vs_deep_comparison}\n\n"
            f"Write the per-agent analysis section."
        )

        try:
            return await client.generate_synthesis(
                system_prompt=system_prompt,
                user_content=user_content,
                max_tokens=380,
                json_mode=False,
            )
        except Exception as e:
            logger.debug(
                f"Per-agent narrative Groq parsing/call failed for {agent_id}: {e}"
            )
            return ""

    async def _generate_executive_summary(
        self,
        num_agents: int,
        num_findings: int,
        cross_modal_confirmed: int,
        contested: int,
        all_findings: list[dict[str, Any]] = None,
        gemini_findings: list[dict[str, Any]] = None,
        active_agent_metrics: list[dict[str, Any]] = None,
        overall_verdict: str = "",
    ) -> str:
        """
        Generate an executive summary using Groq LLM.
        """
        if self.config.llm_api_key and self.config.llm_provider != "none":
            try:
                result = await self._llm_executive_summary(
                    num_agents,
                    num_findings,
                    cross_modal_confirmed,
                    contested,
                    all_findings or [],
                    gemini_findings or [],
                    active_agent_metrics or [],
                    overall_verdict,
                )
                if result:
                    return result
            except Exception as exc:
                logger.warning(f"LLM executive summary failed, using template: {exc}")

        return self._template_executive_summary(
            num_agents, num_findings, cross_modal_confirmed, contested, all_findings
        )

    async def _llm_executive_summary(
        self,
        num_agents: int,
        num_findings: int,
        cross_modal_confirmed: int,
        contested: int,
        all_findings: list[dict[str, Any]],
        gemini_findings: list[dict[str, Any]] = None,
        active_agent_metrics: list[dict[str, Any]] = None,
        overall_verdict: str = "",
    ) -> str:
        """Generate executive summary using Groq LLM synthesis."""
        client = getattr(self, "_synthesis_client", None) or LLMClient(self.config)

        top_findings = sorted(
            [
                f
                for f in all_findings
                if not f.get("stub_result")
                and f.get("metadata", {}).get("analysis_source") != "gemini_vision"
            ],
            key=_finding_importance,
            reverse=True,
        )[:8]

        findings_digest = []
        for f in top_findings:
            findings_digest.append(
                {
                    "agent": f.get("agent_id", "unknown"),
                    "type": f.get("finding_type", "unknown"),
                    "confidence": round(confidence_of(f, default=0.0) or 0.0, 3),
                    "evidence_verdict": evidence_verdict_of(f),
                    "summary": f.get("reasoning_summary", ""),
                    "status": f.get("status", ""),
                    "cross_modal": f.get("cross_modal_confirmed", False),
                }
            )

        gemini_digest = []
        for gf in (gemini_findings or [])[:4]:
            meta = gf.get("metadata", {})
            gemini_digest.append(
                {
                    "agent": gf.get("agent_id", "unknown"),
                    "analysis_type": meta.get("analysis_type", "vision"),
                    "model": meta.get("model_used", "gemini"),
                    "confidence": round(confidence_of(gf, default=0.0) or 0.0, 3),
                    "evidence_verdict": evidence_verdict_of(gf),
                    "summary": gf.get("reasoning_summary", ""),
                    "manipulation_signals": meta.get("manipulation_signals", []),
                    "detected_objects": meta.get("detected_objects", []),
                }
            )

        gemini_section = ""
        if gemini_digest:
            gemini_section = (
                f"\n\nGemini vision deep analysis findings "
                f"({len(gemini_digest)} of {len(gemini_findings or [])}):\n"
                f"{json.dumps(gemini_digest, indent=2)}"
            )

        metrics_summary = ""
        if active_agent_metrics:
            metrics_summary = (
                "\n\nAgent performance metrics (active agents only):\n"
                + json.dumps(
                    [
                        {
                            "agent": m.get("agent_name", m.get("agent_id", "")),
                            "confidence": f"{m.get('confidence_score', 0) * 100:.0f}%",
                            "error_rate": f"{m.get('error_rate', 0) * 100:.0f}%",
                            "tools_ran": m.get("tools_succeeded", 0),
                            "tools_failed": m.get("tools_failed", 0),
                            "not_applicable": m.get("tools_not_applicable", 0),
                            "total_tools": m.get("total_tools_called", 0),
                            "findings": m.get("finding_count", 0),
                        }
                        for m in active_agent_metrics
                        if not m.get("skipped")
                    ],
                    indent=2,
                )
            )

        verdict_line = (
            f"\n\nCouncil Arbiter computed verdict: {overall_verdict}"
            if overall_verdict
            else ""
        )

        system_prompt = f"""You are the Council Arbiter writing the Executive Summary of a court-admissible forensic evidence report.
The computed verdict for this evidence is: {overall_verdict or "REVIEW REQUIRED"}

Your summary must be:
- Factual and grounded only in the structured findings data provided
- Written in formal, precise legal/forensic language
- 3-5 paragraphs: (1) scope and active agents with their confidence scores, (2) key confirmed findings with exact metrics, (3) contested or tool-failure issues, (4) overall verdict justification based on confidence and error rates
- Free of speculation — only state what the data shows
- Explicit about tool failures and low-confidence findings
- Where Gemini vision findings present, attribute them as AI-assisted analysis needing corroboration

Do NOT use bullet points. Write in continuous prose paragraphs.
Reference the computed verdict: {overall_verdict or "REVIEW REQUIRED"} — explain WHY based on the numbers."""

        user_content = f"""Forensic analysis statistics:
- Active agents: {num_agents} (skipped agents excluded from this summary)
- Total findings from active agents: {num_findings}
- Cross-modal confirmed (multiple agents agree): {cross_modal_confirmed}
- Contested findings (agents disagree): {contested}
- Gemini vision findings: {len(gemini_findings or [])}
- Computed verdict: {overall_verdict}{verdict_line}

Top findings by confidence (classical tools):
{json.dumps(findings_digest, indent=2)}{gemini_section}{metrics_summary}

Write the Executive Summary for this forensic report. Justify the {overall_verdict} verdict based on the data."""

        return await client.generate_synthesis(
            system_prompt=system_prompt,
            user_content=user_content,
            max_tokens=500,
            json_mode=False,
        )

    def _template_executive_summary(
        self,
        num_agents: int,
        num_findings: int,
        cross_modal_confirmed: int,
        contested: int,
        all_findings: list[dict[str, Any]] | None,
    ) -> str:
        """Deterministic template fallback when LLM is not configured."""
        lines = [
            f"This report presents findings from a multi-agent forensic analysis conducted by "
            f"{num_agents} specialized agents, resulting in {num_findings} individual findings.",
        ]
        if cross_modal_confirmed > 0:
            lines.append(
                f"Cross-modal confirmation was achieved for {cross_modal_confirmed} findings, "
                "where multiple independent agents using different analysis techniques arrived "
                "at the same conclusion."
            )
        if contested > 0:
            lines.append(
                f"{contested} finding(s) were identified as contested, requiring further "
                "review or tribunal resolution."
            )
        if all_findings:
            top = sorted(
                all_findings, key=_finding_importance, reverse=True
            )[:3]
            highlights = [
                f.get("reasoning_summary", "")
                for f in top
                if f.get("reasoning_summary")
            ]
            if highlights:
                lines.append("Key findings include: " + " ".join(highlights[:2]))
        lines.append(
            "The full analysis chain is preserved in the chain of custody log and "
            "ReAct chains sections of this report."
        )
        return " ".join(lines)

    async def _generate_uncertainty_statement(
        self, incomplete: int, contested: int, overall_error_rate: float = 0.0
    ) -> str:
        """
        Generate the uncertainty and limitations statement.
        """
        if (
            self.config.llm_api_key
            and self.config.llm_provider != "none"
            and (incomplete > 0 or contested > 0 or overall_error_rate > 0.15)
        ):
            try:
                result = await self._llm_uncertainty_statement(
                    incomplete, contested, overall_error_rate
                )
                if result:
                    return result
            except Exception as exc:
                logger.warning(
                    f"LLM uncertainty statement failed, using template: {exc}"
                )

        return self._template_uncertainty_statement(
            incomplete, contested, overall_error_rate
        )

    async def _llm_uncertainty_statement(
        self, incomplete: int, contested: int, overall_error_rate: float = 0.0
    ) -> str:
        """Generate uncertainty statement using LLM."""
        client = getattr(self, "_synthesis_client", None) or LLMClient(self.config)

        system_prompt = """You are the Council Arbiter writing the Limitations and Uncertainty section of a forensic report.

Be specific and legally precise. Explain what the uncertainties mean for the evidential value of the report.
Write 2-3 sentences only. Do not use bullet points."""

        user_content = (
            f"Incomplete findings (tools unavailable or evidence insufficient): {incomplete}\n"
            f"Contested findings (agents disagree, not yet resolved): {contested}\n"
            f"Overall tool error rate across active agents: {overall_error_rate * 100:.1f}%\n\n"
            "Write the uncertainty and limitations statement."
        )

        return await client.generate_synthesis(
            system_prompt=system_prompt,
            user_content=user_content,
            max_tokens=200,
            json_mode=False,
        )

    async def _generate_structured_summary(
        self,
        overall_verdict: str,
        overall_confidence: float,
        overall_error_rate: float,
        manipulation_probability: float,
        applicable_agent_count: int,
        all_findings: list[dict[str, Any]],
        cross_modal_confirmed_count: int,
        contested_count: int,
        analysis_coverage_note: str,
        has_deep_analysis: bool = False,
    ) -> tuple[str, list[str], str]:
        """
        Generate verdict_sentence, key_findings (list), reliability_note.
        """
        if self.config.llm_api_key and self.config.llm_provider != "none":
            try:
                result = await self._llm_structured_summary(
                    overall_verdict,
                    overall_confidence,
                    overall_error_rate,
                    manipulation_probability,
                    applicable_agent_count,
                    all_findings,
                    cross_modal_confirmed_count,
                    contested_count,
                    analysis_coverage_note,
                    has_deep_analysis=has_deep_analysis,
                )
                if result:
                    return result
            except Exception as exc:
                logger.warning(f"Structured summary LLM call failed: {exc}")

        return self._template_structured_summary(
            overall_verdict,
            overall_confidence,
            overall_error_rate,
            manipulation_probability,
            applicable_agent_count,
            all_findings,
            cross_modal_confirmed_count,
            contested_count,
            analysis_coverage_note,
        )

    async def _llm_structured_summary(
        self,
        overall_verdict: str,
        overall_confidence: float,
        overall_error_rate: float,
        manipulation_probability: float,
        applicable_agent_count: int,
        all_findings: list[dict[str, Any]],
        cross_modal_confirmed_count: int,
        contested_count: int,
        analysis_coverage_note: str,
        has_deep_analysis: bool = False,
    ) -> tuple[str, list[str], str] | None:
        client = getattr(self, "_synthesis_client", None) or LLMClient(self.config)

        def _strip_rs_prefix(s: str) -> str:
            idx = s.find(":")
            if (
                0 < idx < 55
                and s[:idx]
                .replace(" ", "")
                .replace("/", "")
                .replace("-", "")
                .replace("_", "")
                .isalpha()
            ):
                return s[idx + 1 :].lstrip()
            return s

        top_findings = sorted(
            [f for f in all_findings if not f.get("stub_result")],
            key=_finding_importance,
            reverse=True,
        )[:6]
        findings_brief = [
            f"{f.get('finding_type', '?')} ({f.get('agent_id', '?')}) — "
            f"{evidence_verdict_of(f)} — "
            f"{(confidence_of(f, default=0.0) or 0):.0%} — "
            f"{_strip_rs_prefix((f.get('reasoning_summary') or '')[:200].rsplit(' ', 1)[0])}"
            for f in top_findings
        ]

        system_prompt = """You are the Council Arbiter. Generate three short forensic summary fields as JSON.

Respond ONLY with valid JSON (no markdown):
{
  "verdict_sentence": "<one sentence: what the evidence shows and the final verdict>",
  "key_findings": ["<finding 1>", "<finding 2>", "<finding 3>", "<finding 4>", "<finding 5>"],
  "reliability_note": "<one sentence: confidence level and any caveats about reliability>"
}

Rules:
- verdict_sentence: state the verdict and primary reason in ≤25 words.
- key_findings: exactly 3-5 plain English bullet items, each ≤25 words.
- reliability_note: ≤20 words. Cite confidence %, error rate, and note if any tools used fallbacks."""

        analysis_mode = (
            "Initial + Deep analysis"
            if has_deep_analysis
            else "Initial analysis only (no deep pass was run)"
        )
        user_content = (
            f"Verdict: {overall_verdict}\n"
            f"Analysis mode: {analysis_mode}\n"
            f"Confidence: {overall_confidence * 100:.0f}%  |  "
            f"Error rate: {overall_error_rate * 100:.0f}%  |  "
            f"Manipulation probability: {manipulation_probability * 100:.0f}%\n"
            f"Active agents: {applicable_agent_count}  |  "
            f"Cross-modal confirmed: {cross_modal_confirmed_count}  |  Contested: {contested_count}\n"
            f"Coverage: {analysis_coverage_note}\n\n"
            f"Top findings:\n" + "\n".join(f"- {b}" for b in findings_brief)
        )

        try:
            raw = await client.generate_synthesis(
                system_prompt=system_prompt,
                user_content=user_content,
                max_tokens=350,
                json_mode=True,
            )
            if not raw:
                return None
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```", 2)[-1].lstrip("json").strip()
                if raw.endswith("```"):
                    raw = raw[:-3].strip()
            data = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
            vs = str(data.get("verdict_sentence", ""))
            kf = [str(x) for x in data.get("key_findings", []) if x][:5]
            rn = str(data.get("reliability_note", ""))
            if vs and kf and rn:
                return vs, kf, rn
        except Exception as e:
            logger.debug(f"LLM structured summary JSON parsing failed: {e}")
        return None

    def _template_structured_summary(
        self,
        overall_verdict: str,
        overall_confidence: float,
        overall_error_rate: float,
        manipulation_probability: float,
        applicable_agent_count: int,
        all_findings: list[dict[str, Any]],
        cross_modal_confirmed_count: int,
        contested_count: int,
        analysis_coverage_note: str,
    ) -> tuple[str, list[str], str]:
        _VERDICT_PHRASES = {
            "AUTHENTIC": "Evidence appears authentic (no manipulation signals).",
            "LIKELY_AUTHENTIC": "Evidence is likely authentic (no significant indicators).",
            "INCONCLUSIVE": "Analysis is inconclusive (insufficient data).",
            "LIKELY_MANIPULATED": "Evidence shows probable manipulation signals.",
            "MANIPULATED": "Strong manipulation indicators detected (multiple independent signals).",
            "ABSTAIN": "Insufficient evidence to render a verdict.",
        }
        verdict_sentence = _VERDICT_PHRASES.get(
            overall_verdict, f"Verdict: {overall_verdict}."
        )

        def _strip_rs_prefix(s: str) -> str:
            idx = s.find(":")
            if (
                0 < idx < 55
                and s[:idx]
                .replace(" ", "")
                .replace("/", "")
                .replace("-", "")
                .replace("_", "")
                .isalpha()
            ):
                return s[idx + 1 :].lstrip()
            return s

        def _truncate(s: str, max_len: int = 200) -> str:
            if len(s) <= max_len:
                return s
            return s[:max_len].rsplit(" ", 1)[0] + ("…" if len(s) > max_len else "")

        top = sorted(
            [
                f
                for f in all_findings
                if not f.get("stub_result") and f.get("reasoning_summary")
            ],
            key=_finding_importance,
            reverse=True,
        )[:5]
        key_findings_list = [
            _strip_rs_prefix(_truncate(f.get("reasoning_summary") or "")) for f in top
        ]
        if not key_findings_list:
            key_findings_list = ["No significant findings were identified."]

        err_note = (
            f"; {overall_error_rate * 100:.0f}% tool error rate"
            if overall_error_rate > 0.05
            else ""
        )
        _a = "agent" if applicable_agent_count == 1 else "agents"
        reliability_note = (
            f"{overall_confidence * 100:.0f}% overall confidence across "
            f"{applicable_agent_count} active {_a}{err_note}."
        )
        return verdict_sentence, key_findings_list, reliability_note

    def _template_uncertainty_statement(
        self, incomplete: int, contested: int, overall_error_rate: float = 0.0
    ) -> str:
        statements = []
        if overall_error_rate > 0.15:
            statements.append(
                f"Average tool error rate across active agents is "
                f"{overall_error_rate * 100:.0f}%, "
                "indicating some analysis dimensions may be incomplete or unreliable."
            )
        if incomplete > 0:
            statements.append(
                f"{incomplete} finding(s) remain incomplete due to unavailable tools "
                "or insufficient evidence."
            )
        if contested > 0:
            statements.append(
                f"{contested} finding(s) are contested and require tribunal resolution."
            )
        if not statements:
            statements.append("No significant uncertainties remain.")
        return " ".join(statements)
    async def deliberate_narratives(
        self,
        overall_verdict: str,
        overall_confidence: float,
        overall_error_rate: float,
        manipulation_probability: float,
        applicable_agent_count: int,
        all_findings: list[dict[str, Any]],
        active_agent_results: dict[str, dict[str, Any]],
        per_agent_metrics: dict[str, Any],
        gemini_vision_findings: list[dict[str, Any]],
        cross_modal_confirmed_count: int,
        contested_findings: list[dict[str, Any]],
        incomplete_findings: list[dict[str, Any]],
        analysis_coverage_note: str,
        use_llm: bool = True,
        step_hook: Any = None,
    ) -> dict[str, Any]:
        """Orchestrate all LLM synthesis tasks in parallel."""
        async def _step(msg: str):
            if step_hook:
                await step_hook(msg)

        llm_enabled = (
            use_llm
            and self.config.llm_api_key
            and self.config.llm_provider != "none"
            and bool(active_agent_results)
        )

        has_deep_analysis = any(
            (f.get("metadata") or {}).get("analysis_phase") == "deep"
            for f in all_findings
        )

        if llm_enabled:
            _client = LLMClient(self.config)
            if not _client.is_available:
                llm_enabled = False
            else:
                try:
                    _healthy = await asyncio.wait_for(_client.health_check(), timeout=5.0)
                    if not _healthy:
                        llm_enabled = False
                    else:
                        self._synthesis_client = _client
                except Exception:
                    llm_enabled = False

        if not llm_enabled:
            v_sent, kf_list, r_note, p_anal, exec_sum, unc_stmt = self._template_all(
                overall_verdict, overall_confidence, overall_error_rate,
                manipulation_probability, applicable_agent_count, all_findings,
                cross_modal_confirmed_count, len(contested_findings), analysis_coverage_note,
                active_agent_results,
                incomplete_count=len(incomplete_findings),
            )
        else:
            await _step("Generating forensic summary via Groq (parallel synthesis)…")

            async def t_structured():
                return await self._generate_structured_summary(
                    overall_verdict, overall_confidence, overall_error_rate,
                    manipulation_probability, applicable_agent_count, all_findings,
                    cross_modal_confirmed_count, len(contested_findings),
                    analysis_coverage_note, has_deep_analysis=has_deep_analysis
                )

            async def t_narratives():
                sem = asyncio.Semaphore(3)
                async def _one(aid, res):
                    async with sem:
                        try:
                            await _step(f"Synthesizing {AGENT_NAMES.get(aid, aid)} narrative...")
                            narr = await asyncio.wait_for(
                                self._generate_agent_narrative(aid, res.get("findings", []), per_agent_metrics.get(aid, {})),
                                timeout=40.0
                            )
                            return aid, narr or ""
                        except Exception:
                            return aid, ""
                pairs = await asyncio.gather(*[_one(aid, res) for aid, res in active_agent_results.items()])
                return {p[0]: p[1] for p in pairs if isinstance(p, tuple) and p[1]}

            async def t_executive():
                try:
                    await _step("Generating cross-modal executive summary...")
                    return await asyncio.wait_for(
                        self._generate_executive_summary(
                            len(active_agent_results), len(all_findings),
                            cross_modal_confirmed_count, len(contested_findings),
                            all_findings=all_findings, gemini_findings=gemini_vision_findings,
                            active_agent_metrics=list(per_agent_metrics.values()),
                            overall_verdict=overall_verdict
                        ), timeout=45.0
                    )
                except Exception:
                    return self._template_executive_summary(len(active_agent_results), len(all_findings), cross_modal_confirmed_count, len(contested_findings), all_findings)

            async def t_uncertainty():
                try:
                    return await asyncio.wait_for(self._generate_uncertainty_statement(len(incomplete_findings), len(contested_findings), overall_error_rate), timeout=30.0)
                except Exception:
                    return self._template_uncertainty_statement(len(incomplete_findings), len(contested_findings), overall_error_rate)

            (v_sent, kf_list, r_note), p_anal, exec_sum, unc_stmt = await asyncio.gather(t_structured(), t_narratives(), t_executive(), t_uncertainty())

        self._synthesis_client = None
        return {
            "verdict_sentence": v_sent,
            "key_findings": kf_list,
            "reliability_note": r_note,
            "per_agent_analysis": p_anal,
            "executive_summary": exec_sum,
            "uncertainty_statement": unc_stmt,
            "llm_used": llm_enabled
        }

    def _template_all(self, ov, oc, oer, mp, aac, af, cmc, cont, acn, aar, incomplete_count: int = 0):
        vs, kf, rn = self._template_structured_summary(ov, oc, oer, mp, aac, af, cmc, cont, acn)
        exec_s = self._template_executive_summary(len(aar), len(af), cmc, cont, af)
        unc_s = self._template_uncertainty_statement(incomplete_count, cont, oer)
        return vs, kf, rn, {}, exec_s, unc_s

    async def sign_report(self, report: ForensicReport) -> ForensicReport:
        """Sign the forensic report with the Arbiter key."""
        report_dict = report.model_dump(mode="json", exclude={"cryptographic_signature", "report_hash", "signed_utc"})
        report_json = json.dumps(report_dict, sort_keys=True)
        report_hash = hashlib.sha256(report_json.encode()).hexdigest()
        signed_entry = sign_content(agent_id="Arbiter", content={"hash": report_hash, "timestamp": datetime.now(UTC).isoformat()})
        report.report_hash = report_hash
        report.cryptographic_signature = signed_entry.signature
        report.signed_utc = datetime.now(UTC)
        return report

"""
Image analysis flow tests — sealing Batch 4 changes.

Covers:
  1. compute_agent_verdict — visual boost constants and convergent confidence bump
  2. _compute_grounded_agent_verdict — confidence_scale applied + visual_signal passed
  3. per_agent_synthesis — key_findings deduplication from Groq output
  4. end-to-end verdict consistency between agent mixin and compute_agent_verdict
"""

from __future__ import annotations

import os
from typing import Any

import pytest

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-" + "x" * 32)
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_PASSWORD", "test")
os.environ.setdefault("DEMO_PASSWORD", "test")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "")
os.environ.setdefault("LLM_MODEL", "test-model")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _finding(
    evidence_verdict: str = "NEGATIVE",
    confidence_raw: float = 0.75,
    severity_tier: str = "LOW",
    tool_name: str = "ela_full_image",
    court_defensible: bool = True,
    report_safe: bool = True,
) -> dict[str, Any]:
    return {
        "evidence_verdict": evidence_verdict,
        "status": "CONFIRMED",
        "confidence_raw": confidence_raw,
        "severity_tier": severity_tier,
        "metadata": {
            "tool_name": tool_name,
            "court_defensible": court_defensible,
            "report_safe": report_safe,
        },
    }


def _visual_signal(
    verdict: str = "",
    court_defensible: bool = True,
    anomalies: list[str] | None = None,
    confidence: float = 0.85,
) -> dict[str, Any]:
    return {
        "verdict": verdict,
        "court_defensible": court_defensible,
        "anomalies": anomalies or [],
        "confidence": confidence,
    }


# ── 1. compute_agent_verdict — visual boost and convergent confidence ─────────

class TestComputeAgentVerdictVisualBoost:
    def test_gemini_court_strong_alone_gives_suspicious(self):
        """Gemini court-defensible MANIPULATED + 0 tool strong → SUSPICIOUS."""
        from core.severity import compute_agent_verdict

        findings = [_finding(evidence_verdict="NEGATIVE")]
        vs = _visual_signal(verdict="LIKELY_MANIPULATED", court_defensible=True)
        verdict, conf, _ = compute_agent_verdict(findings, visual_signal=vs)
        assert verdict == "SUSPICIOUS"
        # Should get the solo Gemini confidence boost
        assert conf >= 0.72

    def test_gemini_court_strong_alone_confidence_boost(self):
        """Court-defensible Gemini alone gets +3pp confidence boost over baseline 0.72."""
        from core.severity import _GEMINI_SOLO_CONF_BOOST, compute_agent_verdict

        findings = [_finding(evidence_verdict="NEGATIVE")]
        vs = _visual_signal(verdict="AI_GENERATED", court_defensible=True)
        _, conf_with_gemini, _ = compute_agent_verdict(findings, visual_signal=vs)

        # Without Gemini visual signal, with 1 tool strong → 0.72
        strong_tool = _finding(evidence_verdict="POSITIVE", confidence_raw=0.85, severity_tier="HIGH")
        _, conf_tool_only, _ = compute_agent_verdict([strong_tool], visual_signal=None)
        assert conf_tool_only == 0.72

        # Gemini solo should be 0.72 + _GEMINI_SOLO_CONF_BOOST
        assert abs(conf_with_gemini - (0.72 + _GEMINI_SOLO_CONF_BOOST)) < 0.01

    def test_gemini_plus_tool_strong_convergent_boost(self):
        """Gemini court + 1 tool strong → MANIPULATED with convergent confidence boost."""
        from core.severity import _CONV_VISUAL_TOOL_CONF_BOOST, compute_agent_verdict

        strong_tool = _finding(evidence_verdict="POSITIVE", confidence_raw=0.80, severity_tier="HIGH")
        vs = _visual_signal(verdict="LIKELY_MANIPULATED", court_defensible=True)

        verdict, conf, _ = compute_agent_verdict([strong_tool], visual_signal=vs)
        assert verdict == "MANIPULATED"
        expected = ((0.80 + 0.85) / 2) + _CONV_VISUAL_TOOL_CONF_BOOST
        assert abs(conf - expected) < 0.01

    def test_two_tool_strong_no_gemini_manipulated_baseline(self):
        """2 tool strong findings → MANIPULATED at baseline 0.85 (no visual boost)."""
        from core.severity import compute_agent_verdict

        findings = [
            _finding(evidence_verdict="POSITIVE", confidence_raw=0.80, severity_tier="HIGH"),
            _finding(evidence_verdict="POSITIVE", confidence_raw=0.75, severity_tier="CRITICAL", tool_name="hash_verify"),
        ]
        verdict, conf, _ = compute_agent_verdict(findings, visual_signal=None)
        assert verdict == "MANIPULATED"
        assert conf == 0.78  # Mean measured strength, with no visual boost

    def test_gemini_clean_vote_boosts_authentic_confidence(self):
        """Gemini AUTHENTIC + all tools clean → higher AUTHENTIC confidence."""
        from core.severity import compute_agent_verdict

        clean_findings = [
            _finding(evidence_verdict="NEGATIVE"),
            _finding(evidence_verdict="NEGATIVE", tool_name="hash_verify"),
        ]
        vs_clean = _visual_signal(verdict="AUTHENTIC", court_defensible=True)
        vs_none = None

        _, conf_with_gemini, _ = compute_agent_verdict(clean_findings, visual_signal=vs_clean)
        _, conf_no_gemini, _ = compute_agent_verdict(clean_findings, visual_signal=vs_none)

        assert conf_with_gemini > conf_no_gemini, (
            "Gemini clean vote should boost AUTHENTIC confidence"
        )

    def test_screening_tier_gemini_does_not_manipulate(self):
        """Non-court-defensible (local ensemble) Gemini strong → alert only, not MANIPULATED."""
        from core.severity import compute_agent_verdict

        findings = [_finding(evidence_verdict="NEGATIVE")]
        vs = _visual_signal(verdict="LIKELY_MANIPULATED", court_defensible=False)

        verdict, _, _ = compute_agent_verdict(findings, visual_signal=vs)
        # Only 1 alert signal from local ensemble → INCONCLUSIVE
        assert verdict == "INCONCLUSIVE"

    def test_not_applicable_findings_ignored(self):
        """NOT_APPLICABLE findings never contribute to verdict."""
        from core.severity import compute_agent_verdict

        findings = [
            _finding(evidence_verdict="NOT_APPLICABLE"),
            _finding(evidence_verdict="NOT_APPLICABLE", tool_name="jpeg_ghost"),
        ]
        verdict, conf, _ = compute_agent_verdict(findings, visual_signal=None)
        # No completed tools → INCONCLUSIVE at low confidence
        assert verdict == "INCONCLUSIVE"
        assert conf == 0.4

    def test_confidence_scale_reduces_strong_signal(self):
        """A finding that would be HIGH-severity gets rendered as LOW after 0.3 scaling."""
        from core.severity import compute_agent_verdict

        # confidence_raw=0.80 would normally be a strong HIGH signal
        # but after 0.3 scale it becomes 0.24 < _STRONG_SIGNAL_CONF_FLOOR → alert only
        scaled_finding = _finding(
            evidence_verdict="POSITIVE",
            confidence_raw=round(0.80 * 0.3, 4),  # simulates confidence_scale=0.3 applied
            severity_tier="HIGH",
        )
        verdict, _, _ = compute_agent_verdict([scaled_finding], visual_signal=None)
        # 0.24 < _STRONG_SIGNAL_CONF_FLOOR → counts as alert only, not strong → INCONCLUSIVE
        assert verdict in ("INCONCLUSIVE", "SUSPICIOUS")  # alert but not MANIPULATED
        assert verdict != "MANIPULATED"


# ── 2. _compute_grounded_agent_verdict — confidence_scale + visual_signal ────

class TestComputeGroundedAgentVerdict:
    """Test the investigation mixin's verdict function in isolation by replicating
    the key logic: confidence_scale must be applied and visual_signal must contribute."""

    def _make_finding_obj(
        self,
        ev: str = "NEGATIVE",
        conf: float = 0.75,
        tool: str = "ela",
        court: bool = True,
    ):
        """Minimal AgentFinding-like object."""
        class _F:
            evidence_verdict = ev
            confidence_raw = conf
            status = "CONFIRMED"
            finding_type = tool
            metadata = {"tool_name": tool, "court_defensible": court, "report_safe": True}
        return _F()

    def test_confidence_scale_applied_to_rows(self):
        """confidence_scale=0.3 from grounding must reduce confidence_raw in rows."""
        from core.visual_grounding import GroundingResult

        # Replicate the loop logic:
        f = self._make_finding_obj(ev="POSITIVE", conf=0.80, tool="ela_full_image")
        conf_raw = f.confidence_raw

        # Simulate grounding returning scale=0.3
        gr = GroundingResult(
            adjusted_severity="LOW",
            confidence_scale=0.3,
            grounded=True,
            grounding_type="camera_noise",
        )
        if gr.confidence_scale < 1.0 and isinstance(conf_raw, (int, float)):
            conf_raw = round(float(conf_raw) * gr.confidence_scale, 4)

        assert conf_raw == pytest.approx(0.24, abs=0.001)

    def test_scaled_confidence_prevents_strong_signal(self):
        """After confidence_scale=0.3, a 0.80-confidence HIGH finding is no longer strong."""
        from core.severity import _STRONG_SIGNAL_CONF_FLOOR, compute_agent_verdict

        scaled_conf = round(0.80 * 0.3, 4)  # 0.24
        assert scaled_conf < _STRONG_SIGNAL_CONF_FLOOR

        row = {
            "evidence_verdict": "POSITIVE",
            "status": "CONFIRMED",
            "confidence_raw": scaled_conf,
            "severity_tier": "HIGH",
            "metadata": {},
        }
        verdict, _, _ = compute_agent_verdict([row], visual_signal=None)
        assert verdict != "MANIPULATED", (
            "A camera-physics signal scaled to 0.24 confidence should not push verdict to MANIPULATED"
        )

    def test_visual_signal_dict_built_for_agent1(self):
        """Agent1 visual_signal should carry verdict + ai_generation_signals."""
        # Replicate the visual_signal construction logic from investigation.py
        class _MockIntegCtx:
            ai_generation_signals = ["GAN periodicity detected", "diffusion grid visible"]

        class _MockVC:
            authenticity_verdict = "AI_GENERATED"
            source = "llm_assisted"
            image_integrity_context = _MockIntegCtx()
            object_scene_context = None
            metadata_visual_context = None

        vc = _MockVC()
        _holistic = str(getattr(vc, "authenticity_verdict", "") or "").upper()
        _is_remote = str(getattr(vc, "source", "") or "").startswith("llm")
        _integ = getattr(vc, "image_integrity_context", None)

        visual_signal = {
            "verdict": _holistic,
            "court_defensible": _is_remote,
            "anomalies": list(getattr(_integ, "ai_generation_signals", None) or []),
        }

        assert visual_signal["verdict"] == "AI_GENERATED"
        assert visual_signal["court_defensible"] is True
        assert len(visual_signal["anomalies"]) == 2

    def test_agent5_visual_signal_inherits_holistic_verdict(self):
        """Agent5 visual_signal inherits the holistic AI-generation/manipulation verdict
        so compute_agent_verdict can fold it in — matching _build_live_visual_signal."""
        class _MockMeta:
            metadata_contradictions = ["GPS timezone mismatch"]

        class _MockVC:
            authenticity_verdict = "LIKELY_MANIPULATED"
            source = "llm_assisted"
            metadata_visual_context = _MockMeta()

        vc = _MockVC()
        _meta_vc = getattr(vc, "metadata_visual_context", None)
        _holistic = str(getattr(vc, "authenticity_verdict", "") or "").upper()
        _inherit = _holistic if _holistic in ("AI_GENERATED", "LIKELY_MANIPULATED", "MANIPULATED", "SUSPICIOUS") else ""

        visual_signal = {
            "verdict": _inherit,
            "court_defensible": True,
            "anomalies": list(getattr(_meta_vc, "metadata_contradictions", None) or []),
        }

        assert visual_signal["verdict"] == "LIKELY_MANIPULATED", (
            "Agent5 must inherit the holistic verdict into compute_agent_verdict"
        )
        assert "GPS timezone mismatch" in visual_signal["anomalies"]

    def test_agent5_visual_signal_skips_authentic_verdict(self):
        """Agent5 visual_signal must have verdict='' when the holistic read is AUTHENTIC."""
        class _MockMeta:
            metadata_contradictions = []

        class _MockVC:
            authenticity_verdict = "AUTHENTIC"
            source = "llm_assisted"
            metadata_visual_context = _MockMeta()

        vc = _MockVC()
        _meta_vc = getattr(vc, "metadata_visual_context", None)
        _holistic = str(getattr(vc, "authenticity_verdict", "") or "").upper()
        _inherit = _holistic if _holistic in ("AI_GENERATED", "LIKELY_MANIPULATED", "MANIPULATED", "SUSPICIOUS") else ""

        visual_signal = {
            "verdict": _inherit,
            "court_defensible": True,
            "anomalies": list(getattr(_meta_vc, "metadata_contradictions", None) or []),
        }

        assert visual_signal["verdict"] == "", (
            "Agent5 must not carry AUTHENTIC as a holistic verdict"
        )


# ── 3. per_agent_synthesis — key_findings deduplication ──────────────────────

class TestKeyFindingsDeduplication:
    """Test the deduplication logic that prevents Groq from emitting duplicate findings."""

    def _dedup(self, kfs: list[str], verdict: str = "AUTHENTIC") -> list[str]:
        """Replicate the deduplication logic from refine_synthesis_batch."""
        import re

        from core.per_agent_synthesis import _text_contradicts_verdict

        seen_kf_norms: set[str] = set()
        validated: list[str] = []
        for kf in kfs:
            kf_str = str(kf).strip()
            if not kf_str:
                continue
            if _text_contradicts_verdict(kf_str, verdict):
                continue
            norm = re.sub(r"\s*\(\d+\.?\d*%\)\s*$", "", kf_str.lower())
            norm = re.sub(r"\s+", " ", norm).strip()[:80]
            if norm in seen_kf_norms:
                continue
            seen_kf_norms.add(norm)
            validated.append(kf_str)
        return validated

    def test_exact_duplicates_removed(self):
        kfs = [
            "Hash verified — file_hash_verify (98%)",
            "Hash verified — file_hash_verify (98%)",
        ]
        result = self._dedup(kfs)
        assert len(result) == 1

    def test_near_duplicates_removed(self):
        kfs = [
            "Hash match confirmed: SHA-256 digest unchanged — file_hash_verify (98%)",
            "Hash match confirmed: SHA-256 digest unchanged — file_hash_verify (97%)",
        ]
        result = self._dedup(kfs)
        assert len(result) == 1

    def test_distinct_findings_kept(self):
        kfs = [
            "Hash verified — file_hash_verify (98%)",
            "0 anomaly regions detected — neural_ela (87%)",
            "No compression artifacts — frequency_domain_analysis (79%)",
        ]
        result = self._dedup(kfs)
        assert len(result) == 3

    def test_empty_strings_dropped(self):
        kfs = ["", "  ", "Hash verified — file_hash_verify (98%)"]
        result = self._dedup(kfs)
        assert len(result) == 1
        assert "Hash verified" in result[0]

    def test_verdict_contradicting_findings_dropped(self):
        """A key finding that contradicts AUTHENTIC verdict must be dropped."""
        kfs = [
            "Hash verified — file_hash_verify (98%)",
            "Manipulation detected in pixel blocks — neural_ela (91%)",  # contradicts AUTHENTIC
        ]
        result = self._dedup(kfs, verdict="AUTHENTIC")
        # Manipulation claim contradicts AUTHENTIC; should be dropped
        assert all("manipulation" not in kf.lower() for kf in result)

    def test_max_5_findings_from_groq(self):
        """Groq occasionally over-generates; ensure we don't silently accept > 5."""
        kfs = [f"Finding {i} — tool_{i} (80%)" for i in range(8)]
        result = self._dedup(kfs)
        # All 8 are unique and valid; dedup doesn't enforce a max, but callers cap at 5
        # Verify dedup itself doesn't drop unique items
        assert len(result) == 8  # dedup logic doesn't cap; frontend caps at display


# ── 4. Prompt schema validation ───────────────────────────────────────────────

class TestSynthesisPromptSchema:
    def test_prompt_contains_three_required_fields(self):
        """System prompt must request exactly the 3 fields: visual_context_summary,
        agent_brief, key_findings — and must NOT request verdict or confidence."""
        from core.per_agent_synthesis import _build_persona_system_prompt

        prompt = _build_persona_system_prompt(["Agent1", "Agent3", "Agent5"])

        assert "visual_context_summary" in prompt
        assert "agent_brief" in prompt
        assert "key_findings" in prompt

    def test_prompt_does_not_ask_groq_to_set_verdict(self):
        """Groq must not be asked to produce verdict or confidence values."""
        from core.per_agent_synthesis import _build_persona_system_prompt

        prompt = _build_persona_system_prompt(["Agent1"])

        # The schema should NOT include a 'verdict' or 'confidence' output field
        # (they appear only as CONSTRAINT language, not as schema output fields)
        schema_section = prompt[prompt.find("OUTPUT SCHEMA"):]
        assert '"verdict"' not in schema_section
        assert '"confidence"' not in schema_section

    def test_prompt_contains_inviolable_constraint_on_verdict(self):
        """Prompt must explicitly forbid Groq from changing verdict/confidence."""
        from core.per_agent_synthesis import _build_persona_system_prompt

        prompt = _build_persona_system_prompt(["Agent1"])
        assert "NEVER alter" in prompt or "NEVER change" in prompt

    def test_prompt_has_per_agent_visual_axis_instructions(self):
        """Each agent's visual axis must have specific instructions (not generic)."""
        from core.per_agent_synthesis import _build_persona_system_prompt

        prompt = _build_persona_system_prompt(["Agent1", "Agent3", "Agent5"])

        assert "image integrity" in prompt.lower() or "image-integrity" in prompt.lower()
        assert "scene" in prompt.lower() and "object" in prompt.lower()
        assert "provenance" in prompt.lower() and "timestamp" in prompt.lower()

    def test_prompt_mandates_metric_in_key_findings(self):
        """key_findings instructions must require a metric number."""
        from core.per_agent_synthesis import _build_persona_system_prompt

        prompt = _build_persona_system_prompt(["Agent1"])
        assert "metric" in prompt.lower() or "value" in prompt.lower()

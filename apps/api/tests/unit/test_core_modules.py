"""
Unit tests for core modules: calibration, cross_modal_fusion, synthesis.

These tests target the logic paths that were previously uncovered and bring
calibration.py, cross_modal_fusion.py, and synthesis.py above the 75% gate.
"""

from __future__ import annotations

import os

# ── Minimal env before any backend import ────────────────────────────────────
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-abcdefghijklmnopqrstuvwxyz123456")
os.environ.setdefault("POSTGRES_USER", "test_user")
os.environ.setdefault("POSTGRES_PASSWORD", "test_pass")
os.environ.setdefault("POSTGRES_DB", "forensic_test")
os.environ.setdefault("REDIS_PASSWORD", "test_redis_pass")
os.environ.setdefault("NEXT_PUBLIC_DEMO_PASSWORD", "test_demo_pass")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_MODEL", "test-model")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-key-abcdefghijklmnopqrstuvwxyz1234")

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ═══════════════════════════════════════════════════════════════════════════════
# 1. CalibrationLayer
# ═══════════════════════════════════════════════════════════════════════════════

class TestCalibrationLayer:
    """Tests for core/calibration.py — CalibrationLayer and helpers."""

    def _make_layer(self, tmp_path: Path) -> CalibrationLayer:  # noqa: F821
        from core.calibration import CalibrationLayer
        return CalibrationLayer(models_path=str(tmp_path))

    # ── fit_default_model ────────────────────────────────────────────────────

    def test_fit_default_model_returns_uncalibrated(self, tmp_path):
        from core.calibration import CalibrationStatus

        layer = self._make_layer(tmp_path)
        model = layer.fit_default_model("agent1_image")

        assert model.agent_id == "agent1_image"
        assert model.calibration_status == CalibrationStatus.UNCALIBRATED

    def test_fit_default_model_writes_files(self, tmp_path):

        layer = self._make_layer(tmp_path)
        layer.fit_default_model("agent1_image")

        latest_path = tmp_path / "agent1_image" / "latest.json"
        assert latest_path.exists()
        with open(latest_path) as f:
            data = json.load(f)
        assert data["agent_id"] == "agent1_image"

    def test_fit_default_model_uses_per_agent_params(self, tmp_path):

        layer = self._make_layer(tmp_path)
        model = layer.fit_default_model("agent5_metadata")

        # agent5_metadata has A=3.0, B=-1.5
        assert model.params["A"] == 3.0
        assert model.params["B"] == -1.5

    def test_fit_default_model_unknown_agent_uses_defaults(self, tmp_path):

        layer = self._make_layer(tmp_path)
        model = layer.fit_default_model("unknown_agent")

        # Falls back to generic defaults
        assert model.params["A"] == 2.0
        assert model.params["B"] == -1.0

    # ── load_model ───────────────────────────────────────────────────────────

    def test_load_model_missing_raises_file_not_found(self, tmp_path):

        layer = self._make_layer(tmp_path)
        with pytest.raises(FileNotFoundError, match="agent1_image"):
            layer.load_model("agent1_image", "v99_does_not_exist")

    def test_load_model_caches_result(self, tmp_path):

        layer = self._make_layer(tmp_path)
        layer.fit_default_model("agent2_audio")

        m1 = layer.load_model("agent2_audio", "latest")
        m2 = layer.load_model("agent2_audio", "latest")
        assert m1 is m2, "load_model must return the same object from cache"

    def test_load_model_falls_back_to_latest_json(self, tmp_path):
        """When version='v_specific' is absent but directory has other JSON, load the latest."""

        layer = self._make_layer(tmp_path)
        model = layer.fit_default_model("agent3_object")
        version = model.version

        # Remove the specific version file but keep the directory
        versioned_file = tmp_path / "agent3_object" / f"{version}.json"
        versioned_file.unlink()

        # Requesting a nonexistent version should load the remaining "latest.json"
        loaded = layer.load_model("agent3_object", "nonexistent_version")
        assert loaded.agent_id == "agent3_object"

    def test_load_model_empty_directory_raises(self, tmp_path):

        layer = self._make_layer(tmp_path)
        agent_dir = tmp_path / "empty_agent"
        agent_dir.mkdir()

        with pytest.raises(FileNotFoundError):
            layer.load_model("empty_agent", "missing")

    # ── list_versions ────────────────────────────────────────────────────────

    def test_list_versions_empty_when_no_dir(self, tmp_path):

        layer = self._make_layer(tmp_path)
        assert layer.list_versions("no_such_agent") == []

    def test_list_versions_excludes_latest(self, tmp_path):

        layer = self._make_layer(tmp_path)
        layer.fit_default_model("agent4_video")
        versions = layer.list_versions("agent4_video")

        assert "latest" not in versions
        assert len(versions) >= 1

    # ── calibrate ────────────────────────────────────────────────────────────

    def test_calibrate_returns_calibrated_confidence(self, tmp_path):
        from core.calibration import CalibrationStatus

        layer = self._make_layer(tmp_path)
        result = layer.calibrate("agent1_image", raw_score=0.7, finding_class="ela_high")

        assert result.raw_score == 0.7
        assert 0.0 <= result.raw_confidence_score <= 1.0
        assert result.calibration_status == CalibrationStatus.UNCALIBRATED

    def test_calibrate_court_statement_warns_uncalibrated(self, tmp_path):

        layer = self._make_layer(tmp_path)
        result = layer.calibrate("agent2_audio", raw_score=0.6, finding_class="voice_clone")

        assert "NOT court-admissible" in result.court_statement
        assert "UNCALIBRATED" in result.court_statement

    def test_calibrate_handles_none_score(self, tmp_path):
        """When raw_score is None it should default to 0.5 without crashing."""

        layer = self._make_layer(tmp_path)
        # raw_score=None is passed directly — the code defaults it to 0.5
        result = layer.calibrate("agent3_object", raw_score=None, finding_class="test")  # type: ignore[arg-type]
        assert result.raw_score == 0.5

    def test_calibrate_computes_confidence_interval(self, tmp_path):

        layer = self._make_layer(tmp_path)
        result = layer.calibrate("agent4_video", raw_score=0.5, finding_class="motion")

        assert result.confidence_interval is not None
        ci = result.confidence_interval
        assert "lower" in ci
        assert "upper" in ci
        assert ci["lower"] <= ci["upper"]

    def test_calibrate_uncertainty_decomposition_present(self, tmp_path):

        layer = self._make_layer(tmp_path)
        result = layer.calibrate("agent5_metadata", raw_score=0.3, finding_class="exif_anomaly")

        assert result.uncertainty is not None
        u = result.uncertainty
        assert 0.0 <= u.total_uncertainty <= 1.0
        assert 0.0 <= u.epistemic_uncertainty <= 1.0
        assert 0.0 <= u.aleatoric_uncertainty <= 1.0

    # ── _bootstrap_ci ────────────────────────────────────────────────────────

    def test_bootstrap_ci_platt_returns_valid_interval(self, tmp_path):

        layer = self._make_layer(tmp_path)
        params = {"A": 2.5, "B": -1.2, "method": "platt"}
        ci = layer._bootstrap_ci(raw_score=0.6, params=params, method="platt", n_bootstrap=200)

        assert ci["lower"] <= ci["upper"]
        assert 0.0 <= ci["lower"] <= 1.0
        assert 0.0 <= ci["upper"] <= 1.0
        assert "platt" in ci["method"]

    def test_bootstrap_ci_sigmoid_returns_valid_interval(self, tmp_path):

        layer = self._make_layer(tmp_path)
        params = {"k": 10.0, "x0": 0.5, "method": "sigmoid"}
        ci = layer._bootstrap_ci(raw_score=0.5, params=params, method="sigmoid", n_bootstrap=200)

        assert ci["lower"] <= ci["upper"]
        assert "sigmoid" in ci["method"]

    # ── _decompose_uncertainty ────────────────────────────────────────────────

    def test_decompose_uncertainty_escalates_uncalibrated_high_ci(self, tmp_path):

        layer = self._make_layer(tmp_path)
        ci = {"lower": 0.1, "upper": 0.8}  # width=0.7 → triggers UNCALIBRATED escalation
        result = layer._decompose_uncertainty(
            raw_score=0.5,
            params={"A": 2.0, "B": -1.0},
            method="platt",
            ci=ci,
            is_uncalibrated=True,
        )

        assert result.should_escalate is True
        assert result.escalation_reason is not None
        assert "UNCALIBRATED" in result.escalation_reason

    def test_decompose_uncertainty_no_escalate_when_narrow_ci(self, tmp_path):

        layer = self._make_layer(tmp_path)
        ci = {"lower": 0.58, "upper": 0.62}  # very narrow CI
        result = layer._decompose_uncertainty(
            raw_score=0.9,  # high score → low aleatoric
            params={},
            method="platt",
            ci=ci,
            is_uncalibrated=False,
        )
        assert result.should_escalate is False


# ═══════════════════════════════════════════════════════════════════════════════
# 2. CrossModalFusion
# ═══════════════════════════════════════════════════════════════════════════════

class TestCrossModalFusion:
    """Tests for core/cross_modal_fusion.py — fuse() and helpers."""

    def _make_finding(
        self,
        finding_type: str = "test_finding",
        confidence: float = 0.8,
        status: str = "CONFIRMED",
        manipulation: bool = False,
        phase: str = "initial",
    ) -> dict:
        return {
            "finding_type": finding_type,
            "confidence_raw": confidence,
            "status": status,
            "reasoning_summary": "Test summary",
            "metadata": {
                "analysis_phase": phase,
                "splicing_detected": manipulation,
                "anomaly_detected": False,
            },
        }

    # ── _extract_signals ─────────────────────────────────────────────────────

    def test_extract_signals_maps_agents_to_modalities(self):
        from core.cross_modal_fusion import Modality, _extract_signals

        findings = {
            "Agent1": [self._make_finding()],
            "Agent3": [self._make_finding()],
        }
        signals = _extract_signals(findings)

        modalities = {s.modality for s in signals}
        assert Modality.IMAGE in modalities
        assert Modality.OBJECT in modalities

    def test_extract_signals_unknown_agent_skipped(self):
        from core.cross_modal_fusion import _extract_signals

        findings = {"UnknownAgent99": [self._make_finding()]}
        signals = _extract_signals(findings)
        assert signals == []

    def test_extract_signals_non_dict_finding_skipped(self):
        from core.cross_modal_fusion import _extract_signals

        findings = {"Agent1": ["not a dict", 42]}
        signals = _extract_signals(findings)
        assert signals == []

    def test_extract_signals_detects_manipulation_flags(self):
        from core.cross_modal_fusion import _extract_signals

        finding = {
            "finding_type": "face_swap",
            "confidence_raw": 0.9,
            "status": "CONFIRMED",
            "reasoning_summary": "",
            "metadata": {
                "analysis_phase": "deep",
                "face_swap_detected": True,
            },
        }
        signals = _extract_signals({"Agent4": [finding]})
        assert len(signals) == 1
        assert signals[0].manipulation_detected is True

    # ── _find_corroboration ──────────────────────────────────────────────────

    def test_corroboration_both_detect_manipulation(self):
        from core.cross_modal_fusion import Modality, ModalitySignal, _find_corroboration

        sig_a = ModalitySignal(
            modality=Modality.IMAGE, agent_id="Agent1",
            finding_type="ela", confidence=0.8,
            status="CONFIRMED", manipulation_detected=True,
        )
        sig_b = ModalitySignal(
            modality=Modality.OBJECT, agent_id="Agent3",
            finding_type="scene_incon", confidence=0.7,
            status="CONFIRMED", manipulation_detected=True,
        )
        result = _find_corroboration(sig_a, sig_b)
        assert result is not None
        assert "manipulation" in result["direction"]

    def test_corroboration_none_when_no_manipulation(self):
        from core.cross_modal_fusion import Modality, ModalitySignal, _find_corroboration

        sig_a = ModalitySignal(
            modality=Modality.IMAGE, agent_id="Agent1",
            finding_type="ela", confidence=0.8,
            status="CONFIRMED", manipulation_detected=False,
        )
        sig_b = ModalitySignal(
            modality=Modality.AUDIO, agent_id="Agent2",
            finding_type="voice", confidence=0.7,
            status="CONFIRMED", manipulation_detected=False,
        )
        result = _find_corroboration(sig_a, sig_b)
        assert result is None

    def test_corroboration_none_when_not_confirmed(self):
        from core.cross_modal_fusion import Modality, ModalitySignal, _find_corroboration

        sig_a = ModalitySignal(
            modality=Modality.IMAGE, agent_id="Agent1",
            finding_type="ela", confidence=0.8,
            status="CONTESTED", manipulation_detected=True,
        )
        sig_b = ModalitySignal(
            modality=Modality.OBJECT, agent_id="Agent3",
            finding_type="scene", confidence=0.7,
            status="CONFIRMED", manipulation_detected=True,
        )
        assert _find_corroboration(sig_a, sig_b) is None

    # ── _find_contradiction ──────────────────────────────────────────────────

    def test_contradiction_detected_when_disagreement(self):
        from core.cross_modal_fusion import Modality, ModalitySignal, _find_contradiction

        sig_a = ModalitySignal(
            modality=Modality.IMAGE, agent_id="Agent1",
            finding_type="ela", confidence=0.9,
            status="CONFIRMED", manipulation_detected=True,
        )
        sig_b = ModalitySignal(
            modality=Modality.METADATA, agent_id="Agent5",
            finding_type="exif", confidence=0.8,
            status="CONFIRMED", manipulation_detected=False,
        )
        result = _find_contradiction(sig_a, sig_b)
        assert result is not None
        assert "Agent1" in result["agents"]
        assert "Agent5" in result["agents"]

    def test_no_contradiction_when_both_agree(self):
        from core.cross_modal_fusion import Modality, ModalitySignal, _find_contradiction

        sig_a = ModalitySignal(
            modality=Modality.AUDIO, agent_id="Agent2",
            finding_type="voice", confidence=0.7,
            status="CONFIRMED", manipulation_detected=True,
        )
        sig_b = ModalitySignal(
            modality=Modality.VIDEO, agent_id="Agent4",
            finding_type="frame", confidence=0.8,
            status="CONFIRMED", manipulation_detected=True,
        )
        assert _find_contradiction(sig_a, sig_b) is None

    # ── fuse ─────────────────────────────────────────────────────────────────

    def test_fuse_empty_returns_insufficient(self):
        from core.cross_modal_fusion import CrossModalVerdict, fuse

        result = fuse({})
        assert result.verdict == CrossModalVerdict.INSUFFICIENT
        assert result.fused_confidence == 0.0

    def test_fuse_single_agent_independent(self):
        from core.cross_modal_fusion import CrossModalVerdict, fuse

        findings = {"Agent1": [self._make_finding(manipulation=False)]}
        result = fuse(findings)
        assert result.verdict in (CrossModalVerdict.INDEPENDENT, CrossModalVerdict.INSUFFICIENT)

    def test_fuse_two_corroborating_agents(self):
        from core.cross_modal_fusion import CrossModalVerdict, fuse

        findings = {
            "Agent1": [self._make_finding(manipulation=True, confidence=0.85)],
            "Agent3": [self._make_finding(manipulation=True, confidence=0.80)],
        }
        result = fuse(findings)
        assert result.verdict in (
            CrossModalVerdict.CORROBORATED, CrossModalVerdict.PARTIALLY_CORROBORATED
        )
        assert len(result.corroborations) >= 1

    def test_fuse_contradiction_verdict(self):
        from core.cross_modal_fusion import CrossModalVerdict, fuse

        findings = {
            "Agent1": [self._make_finding(manipulation=True, confidence=0.9)],
            "Agent5": [self._make_finding(manipulation=False, confidence=0.85)],
        }
        result = fuse(findings)
        assert result.verdict == CrossModalVerdict.CONTRADICTED
        assert len(result.contradictions) >= 1

    def test_fuse_three_corroborations_gives_corroborated(self):
        from core.cross_modal_fusion import CrossModalVerdict, fuse

        findings = {
            "Agent1": [self._make_finding(manipulation=True, confidence=0.9)],
            "Agent2": [self._make_finding(manipulation=True, confidence=0.85)],
            "Agent3": [self._make_finding(manipulation=True, confidence=0.88)],
            "Agent4": [self._make_finding(manipulation=True, confidence=0.87)],
        }
        result = fuse(findings)
        assert result.verdict == CrossModalVerdict.CORROBORATED

    def test_fuse_intra_agent_phase_contradiction(self):
        from core.cross_modal_fusion import fuse

        findings = {
            "Agent1": [
                self._make_finding(manipulation=True, phase="initial"),
                self._make_finding(manipulation=False, phase="deep"),
            ],
        }
        result = fuse(findings)
        assert any(
            "initial vs deep" in c.get("agents", "") for c in result.contradictions
        ), "Intra-agent phase contradiction must be flagged"

    def test_fuse_intra_agent_phase_corroboration(self):
        from core.cross_modal_fusion import fuse

        findings = {
            "Agent1": [
                self._make_finding(manipulation=True, phase="initial"),
                self._make_finding(manipulation=True, phase="deep"),
            ],
        }
        result = fuse(findings)
        assert any(
            "initial + deep" in c.get("agents", "") for c in result.corroborations
        ), "Intra-agent phase agreement must be recorded as corroboration"

    def test_fuse_confidence_within_bounds(self):
        from core.cross_modal_fusion import fuse

        findings = {
            "Agent1": [self._make_finding(manipulation=True, confidence=0.95)],
            "Agent3": [self._make_finding(manipulation=True, confidence=0.60)],
        }
        result = fuse(findings)
        assert 0.0 <= result.fused_confidence <= 1.0

    def test_fuse_rationale_mentions_corroborations(self):
        from core.cross_modal_fusion import fuse

        findings = {
            "Agent1": [self._make_finding(manipulation=True)],
            "Agent3": [self._make_finding(manipulation=True)],
        }
        result = fuse(findings)
        assert len(result.fusion_rationale) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. SynthesisService
# ═══════════════════════════════════════════════════════════════════════════════

class TestSynthesisService:
    """Tests for core/synthesis.py — SynthesisService.synthesize_findings."""

    def _make_finding(
        self,
        tool_name: str = "ela_full_image",
        confidence: float = 0.75,
        status: str = "CONFIRMED",
    ) -> AgentFinding:  # noqa: F821
        from core.react_loop import AgentFinding

        return AgentFinding(
            agent_id="Agent1_image",
            finding_type="ela_analysis",
            confidence_raw=confidence,
            status=status,
            reasoning_summary="Test reasoning.",
            metadata={"tool_name": tool_name, "court_defensible": True},
        )

    def _make_service(self) -> SynthesisService:  # noqa: F821
        from core.config import get_settings
        from core.synthesis import SynthesisService

        return SynthesisService(get_settings())

    def _make_artifact(self) -> MagicMock:
        artifact = MagicMock()
        artifact.file_path = "/tmp/test_evidence.jpg"
        artifact.mime_type = "image/jpeg"
        return artifact

    @pytest.mark.asyncio
    async def test_empty_findings_returns_empty_dict(self):
        service = self._make_service()
        result = await service.synthesize_findings(
            agent_id="Agent1_image",
            agent_name="Image Expert",
            findings=[],
            evidence_artifact=self._make_artifact(),
            tool_success_count=0,
            tool_error_count=0,
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_llm_success_path_returns_expected_keys(self):
        from core.config import get_settings
        from core.synthesis import SynthesisService

        service = SynthesisService(get_settings())

        llm_response = json.dumps({
            "verdict": "AUTHENTIC",
            "narrative_summary": "Evidence appears authentic based on ELA results.",
            "sections": [
                {"id": "pixel_integrity", "label": "Pixel-Level Integrity",
                 "opinion": "Consistent.", "severity": "LOW"}
            ]
        })

        with patch("core.synthesis.LLMClient") as MockLLM:
            mock_instance = AsyncMock()
            mock_instance.generate_synthesis = AsyncMock(return_value=llm_response)
            MockLLM.return_value = mock_instance

            findings = [self._make_finding()]
            result = await service.synthesize_findings(
                agent_id="Agent1_image",
                agent_name="Image Expert",
                findings=findings,
                evidence_artifact=self._make_artifact(),
                tool_success_count=5,
                tool_error_count=1,
            )

        assert result["verdict"] == "AUTHENTIC"
        assert "narrative_summary" in result
        assert "agent_confidence" in result
        assert "agent_error_rate" in result
        assert 0.0 <= result["agent_error_rate"] <= 1.0

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_gracefully(self):
        from core.config import get_settings
        from core.synthesis import SynthesisService

        service = SynthesisService(get_settings())

        with patch("core.synthesis.LLMClient") as MockLLM:
            mock_instance = AsyncMock()
            mock_instance.generate_synthesis = AsyncMock(
                side_effect=RuntimeError("Groq unavailable")
            )
            MockLLM.return_value = mock_instance

            findings = [self._make_finding(confidence=0.9)]
            result = await service.synthesize_findings(
                agent_id="Agent1_image",
                agent_name="Image Expert",
                findings=findings,
                evidence_artifact=self._make_artifact(),
                tool_success_count=3,
                tool_error_count=0,
            )

        # Fallback should still return valid structure
        assert "verdict" in result
        assert result["verdict"] in ("AUTHENTIC", "SUSPICIOUS", "INCONCLUSIVE")
        assert "narrative_summary" in result

    @pytest.mark.asyncio
    async def test_fallback_verdict_suspicious_on_low_confidence(self):
        from core.config import get_settings
        from core.synthesis import SynthesisService

        service = SynthesisService(get_settings())

        with patch("core.synthesis.LLMClient") as MockLLM:
            mock_instance = AsyncMock()
            mock_instance.generate_synthesis = AsyncMock(
                side_effect=RuntimeError("forced failure")
            )
            MockLLM.return_value = mock_instance

            # Low confidence (< 0.5) should produce SUSPICIOUS verdict
            findings = [self._make_finding(confidence=0.3), self._make_finding(confidence=0.2)]
            result = await service.synthesize_findings(
                agent_id="Agent1_image",
                agent_name="Image Expert",
                findings=findings,
                evidence_artifact=self._make_artifact(),
                tool_success_count=1,
                tool_error_count=4,  # error_rate=0.8 → also SUSPICIOUS
            )

        assert result["verdict"] == "SUSPICIOUS"

    @pytest.mark.asyncio
    async def test_llm_returns_markdown_json_stripped(self):
        """LLM wrapping JSON in ```json fences should be handled correctly."""
        from core.config import get_settings
        from core.synthesis import SynthesisService

        service = SynthesisService(get_settings())

        wrapped_response = '```json\n{"verdict": "TAMPERED", "narrative_summary": "Splicing detected.", "sections": []}\n```'

        with patch("core.synthesis.LLMClient") as MockLLM:
            mock_instance = AsyncMock()
            mock_instance.generate_synthesis = AsyncMock(return_value=wrapped_response)
            MockLLM.return_value = mock_instance

            findings = [self._make_finding()]
            result = await service.synthesize_findings(
                agent_id="Agent1_image",
                agent_name="Image Expert",
                findings=findings,
                evidence_artifact=self._make_artifact(),
                tool_success_count=1,
                tool_error_count=0,
            )

        assert result["verdict"] == "TAMPERED"

    @pytest.mark.asyncio
    async def test_agent_id_normalisation_agent2(self):
        """Agent IDs containing 'Agent2' should resolve to the Agent2 tool group."""
        from core.config import get_settings
        from core.react_loop import AgentFinding
        from core.synthesis import SynthesisService

        service = SynthesisService(get_settings())

        # Use a tool name that belongs to Agent2's groups
        finding = AgentFinding(
            agent_id="Agent2_audio",
            finding_type="voice_clone",
            confidence_raw=0.8,
            status="CONFIRMED",
            reasoning_summary="Voice analysis complete.",
            metadata={"tool_name": "voice_clone_detect", "court_defensible": True},
        )

        with patch("core.synthesis.LLMClient") as MockLLM:
            mock_instance = AsyncMock()
            mock_instance.generate_synthesis = AsyncMock(
                return_value=json.dumps({
                    "verdict": "SUSPICIOUS",
                    "narrative_summary": "Voice cloning detected.",
                    "sections": [],
                })
            )
            MockLLM.return_value = mock_instance

            result = await service.synthesize_findings(
                agent_id="Agent2_audio",
                agent_name="Audio Expert",
                findings=[finding],
                evidence_artifact=self._make_artifact(),
                tool_success_count=1,
                tool_error_count=0,
            )

        assert result["verdict"] == "SUSPICIOUS"

    def test_compact_metrics_skips_internal_keys(self):
        service = self._make_service()
        from core.react_loop import AgentFinding

        finding = AgentFinding(
            agent_id="Agent1",
            finding_type="ela",
            confidence_raw=0.7,
            status="CONFIRMED",
            reasoning_summary="ELA analysis complete.",
            metadata={
                "tool_name": "ela_full_image",        # SKIP_META
                "llm_synthesis": "some text",         # SKIP_META
                "anomaly_score": 0.42,                # keep
                "nested_dict": {"a": 1},              # skip (dict not in allowed types)
                "flag": True,                         # keep
            },
        )
        result = service._compact_metrics(finding)

        assert "tool_name" not in result
        assert "llm_synthesis" not in result
        assert result["anomaly_score"] == 0.42
        assert result["flag"] is True
        assert "nested_dict" not in result

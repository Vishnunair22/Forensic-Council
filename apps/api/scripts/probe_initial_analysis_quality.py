from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from PIL import Image, ImageDraw

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-" + "x" * 32)
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_PASSWORD", "test")
os.environ.setdefault("DEMO_PASSWORD", "test")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-" + "x" * 32)
os.environ.setdefault("GEMINI_API_KEY_POLICY_OK", "false")

from core.config import Settings
from core.evidence import ArtifactType, EvidenceArtifact
from core.gemini_client import GeminiVisionClient
from core.image_routing import build_image_forensic_routing
from core.react_loop import AgentFinding
from core.synthesis import SynthesisService
from core.handlers.image import ImageHandlers
from agents.mixins.investigation import AgentInvestigationMixin
from agents.arbiter import CouncilArbiter
from agents.arbiter_verdict import ForensicReport
from orchestration.pipeline_enrichment import _detect_visual_profile_provenance


SCENARIOS = {
    "person": {
        "category": "live_photograph",
        "description": "Portrait photo of a person standing indoors with normal lighting.",
        "tools": [
            ("file_hash_verify", "NEGATIVE", 1.0, {"hash_matches": True, "computed_hash": "a" * 64}),
            ("neural_ela", "NEGATIVE", 0.82, {"num_anomaly_regions": 0, "max_anomaly": 0.02}),
            ("frequency_domain_analysis", "NEGATIVE", 0.79, {"anomaly_score": 0.04, "high_freq_ratio": 0.18}),
        ],
    },
    "weapon": {
        "category": "object_scene",
        "description": "Camera photograph showing a handgun on a table next to keys.",
        "tools": [
            ("object_detection", "NEGATIVE", 0.74, {"object_count": 3, "labels": ["handgun", "table", "keys"]}),
            ("vector_contraband_search", "POSITIVE", 0.86, {"matches": ["handgun"], "concern_flag": True}),
            ("lighting_correlation_initial", "NEGATIVE", 0.76, {"consistency_score": 0.82}),
        ],
    },
    "crime_scene": {
        "category": "object_scene",
        "description": "Evidence photograph of a room with visible blood-like staining and a broken chair.",
        "tools": [
            ("object_detection", "NEGATIVE", 0.72, {"object_count": 4, "labels": ["chair", "stain", "floor"]}),
            ("scene_incongruence", "NEGATIVE", 0.70, {"matches": [], "scene_incongruent": False}),
            ("neural_ela", "NEGATIVE", 0.80, {"num_anomaly_regions": 0, "max_anomaly": 0.01}),
        ],
    },
    "web_page": {
        "category": "screenshot",
        "description": "Browser screenshot of a case management web page with tabs and visible UI text.",
        "tools": [
            ("extract_text_from_image", "NEGATIVE", 0.83, {"word_count": 38, "text": "Forensic Council Evidence Analysis"}),
            ("screenshot_layout_forensics", "NEGATIVE", 0.78, {"layout_anomaly_count": 0, "edge_density": 0.016}),
            ("detect_font_inconsistency", "NEGATIVE", 0.70, {"font_consistency_score": 0.61, "num_anomaly_regions": 2}),
        ],
    },
    "document": {
        "category": "document",
        "description": "Photograph of a signed invoice document with printed text and a date.",
        "tools": [
            ("extract_text_from_image", "NEGATIVE", 0.84, {"word_count": 112, "text": "Invoice Date 2026-05-29"}),
            ("neural_ela", "NEGATIVE", 0.76, {"num_anomaly_regions": 0, "max_anomaly": 0.02}),
            ("exif_extract", "NEGATIVE", 0.68, {"total_fields_extracted": 4, "datetime_original": "2026:05:29 10:22:00"}),
        ],
    },
    "product_object": {
        "category": "object_scene",
        "description": "Product photo of a sealed electronics box on a desk.",
        "tools": [
            ("object_detection", "NEGATIVE", 0.73, {"object_count": 2, "labels": ["box", "desk"]}),
            ("frequency_domain_analysis", "NEGATIVE", 0.80, {"anomaly_score": 0.03, "high_freq_ratio": 0.16}),
            ("file_structure_analysis", "NEGATIVE", 0.85, {"anomalies": [], "header_valid": True}),
        ],
    },
}


def _settings() -> Settings:
    return Settings(
        app_env="testing",
        signing_key="test-signing-key-" + "x" * 32,
        postgres_user="test",
        postgres_password="test",
        postgres_db="test",
        redis_password="test",
        DEMO_PASSWORD="test",
        jwt_secret_key="test-jwt-secret-" + "x" * 32,
        llm_provider="groq",
        llm_api_key="gsk_" + "x" * 40,
        llm_model="llama-3.3-70b-versatile",
        llm_enable_post_synthesis=True,
        gemini_api_key_policy_ok=False,
        bootstrap_admin_password="Admin_123!",
        bootstrap_investigator_password="Inv_123!",
    )


def _artifact(path: Path) -> EvidenceArtifact:
    return EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=str(path),
        content_hash="a" * 64,
        action="probe",
        agent_id="probe",
        session_id=uuid4(),
        metadata={"mime_type": "image/png"},
    )


def _make_probe_image(path: Path, label: str) -> None:
    img = Image.new("RGB", (720, 420), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle((20, 20, 700, 90), fill=(28, 36, 48))
    draw.text((40, 45), label, fill="white")
    draw.rectangle((80, 150, 260, 330), outline="black", width=3)
    draw.text((100, 230), "EVIDENCE", fill="black")
    img.save(path)


def _finding(tool: str, verdict: str, confidence: float, data: dict) -> AgentFinding:
    return AgentFinding(
        agent_id="Agent1",
        finding_type=tool.replace("_", " ").title(),
        confidence_raw=confidence,
        status="CONFIRMED",
        evidence_verdict=verdict,
        reasoning_summary=f"{tool} probe summary",
        metadata={"tool_name": tool, "court_defensible": True, **data},
    )


def _visual_context(name: str, scenario: dict) -> dict:
    return {
        "content_description": scenario["description"],
        "image_category": scenario["category"],
        "visual_verdict": "AUTHENTIC",
        "visual_confidence": 0.88,
        "priority_signals": [],
        "contextual_anomalies": [],
        "forensic_specifics": f"Probe scenario: {name}",
        "extracted_text": ["Forensic Council Evidence Analysis"] if name == "web_page" else [],
    }


async def probe_gemini_visual_parse() -> None:
    client = GeminiVisionClient(_settings())
    raw = json.dumps(
        {
            "content_type": "browser screenshot",
            "scene_description": "A forensic case management web page is open in a browser.",
            "extracted_text": ["Forensic Council", "Evidence Analysis"],
            "detected_objects": ["browser tab", "navigation bar"],
            "interface_identification": "web browser application UI",
            "contextual_narrative": "The screenshot shows an investigation dashboard.",
            "manipulation_signals": [],
            "metadata_visual_consistency": "No EXIF provided for cross-validation",
            "contradiction_audit": [],
            "authenticity_verdict": "AUTHENTIC",
            "confidence": 0.91,
            "forensic_routing": {
                "image_category": "screenshot",
                "priority_signals": ["ocr", "layout"],
                "skip_tools": [],
                "focus_regions": ["browser viewport"],
            },
            "forensic_specifics": "UI alignment and text rendering should be checked.",
        }
    )
    parsed = client._parse_response(raw, "deep_forensic_analysis", 42.0)
    as_dict = parsed.to_finding_dict("Agent1")
    routing = as_dict["metadata"]["forensic_routing"]
    assert "extract_text_from_image" in routing["recommended_initial_tools"]
    assert "noiseprint_cluster" in routing["skip_tools"]
    assert as_dict["metadata"]["interface_identification"] == "web browser application UI"
    print("gemini_visual_parse: PASS")


async def probe_groq_synthesis() -> None:
    class FakeLLM:
        provider = "groq"

        def __init__(self, *_args, **_kwargs):
            pass

        async def generate_synthesis(self, **_kwargs):
            return json.dumps(
                {
                    "agent_confidence": 0.88,
                    "agent_error_rate": 0.0,
                    "verdict": "AUTHENTIC",
                    "agent_brief": "The visual profile identified this evidence as a browser screenshot. 3 forensic tools ran: hash matched; OCR extracted 38 words; layout found 0 anomaly flags. Based on the visual-profile verdict and tool agreement, this evidence is assessed as AUTHENTIC with 88% confidence.",
                    "narrative_summary": "The submitted browser screenshot was checked as a digital UI capture, not a camera photograph. OCR and layout checks matched the visual profile, while hash custody confirmed the uploaded file remained unchanged after intake. The evidence is usable as an intact submitted screenshot, with no claim about original device capture time.",
                    "key_findings": [
                        "extract_text_from_image read 38 words from the visible UI text.",
                        "screenshot_layout_forensics found 0 layout anomaly flags.",
                        "file_hash_verify matched the intake SHA-256 hash.",
                    ],
                    "signal_weight": {"strongest_positive": "none", "strongest_negative": "file_hash_verify"},
                    "sections": [],
                }
            )

    scenario = SCENARIOS["web_page"]
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "web_page.png"
        _make_probe_image(path, "Forensic Council Web Page")
        service = SynthesisService(_settings())
        findings = [_finding(*tool_data) for tool_data in scenario["tools"]]
        with patch("core.synthesis.LLMClient", FakeLLM):
            result = await service.synthesize_findings(
                agent_id="Agent1",
                agent_name="Agent1_ImageIntegrity",
                findings=findings,
                evidence_artifact=_artifact(path),
                tool_success_count=len(findings),
                tool_error_count=0,
                phase="initial",
                agent_persona="Image integrity analyst persona.",
                visual_profile_context=_visual_context("web_page", scenario),
            )
        assert result["verdict"] == "AUTHENTIC"
        assert "browser screenshot" in result["agent_brief"].lower()
        assert len(result.get("key_findings") or []) >= 3
        print("groq_synthesis_mock: PASS")


async def probe_scenarios() -> None:
    service = SynthesisService(_settings())
    with tempfile.TemporaryDirectory() as td:
        for name, scenario in SCENARIOS.items():
            routing = build_image_forensic_routing(
                {"image_category": scenario["category"]},
                description=scenario["description"],
                file_path=f"{name}.png",
            )
            assert routing["recommended_initial_tools"]
            path = Path(td) / f"{name}.png"
            _make_probe_image(path, name)
            rows = [
                {
                    "tool": tool,
                    "confidence": conf,
                    "evidence_verdict": verdict,
                    "status": "CONFIRMED",
                    "data": data,
                }
                for tool, verdict, conf, data in scenario["tools"]
            ]
            summaries = [
                service._tool_grounded_summary(row, screenshot_like=scenario["category"] == "screenshot")
                for row in rows
            ]
            assert all(s and "Tool results:" not in s for s in summaries)
            print(f"scenario_{name}: PASS -> {routing['image_category']} -> {', '.join(routing['recommended_initial_tools'][:4])}")


async def probe_confidence_verdict_paths() -> None:
    class SuspiciousFakeLLM:
        provider = "groq"

        def __init__(self, *_args, **_kwargs):
            pass

        async def generate_synthesis(self, **_kwargs):
            return json.dumps(
                {
                    "agent_confidence": 0.93,
                    "agent_error_rate": 0.0,
                    "verdict": "SUSPICIOUS",
                    "agent_brief": "The visual profile identified this evidence as a clean screenshot. 2 forensic tools ran: OCR extracted 38 words; layout found 0 anomaly flags. Based on the visual-profile verdict and tool agreement, this evidence is assessed as SUSPICIOUS with 93% confidence.",
                    "narrative_summary": "Suspicious wording from mocked LLM should be corrected because no positive tools exist.",
                    "key_findings": ["OCR extracted 38 words.", "Layout found 0 anomaly flags."],
                    "sections": [],
                    "signal_weight": {},
                }
            )

    scenario = SCENARIOS["web_page"]
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "web_page.png"
        _make_probe_image(path, "Forensic Council Web Page")
        service = SynthesisService(_settings())
        findings = [_finding(*tool_data) for tool_data in scenario["tools"][:2]]
        with patch("core.synthesis.LLMClient", SuspiciousFakeLLM):
            llm_result = await service.synthesize_findings(
                agent_id="Agent1",
                agent_name="Agent1_ImageIntegrity",
                findings=findings,
                evidence_artifact=_artifact(path),
                tool_success_count=len(findings),
                tool_error_count=0,
                phase="initial",
                visual_profile_context=_visual_context("web_page", scenario),
            )
        assert llm_result["verdict"] == "AUTHENTIC"
        assert llm_result["agent_confidence"] == 0.93

        class FailingLLM:
            provider = "groq"

            def __init__(self, *_args, **_kwargs):
                pass

            async def generate_synthesis(self, **_kwargs):
                raise RuntimeError("mock provider unavailable")

        with patch("core.synthesis.LLMClient", FailingLLM):
            fallback_result = await service.synthesize_findings(
                agent_id="Agent1",
                agent_name="Agent1_ImageIntegrity",
                findings=findings,
                evidence_artifact=_artifact(path),
                tool_success_count=len(findings),
                tool_error_count=0,
                phase="initial",
                visual_profile_context=_visual_context("web_page", scenario),
            )
        assert fallback_result["verdict"] == "AUTHENTIC"
        assert 0.70 <= fallback_result["agent_confidence"] <= 1.0
        print("confidence_verdict_paths: PASS")


async def probe_initial_report_trace() -> None:
    class TraceLLM:
        provider = "groq"

        def __init__(self, *_args, **_kwargs):
            pass

        async def generate_synthesis(self, **_kwargs):
            context = _kwargs.get("context") or ""
            is_screenshot = "screenshot" in context.lower() or "browser" in context.lower()
            desc = (
                "a browser screenshot of a case management page"
                if is_screenshot
                else "a live photograph of a person indoors"
            )
            tool_line = (
                "OCR, layout, and font checks agree with the screen-capture visual profile"
                if is_screenshot
                else "hash, ELA, and frequency checks agree with the live-photo visual profile"
            )
            return json.dumps(
                {
                    "agent_confidence": 0.87,
                    "agent_error_rate": 0.0,
                    "verdict": "AUTHENTIC",
                    "agent_brief": f"The visual profile identified this evidence as {desc}. {tool_line}. Based on visual-profile and tool agreement, this evidence is assessed as AUTHENTIC with 87% confidence.",
                    "narrative_summary": f"Initial analysis treated the file as {desc}; relevant tools ran cleanly and no failed tool was converted into a suspicion signal.",
                    "key_findings": [
                        f"Visual profile identified {desc}.",
                        tool_line + ".",
                        "No called tool failed or returned incomplete output.",
                    ],
                    "sections": [],
                    "signal_weight": {"strongest_positive": "none", "strongest_negative": "visual_profile"},
                }
            )

    service = SynthesisService(_settings())
    client = GeminiVisionClient(_settings())
    with tempfile.TemporaryDirectory() as td:
        for name in ("web_page", "person"):
            scenario = SCENARIOS[name]
            raw = json.dumps(
                {
                    "content_type": scenario["category"],
                    "scene_description": scenario["description"],
                    "extracted_text": ["Forensic Council"] if name == "web_page" else [],
                    "detected_objects": ["browser", "navigation"] if name == "web_page" else ["person"],
                    "interface_identification": "web browser UI" if name == "web_page" else "",
                    "contextual_narrative": scenario["description"],
                    "manipulation_signals": [],
                    "metadata_visual_consistency": "No contradiction detected",
                    "authenticity_verdict": "AUTHENTIC",
                    "confidence": 0.9,
                    "forensic_routing": {"image_category": scenario["category"]},
                    "forensic_specifics": f"Trace pass for {name}.",
                }
            )
            visual = client._parse_response(raw, "deep_forensic_analysis", 12.0)
            visual_dict = visual.to_finding_dict("Agent1")
            path = Path(td) / f"{name}.png"
            _make_probe_image(path, name)
            findings = [_finding(*tool_data) for tool_data in scenario["tools"]]
            visual_context = dict(visual_dict["metadata"])
            visual_context["content_description"] = visual.content_description

            with patch("core.synthesis.LLMClient", TraceLLM):
                synthesis = await service.synthesize_findings(
                    agent_id="Agent1",
                    agent_name="Agent1_ImageIntegrity",
                    findings=findings,
                    evidence_artifact=_artifact(path),
                    tool_success_count=len(findings),
                    tool_error_count=0,
                    phase="initial",
                    agent_persona="Image integrity analyst aware of the full evidence context.",
                    visual_profile_context=visual_context,
                )

            finding_dicts = [visual_dict] + [f.model_dump(mode="json") for f in findings]
            report = ForensicReport(
                session_id=uuid4(),
                case_id=f"probe_{name}",
                executive_summary=synthesis["narrative_summary"],
                per_agent_findings={"Agent1": finding_dicts},
                per_agent_metrics={
                    "Agent1": {
                        "agent_id": "Agent1",
                        "agent_name": "Image Integrity",
                        "total_tools_called": len(finding_dicts),
                        "tools_succeeded": len(finding_dicts),
                        "tools_failed": 0,
                        "error_rate": 0.0,
                        "confidence_score": synthesis["agent_confidence"],
                        "finding_count": len(finding_dicts),
                    }
                },
                overall_confidence=synthesis["agent_confidence"],
                overall_error_rate=0.0,
                overall_verdict=synthesis["verdict"],
                uncertainty_statement="No significant uncertainties remain.",
                verdict_sentence=synthesis["agent_brief"],
                key_findings=synthesis["key_findings"],
                reliability_note="Initial analysis used the visual profile and relevant tool agreement.",
                manipulation_probability=0.0,
                applicable_agent_count=1,
                per_agent_summary={
                    "Agent1": {
                        "verdict": synthesis["verdict"],
                        "confidence_pct": round(synthesis["agent_confidence"] * 100),
                        "tools_ok": len(finding_dicts),
                        "tools_total": len(finding_dicts),
                    }
                },
            )
            pipeline = SimpleNamespace(_degradation_flags=[], config=SimpleNamespace(local_only_analysis=False))
            _detect_visual_profile_provenance(pipeline, report)
            assert report.overall_verdict == "AUTHENTIC"
            assert "Visual profile provider" in report.analysis_coverage_note
            assert not pipeline._degradation_flags
            assert len(report.key_findings) == 3
            assert "Tool results:" not in " ".join(report.key_findings)
            print(f"initial_report_trace_{name}: PASS")


async def probe_inter_tool_and_persona_fallback() -> None:
    fake_agent = SimpleNamespace(
        _tool_context={
            "visual_evidence_profile": {
                "reasoning_summary": "Browser screenshot of a financial dashboard.",
                "metadata": {
                    "forensic_routing": {"image_category": "screenshot"},
                    "authenticity_verdict": "AUTHENTIC",
                    "extracted_text": ["Dashboard"],
                },
            },
            "extract_text_from_image": {
                "text": "Dashboard Balance Transfer",
                "word_count": 3,
            },
        },
        inter_agent_bus=None,
        session_id=uuid4(),
    )
    grounding = ImageHandlers(fake_agent)._visual_grounding_context()
    assert grounding["image_category"] == "screenshot"
    assert "Dashboard Balance Transfer" in grounding["extracted_text"]
    assert grounding["ocr_word_count"] == 3

    fallback_agent = SimpleNamespace(
        agent_name="Agent1_ImageIntegrity",
        persona="Image integrity analyst. Use visual context before generic model scores.",
        _tool_context=fake_agent._tool_context,
        evidence_artifact=None,
    )
    finding = _finding(
        "screenshot_layout_forensics",
        "NEGATIVE",
        0.78,
        {
            "layout_anomaly_count": 0,
            "visual_grounding": grounding,
            "raw_tool_summary": "layout check clean",
        },
    )
    result = AgentInvestigationMixin._build_deterministic_synthesis(
        fallback_agent,
        [finding],
        "initial",
    )
    assert result["verdict"] in {"AUTHENTIC", "INCONCLUSIVE"}
    assert result["agent_role"].startswith("Image integrity analyst")
    assert "visual profile" in result["fallback_reason"].lower()
    assert "Browser screenshot" in result["narrative_summary"]
    print("inter_tool_and_persona_fallback: PASS")


async def probe_no_api_deep_and_arbiter_fallback() -> None:
    class FailingLLM:
        provider = "groq"

        def __init__(self, *_args, **_kwargs):
            pass

        async def generate_synthesis(self, **_kwargs):
            raise RuntimeError("mock no-api mode")

    scenario = SCENARIOS["person"]
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "person.png"
        _make_probe_image(path, "Person Evidence")
        service = SynthesisService(_settings())
        initial_findings = [_finding(*tool_data) for tool_data in scenario["tools"]]
        deep_findings = [
            _finding(
                "f3_net_frequency",
                "NEGATIVE",
                0.81,
                {"anomaly_score": 0.03, "high_frequency_score": 0.08},
            ),
            _finding(
                "neural_splicing",
                "NEGATIVE",
                0.79,
                {"splicing_detected": False, "confidence": 0.79},
            ),
        ]
        for f in initial_findings:
            f.metadata["analysis_phase"] = "initial"
        for f in deep_findings:
            f.metadata["analysis_phase"] = "deep"
        visual_context = _visual_context("person", scenario)
        with patch("core.synthesis.LLMClient", FailingLLM):
            result = await service.synthesize_findings(
                agent_id="Agent1",
                agent_name="Agent1_ImageIntegrity",
                findings=initial_findings + deep_findings,
                evidence_artifact=_artifact(path),
                tool_success_count=len(initial_findings) + len(deep_findings),
                tool_error_count=0,
                phase="deep",
                agent_persona="Image integrity analyst persona.",
                visual_profile_context=visual_context,
                phase1_context={
                    "phase1_verdict": "AUTHENTIC",
                    "phase1_confidence": 0.82,
                    "phase1_narrative": "Initial tools found no manipulation signal.",
                },
            )
        assert result["verdict"] == "AUTHENTIC"
        assert result["phase_delta"] == "CONFIRMED"
        assert "Visual profile:" in result["key_findings"][0]
        assert "Tool results:" not in " ".join(result["key_findings"])
        assert "visual profile identified" in result["agent_brief"].lower()

        visual_finding = {
            "agent_id": "Agent1",
            "finding_type": "visual_evidence_profile",
            "reasoning_summary": scenario["description"],
            "metadata": {
                "tool_name": "visual_evidence_profile",
                "content_description": scenario["description"],
                "provider_used": "local_visual_ensemble",
            },
            "evidence_verdict": "NEGATIVE",
            "confidence_raw": 0.84,
            "status": "CONFIRMED",
        }
        arbiter = CouncilArbiter(session_id=uuid4(), config=_settings())
        narrative_json = arbiter._programmatic_agent_narrative(
            "Agent1",
            [visual_finding] + [f.model_dump(mode="json") for f in initial_findings + deep_findings],
            {
                "tools_succeeded": 1 + len(initial_findings) + len(deep_findings),
                "total_tools_called": 1 + len(initial_findings) + len(deep_findings),
                "error_rate": 0.0,
            },
            visual_profile_findings=[visual_finding],
        )
        parsed = json.loads(narrative_json)
        assert scenario["description"] in parsed["visual_description"]
        assert "Deep analysis added" in parsed["opinion"]

        _vs, kf, _rn, _pa, _ex, _unc = arbiter._template_all(
            "AUTHENTIC",
            0.87,
            0.0,
            0.0,
            1,
            [visual_finding] + [f.model_dump(mode="json") for f in initial_findings + deep_findings],
            0,
            0,
            "All tools completed.",
            {
                "Agent1": {
                    "findings": [visual_finding] + [f.model_dump(mode="json") for f in initial_findings + deep_findings],
                    "synthesis": {
                        "phase_delta": "CONFIRMED",
                        "delta_reason": "Deep analysis confirmed Phase 1.",
                    },
                }
            },
            per_agent_metrics={
                "Agent1": {
                    "tools_succeeded": 1 + len(initial_findings) + len(deep_findings),
                    "total_tools_called": 1 + len(initial_findings) + len(deep_findings),
                    "error_rate": 0.0,
                }
            },
        )
        assert any("deep-pass delta: CONFIRMED" in item for item in kf)
        print("no_api_deep_and_arbiter_fallback: PASS")


async def probe_screenshot_camera_tool_guards() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "browser_screenshot.png"
        _make_probe_image(path, "Browser Screenshot")
        artifact = _artifact(path)
        artifact.metadata["mime_type"] = "image/png"
        records: dict[str, dict] = {}

        async def _record(tool_name: str, result: dict) -> None:
            records[tool_name] = result

        fake_agent = SimpleNamespace(
            evidence_artifact=artifact,
            _tool_context={
                "visual_evidence_profile": {
                    "reasoning_summary": "Browser screenshot of a forensic dashboard.",
                    "metadata": {
                        "forensic_routing": {"image_category": "screenshot"},
                        "file_type_assessment": "screenshot",
                        "authenticity_verdict": "AUTHENTIC",
                    },
                }
            },
            _record_tool_result=_record,
            working_memory=None,
            session_id=uuid4(),
        )
        handlers = ImageHandlers(fake_agent)
        guarded = {
            "noiseprint_cluster": await handlers.noiseprint_cluster_handler({"artifact": artifact}),
            "noise_fingerprint": await handlers.noise_fingerprint_handler({"artifact": artifact}),
            "neural_splicing": await handlers.neural_splicing_handler({"artifact": artifact}),
            "splicing_detect": await handlers.splicing_detect_handler({"artifact": artifact}),
            "neural_copy_move": await handlers.neural_copy_move_handler({"artifact": artifact}),
            "copy_move_detect": await handlers.copy_move_detect_handler({"artifact": artifact}),
            "adversarial_robustness_check": await handlers.adversarial_robustness_check_handler({"artifact": artifact}),
        }
        for tool, result in guarded.items():
            assert result["evidence_verdict"] == "NOT_APPLICABLE", tool
            assert result["screenshot_scope_guard"] is True, tool
        print("screenshot_camera_tool_guards: PASS")


async def main() -> None:
    await probe_gemini_visual_parse()
    await probe_groq_synthesis()
    await probe_scenarios()
    await probe_confidence_verdict_paths()
    await probe_initial_report_trace()
    await probe_inter_tool_and_persona_fallback()
    await probe_no_api_deep_and_arbiter_fallback()
    await probe_screenshot_camera_tool_guards()


if __name__ == "__main__":
    asyncio.run(main())

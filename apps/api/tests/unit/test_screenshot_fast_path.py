import os
from unittest.mock import AsyncMock
from uuid import uuid4

import numpy as np
from PIL import Image

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-" + "x" * 32)
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_PASSWORD", "test")
os.environ.setdefault("DEMO_PASSWORD", "test")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_MODEL", "test-model")

from agents.agent1_image import Agent1Image
from agents.agent3_object import Agent3Object
from agents.agent5_metadata import Agent5Metadata
from core.config import Settings
from core.evidence import ArtifactType, EvidenceArtifact
from core.media_kind import is_screen_capture_like
from core.react_loop import AgentFinding
from orchestration.pipeline_phases import (
    _agent1_screenshot_preview,
    _humanize_initial_finding,
    _screenshot_agent_override,
)


def _settings() -> Settings:
    return Settings(
        app_env="testing",
        signing_key="test-signing-key-" + "x" * 32,
        postgres_user="test",
        postgres_password="test",
        postgres_db="test",
        redis_password="test",
        DEMO_PASSWORD="test",
        llm_provider="none",
        llm_api_key=None,
        llm_model="test-model",
        bootstrap_admin_password="Admin_123!",
        bootstrap_investigator_password="Inv_123!",
    )


def _artifact(path: str, mime_type: str = "image/png") -> EvidenceArtifact:
    return EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=path,
        content_hash="abc123",
        action="upload",
        agent_id="system",
        session_id=uuid4(),
        metadata={"mime_type": mime_type},
    )


def _artifact_with_metadata(
    path: str, metadata: dict[str, str], mime_type: str = "image/png"
) -> EvidenceArtifact:
    return EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=path,
        content_hash="abc123",
        action="upload",
        agent_id="system",
        session_id=uuid4(),
        metadata={"mime_type": mime_type, **metadata},
    )


def _agent(cls, agent_id: str, artifact: EvidenceArtifact):
    return cls(
        agent_id=agent_id,
        session_id=artifact.session_id,
        evidence_artifact=artifact,
        config=_settings(),
        working_memory=AsyncMock(),
        episodic_memory=AsyncMock(),
        custody_logger=AsyncMock(),
        evidence_store=AsyncMock(),
    )


def _save_screen_png(path) -> None:
    arr = np.full((1080, 1920, 3), 245, dtype=np.uint8)
    arr[120:180, 150:900] = 20
    Image.fromarray(arr, mode="RGB").save(path, format="PNG")


def test_screen_capture_like_png_is_detected(tmp_path):
    path = tmp_path / "screen.png"
    _save_screen_png(path)
    assert is_screen_capture_like(_artifact(str(path))) is True


def test_agent1_uses_short_screen_capture_initial_plan(tmp_path):
    path = tmp_path / "screen.png"
    _save_screen_png(path)
    agent = _agent(Agent1Image, "Agent1", _artifact(str(path)))

    tasks = agent.task_decomposition

    assert "Run extract_text_from_image for visible text extraction" in tasks
    assert all("noiseprint" not in t.lower() for t in tasks)
    assert all("neural_fingerprint" not in t.lower() for t in tasks)


def test_agent3_skips_physical_scene_tools_for_screen_capture(tmp_path):
    path = tmp_path / "screen.png"
    _save_screen_png(path)
    agent = _agent(Agent3Object, "Agent3", _artifact(str(path)))

    assert agent.task_decomposition == [
        "Run screenshot_scene_applicability for screen-capture object/scene scope",
    ]
    # Now has deep tasks for screen captures instead of empty
    assert len(agent.deep_task_decomposition) == 2


def test_agent5_omits_camera_provenance_tools_for_screen_capture(tmp_path):
    path = tmp_path / "screen.png"
    _save_screen_png(path)
    agent = _agent(Agent5Metadata, "Agent5", _artifact(str(path)))

    tasks = " ".join(agent.task_decomposition).lower()

    assert "gps_timezone" not in tasks
    assert "astro_grounding" not in tasks
    assert "exif_isolation_forest" not in tasks
    assert agent.deep_task_decomposition == []


def test_agent3_screenshot_scope_overrides_inconclusive_card(tmp_path):
    path = tmp_path / "screen.png"
    _save_screen_png(path)
    agent = _agent(Agent3Object, "Agent3", _artifact(str(path)))
    finding = AgentFinding(
        agent_id="Agent3",
        finding_type="screenshot_scene_applicability",
        status="NOT_APPLICABLE",
        confidence_raw=None,
        evidence_verdict="NOT_APPLICABLE",
        reasoning_summary="Screenshot scene applicability: skipped.",
        metadata={"tool_name": "screenshot_scene_applicability"},
    )

    override = _screenshot_agent_override("Agent3", [finding], agent)

    assert override is not None
    assert override["verdict"] == "NOT_APPLICABLE"
    assert "scope skip" in override["narrative_summary"]
    assert "not a failed or suspicious finding" in override["narrative_summary"]


def test_agent1_screenshot_override_does_not_authenticate_screen_content(tmp_path):
    path = tmp_path / "screen.png"
    _save_screen_png(path)
    agent = _agent(Agent1Image, "Agent1", _artifact(str(path)))
    finding = AgentFinding(
        agent_id="Agent1",
        finding_type="analyze_image_content",
        status="CONFIRMED",
        confidence_raw=0.85,
        evidence_verdict="NEGATIVE",
        reasoning_summary=(
            "Analyze Image Content: Visual classifier recognized the upload as "
            "forensic/evidence imagery."
        ),
        metadata={"tool_name": "analyze_image_content", "file_name": "Screenshot.png"},
    )

    override = _screenshot_agent_override("Agent1", [finding], agent)

    assert override is not None
    assert override["verdict"] == "CLEAN"
    assert "does not authenticate the on-screen claim" in override["narrative_summary"]


def test_agent1_screenshot_override_uses_original_filename_metadata(tmp_path):
    path = tmp_path / "5816ab5e-dc07-4d6c-b1b1-425e689ba8ca.png"
    _save_screen_png(path)
    artifact = _artifact_with_metadata(
        str(path),
        {"original_filename": "Screenshot 2026-05-04 131111.png"},
    )
    agent = _agent(Agent1Image, "Agent1", artifact)
    finding = AgentFinding(
        agent_id="Agent1",
        finding_type="frequency_domain_analysis",
        status="CONFIRMED",
        confidence_raw=0.7,
        evidence_verdict="NEGATIVE",
        reasoning_summary="No signs of digital editing or manipulation were detected.",
        metadata={"tool_name": "frequency_domain_analysis"},
    )

    override = _screenshot_agent_override("Agent1", [finding], agent)

    assert override is not None
    assert override["synthesis_source"] == "screenshot_image_override"


def test_agent1_screenshot_hides_semantic_classifier_as_authenticity_signal():
    summary = _humanize_initial_finding(
        agent_id="Agent1",
        tool_name="analyze_image_content",
        summary="Analyze Image Content: Visual classifier recognized the upload as forensic/evidence imagery.",
        evidence_verdict="NEGATIVE",
        finding_status="CONFIRMED",
        metadata={"file_name": "Screenshot.png"},
    )

    assert summary is None


def test_agent1_screenshot_preview_keeps_only_valid_deduped_artifact_findings():
    findings = [
        AgentFinding(
            agent_id="Agent1",
            finding_type="analyze_image_content",
            status="CONFIRMED",
            confidence_raw=0.09,
            evidence_verdict="NEGATIVE",
            reasoning_summary="The image appears to be a real photograph, likely taken as forensic evidence.",
            metadata={"tool_name": "analyze_image_content", "file_name": "Screenshot.png"},
        ),
        AgentFinding(
            agent_id="Agent1",
            finding_type="file_hash_verify",
            status="CONFIRMED",
            confidence_raw=1.0,
            evidence_verdict="NEGATIVE",
            reasoning_summary="File Hash Verify: SHA-256=8ef98018c55b1234567890 matched chain record.",
            metadata={"tool_name": "file_hash_verify"},
        ),
        AgentFinding(
            agent_id="Agent1",
            finding_type="frequency_domain_analysis",
            status="CONFIRMED",
            confidence_raw=0.7,
            evidence_verdict="NEGATIVE",
            reasoning_summary="Frequency analysis found no unusual high-frequency artifact pattern.",
            metadata={"tool_name": "frequency_domain_analysis"},
        ),
        AgentFinding(
            agent_id="Agent1",
            finding_type="extract_text_from_image",
            status="CONFIRMED",
            confidence_raw=0.95,
            evidence_verdict="NEGATIVE",
            reasoning_summary="Text extracted from the image is consistent with a genuine forensic evidence photograph.",
            metadata={"tool_name": "extract_text_from_image", "ocr_text_preview": "SYSTEM OVERVIEW"},
        ),
        AgentFinding(
            agent_id="Agent1",
            finding_type="file_hash_verify",
            status="CONFIRMED",
            confidence_raw=0.68,
            evidence_verdict="NEGATIVE",
            reasoning_summary="The image's digital fingerprint matches the original.",
            metadata={"tool_name": "file_hash_verify"},
        ),
    ]

    preview = _agent1_screenshot_preview(
        findings,
        "Initial screenshot checks found no supported file-integrity or image-artifact tampering signal.",
    )
    tools = [item["tool"] for item in preview]
    summaries = " ".join(str(item["summary"]) for item in preview).lower()

    assert tools == [
        "screenshot_initial_summary",
        "file_hash_verify",
        "frequency_domain_analysis",
        "extract_text_from_image",
    ]
    assert "real photograph" not in summaries
    assert "genuine forensic evidence" not in summaries
    assert "digital fingerprint matches the original" not in summaries
    assert "chain-of-custody record" in summaries
    assert "ocr extracted visible text" in summaries


def test_agent5_screenshot_metadata_overrides_noisy_inconclusive_card(tmp_path):
    path = tmp_path / "screen.png"
    _save_screen_png(path)
    agent = _agent(Agent5Metadata, "Agent5", _artifact(str(path)))
    finding = AgentFinding(
        agent_id="Agent5",
        finding_type="exif_extract",
        status="INCONCLUSIVE",
        confidence_raw=0.4,
        evidence_verdict="INCONCLUSIVE",
        reasoning_summary="No EXIF metadata block was present.",
        metadata={"tool_name": "exif_extract", "mime_type": "image/png"},
    )

    override = _screenshot_agent_override("Agent5", [finding], agent)

    assert override is not None
    assert override["verdict"] == "CLEAN"
    assert "camera/GPS EXIF absence is expected" in override["narrative_summary"]

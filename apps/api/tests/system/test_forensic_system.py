"""
Comprehensive Forensic Council System Test
==========================================
Tests the full pipeline: agents, tools, Groq synthesis, arbiter, Gemini, deep analysis.
Flags issues and reports results.

NOTE: These are standalone async scripts, NOT pytest-compatible test functions.
Run with: python -m tests.test_forensic_system (requires full Docker stack)
"""

import asyncio
import json
import os
import sys
import time
import traceback
from pathlib import Path
from uuid import uuid4

import pytest

pytestmark = [
    pytest.mark.skip(reason="Standalone system test — run with Docker stack directly"),
    pytest.mark.requires_ml,
]

# Identify API root (works for both local and Docker)
API_DIR = Path(__file__).resolve().parents[2]
if not (API_DIR / "api").exists():
    # Fallback for complex layouts
    if os.path.exists("/app/api"):
        API_DIR = Path("/app")

sys.path.insert(0, str(API_DIR))
os.chdir(str(API_DIR))

from agents.agent1_image import Agent1Image
from agents.agent2_audio import Agent2Audio
from agents.agent3_object import Agent3Object
from agents.agent4_video import Agent4Video
from agents.agent5_metadata import Agent5Metadata
from agents.arbiter import CouncilArbiter, ForensicReport
from core.config import get_settings
from core.custody_logger import CustodyLogger
from core.episodic_memory import EpisodicMemory
from core.evidence import EvidenceArtifact
from core.gemini_client import GeminiVisionClient
from core.llm_client import LLMClient
from core.persistence.evidence_store import EvidenceStore
from core.working_memory import WorkingMemory


# ── Color output ──────────────────────────────────────────────────────────
class C:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    END = "\033[0m"


def ok(msg):
    print(f"  {C.GREEN}[PASS]{C.END} {msg}")


def fail(msg):
    print(f"  {C.RED}[FAIL]{C.END} {msg}")


def warn(msg):
    print(f"  {C.YELLOW}[WARN]{C.END} {msg}")


def header(msg):
    print(f"\n{C.BOLD}{C.CYAN}{'=' * 60}\n{msg}\n{'=' * 60}{C.END}")


def section(msg):
    print(f"\n{C.BOLD}--- {msg} ---{C.END}")


issues = []


def flag(severity, location, msg):
    """Flag an issue for later fix."""
    issues.append({"severity": severity, "location": location, "message": msg})
    if severity == "CRITICAL":
        fail(f"CRITICAL: [{location}] {msg}")
    elif severity == "WARNING":
        warn(f"WARNING: [{location}] {msg}")
    else:
        ok(f"INFO: [{location}] {msg}")


# ── Test fixtures ─────────────────────────────────────────────────────────
TEST_IMAGE_PATH = str(Path(__file__).parent / "fixtures" / "test_image.webp")


async def create_evidence_artifact(config):
    """Create evidence artifact from test image."""
    file_path = Path(TEST_IMAGE_PATH)
    if not file_path.exists():
        # Try alternate locations
        for alt in ["fixtures/test_image.webp", "tests/fixtures/test_image.webp"]:
            if Path(alt).exists():
                file_path = Path(alt)
                break

    import hashlib

    with open(file_path, "rb") as f:
        content = f.read()

    sha256 = hashlib.sha256(content).hexdigest()

    from core.evidence import ArtifactType

    artifact = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=str(file_path),
        content_hash=sha256,
        action="UPLOAD",
        agent_id="User",
        session_id=uuid4(),
        metadata={"mime_type": "image/webp", "original_filename": file_path.name},
    )
    return artifact


async def create_test_infrastructure():
    config = get_settings()
    session_id = uuid4()
    working_memory = WorkingMemory(redis_client=None, custody_logger=None)
    episodic_memory = EpisodicMemory(qdrant_client=None, custody_logger=None)
    custody_logger = CustodyLogger(postgres_client=None)
    from core.persistence.storage import LocalStorageBackend

    evidence_store = EvidenceStore(
        postgres_client=None,
        storage_backend=LocalStorageBackend(storage_path="./storage/evidence"),
        custody_logger=custody_logger,
    )
    return config, session_id, working_memory, episodic_memory, custody_logger, evidence_store


# ══════════════════════════════════════════════════════════════════════════
#  TEST 1: Image Agent Initial Analysis
# ══════════════════════════════════════════════════════════════════════════
async def test_agent1_initial():
    header("TEST 1: Agent 1 (Image Integrity) — Initial Analysis")

    config, session_id, wm, em, cl, es = await create_test_infrastructure()
    artifact = await create_evidence_artifact(config)

    agent = Agent1Image(
        agent_id="Agent1",
        session_id=session_id,
        evidence_artifact=artifact,
        config=config,
        working_memory=wm,
        episodic_memory=em,
        custody_logger=cl,
        evidence_store=es,
    )

    section("1.1 Agent Creation & Properties")
    try:
        assert agent.agent_name == "Agent1_ImageIntegrity"
        assert "image" in agent.agent_name.lower()
        ok(f"Agent name: {agent.agent_name}")

        tasks = agent.task_decomposition
        ok(f"Task decomposition: {len(tasks)} tasks")
        for i, t in enumerate(tasks):
            ok(f"  Task {i + 1}: {t}")
    except Exception as e:
        flag("CRITICAL", "Agent1.init", str(e))
        return

    section("1.2 Tool Registry")
    try:
        registry = await agent.build_tool_registry()
        tools = registry.list_tools()
        ok(f"Tool registry: {len(tools)} tools registered")
        tool_names = [t.name for t in tools]
        ok(f"  Tools: {', '.join(tool_names)}")

        # Check required tools (Modernized Neural-First Registry)
        required = [
            "neural_ela",
            "frequency_domain_analysis",
            "noiseprint_cluster",
            "analyze_image_content",
            "gemini_deep_forensic",
        ]
        for req in required:
            if req in tool_names:
                ok(f"  Required tool '{req}' registered")
            else:
                flag("CRITICAL", "Agent1.registry", f"Required tool '{req}' NOT registered")
    except Exception as e:
        flag("CRITICAL", "Agent1.registry", str(e))
        traceback.print_exc()
        return

    section("1.3 Run Initial Investigation")
    try:
        t0 = time.time()
        findings = await agent.run_investigation()
        elapsed = time.time() - t0
        ok(f"Initial investigation completed in {elapsed:.1f}s")
        ok(f"Findings count: {len(findings)}")

        for i, f in enumerate(findings):
            fname = (
                f.metadata.get("tool_name", f.finding_type)
                if hasattr(f, "metadata")
                else f.finding_type
            )
            conf = getattr(f, "confidence_raw", 0) or 0
            status = getattr(f, "status", "UNKNOWN")
            ok(f"  Finding {i + 1}: {fname} | confidence={conf:.3f} | status={status}")

            # Validate finding structure
            if not hasattr(f, "finding_type"):
                flag("WARNING", f"Agent1.finding[{i}]", "Missing finding_type")
            if not hasattr(f, "confidence_raw"):
                flag("WARNING", f"Agent1.finding[{i}]", "Missing confidence_raw")
            if not hasattr(f, "metadata") or not isinstance(f.metadata, dict):
                flag("WARNING", f"Agent1.finding[{i}]", "Missing or invalid metadata")

            # Check for tool errors
            if f.metadata.get("error") and f.metadata.get("court_defensible") is False:
                flag(
                    "WARNING", f"Agent1.{fname}", f"Tool error: {f.metadata.get('error', '')[:100]}"
                )

        if not findings:
            flag("CRITICAL", "Agent1.initial", "No findings produced!")
    except Exception as e:
        flag("CRITICAL", "Agent1.initial", str(e))
        traceback.print_exc()
        return

    section("1.4 Check ELA Handling for WEBP")
    try:
        ela_findings = [
            f for f in findings if "ela" in str(f.metadata.get("tool_name", "")).lower()
        ]
        if ela_findings:
            for ef in ela_findings:
                is_na = ef.metadata.get("ela_not_applicable", False)
                if is_na:
                    ok(
                        f"ELA correctly marked not applicable for WEBP: {ef.metadata.get('ela_limitation_note', '')[:80]}"
                    )
                else:
                    ok(f"ELA ran: mean={ef.metadata.get('ela_mean', 'N/A')}")
        else:
            warn("No ELA findings (expected for WEBP)")
    except Exception as e:
        flag("WARNING", "Agent1.ela_webp", str(e))

    return agent, findings


# ══════════════════════════════════════════════════════════════════════════
#  TEST 2: Agent 1 Deep Analysis
# ══════════════════════════════════════════════════════════════════════════
async def test_agent1_deep(agent=None):
    header("TEST 2: Agent 1 — Deep Analysis (Gemini + Advanced Tools)")

    section("2.1 Deep Task Decomposition")
    try:
        deep_tasks = agent.deep_task_decomposition
        ok(f"Deep tasks: {len(deep_tasks)}")
        for i, t in enumerate(deep_tasks):
            ok(f"  Deep Task {i + 1}: {t[:80]}...")
    except Exception as e:
        flag("CRITICAL", "Agent1.deep_tasks", str(e))
        return

    section("2.2 Run Deep Investigation")
    try:
        t0 = time.time()
        deep_findings = await agent.run_deep_investigation()
        elapsed = time.time() - t0
        ok(f"Deep investigation completed in {elapsed:.1f}s")
        ok(f"Deep findings count: {len(deep_findings)}")

        for i, f in enumerate(deep_findings):
            fname = (
                f.metadata.get("tool_name", f.finding_type)
                if hasattr(f, "metadata")
                else f.finding_type
            )
            conf = getattr(f, "confidence_raw", 0) or 0
            phase = f.metadata.get("analysis_phase", "unknown")
            ok(f"  Deep Finding {i + 1}: {fname} | confidence={conf:.3f} | phase={phase}")

            if phase != "deep":
                flag(
                    "WARNING", f"Agent1.deep[{i}]", f"Expected analysis_phase='deep', got '{phase}'"
                )

        # Check Gemini finding
        gemini_findings = [
            f
            for f in deep_findings
            if f.metadata.get("tool_name") == "gemini_deep_forensic"
            or f.metadata.get("analysis_source") == "gemini_vision"
        ]
        if gemini_findings:
            ok(f"Gemini vision findings: {len(gemini_findings)}")
            gf = gemini_findings[0]
            model = gf.metadata.get("model_used", "unknown")
            content_type = gf.metadata.get(
                "gemini_content_type", gf.metadata.get("file_type_assessment", "")
            )
            ok(f"  Model used: {model}")
            ok(f"  Content type: {content_type}")
            if gf.metadata.get("error"):
                warn(f"  Gemini error: {gf.metadata.get('error', '')[:100]}")
        else:
            warn("No Gemini vision findings in deep pass")
    except Exception as e:
        flag("CRITICAL", "Agent1.deep", str(e))
        traceback.print_exc()

    # Check combined findings (initial + deep)
    section("2.3 Combined Findings (Initial + Deep)")
    try:
        all_findings = agent._findings
        initial_count = len(
            [f for f in all_findings if f.metadata.get("analysis_phase", "initial") == "initial"]
        )
        deep_count = len([f for f in all_findings if f.metadata.get("analysis_phase") == "deep"])
        ok(f"Combined: {len(all_findings)} total ({initial_count} initial + {deep_count} deep)")
    except Exception as e:
        flag("WARNING", "Agent1.combined", str(e))


# ══════════════════════════════════════════════════════════════════════════
#  TEST 3: Other Agents (2-5)
# ══════════════════════════════════════════════════════════════════════════
async def test_other_agents():
    header("TEST 3: Other Agents (2-5) — File Type Filtering & Basic Run")

    config, session_id, wm, em, cl, es = await create_test_infrastructure()
    artifact = await create_evidence_artifact(config)

    agent_classes = {
        "Agent2": (Agent2Audio, "Audio"),
        "Agent3": (Agent3Object, "Object"),
        "Agent4": (Agent4Video, "Video"),
        "Agent5": (Agent5Metadata, "Metadata"),
    }

    for agent_id, (agent_class, name) in agent_classes.items():
        section(f"3.{list(agent_classes.keys()).index(agent_id) + 1} Agent {name}")
        try:
            agent = agent_class(
                agent_id=agent_id,
                session_id=session_id,
                evidence_artifact=artifact,
                config=config,
                working_memory=wm,
                episodic_memory=em,
                custody_logger=cl,
                evidence_store=es,
            )

            # Check file type support
            supports = agent.supports_uploaded_file
            file_types = agent.supported_file_types
            ok(f"  Supports WEBP image: {supports} (types: {file_types})")

            # Run investigation
            t0 = time.time()
            findings = await agent.run_investigation()
            elapsed = time.time() - t0
            ok(f"  Investigation completed in {elapsed:.1f}s, findings: {len(findings)}")

            for f in findings[:5]:
                fname = (
                    f.metadata.get("tool_name", f.finding_type)
                    if hasattr(f, "metadata")
                    else f.finding_type
                )
                conf = getattr(f, "confidence_raw", 0) or 0
                ok(f"    {fname}: confidence={conf:.3f}")

            if len(findings) > 5:
                ok(f"    ... and {len(findings) - 5} more")

        except Exception as e:
            flag("CRITICAL", f"Agent{agent_id}", str(e))
            traceback.print_exc()


# ══════════════════════════════════════════════════════════════════════════
#  TEST 4: Groq LLM Synthesis
# ══════════════════════════════════════════════════════════════════════════
async def test_groq_synthesis():
    header("TEST 4: Groq LLM Synthesis")

    config = get_settings()

    section("4.1 LLM Client Configuration")
    client = LLMClient(config)
    ok(f"  Provider: {client.provider}")
    ok(f"  Model: {client.model}")
    ok(f"  Available: {client.is_available}")

    if not client.is_available:
        flag("CRITICAL", "Groq", "LLM client not available — check LLM_API_KEY")
        return

    section("4.2 LLM Synthesis Call")
    try:
        t0 = time.time()
        result = await client.generate_synthesis(
            system_prompt="You are a forensic analyst. Respond with valid JSON.",
            user_content='Analyze this test: {"tool": "test", "confidence": 0.85}. Return {"verdict": "test", "analysis": "brief analysis"}',
            max_tokens=200,
            timeout_override=30.0,
        )
        elapsed = time.time() - t0
        ok(f"  Synthesis response in {elapsed:.1f}s")
        ok(f"  Response length: {len(result)} chars")

        if result:
            # Try to parse JSON
            try:
                parsed = json.loads(result)
                ok(f"  Valid JSON: {json.dumps(parsed, indent=2)[:200]}")
            except json.JSONDecodeError:
                flag("WARNING", "Groq.synthesis", "Response is not valid JSON")
                ok(f"  Raw response: {result[:200]}")
        else:
            flag("CRITICAL", "Groq.synthesis", "Empty response from Groq")
    except Exception as e:
        flag("CRITICAL", "Groq.synthesis", str(e))
        traceback.print_exc()


# ══════════════════════════════════════════════════════════════════════════
#  TEST 5: Gemini Integration
# ══════════════════════════════════════════════════════════════════════════
async def test_gemini():
    header("TEST 5: Gemini Vision Integration")

    config = get_settings()

    section("5.1 Gemini Client Configuration")
    gemini = GeminiVisionClient(config)
    ok(f"  Enabled: {gemini._enabled}")
    ok(f"  Primary model: {gemini.model}")
    ok(f"  Fallback chain: {gemini.fallback_chain}")
    ok(f"  Timeout: {gemini.timeout}s")

    if not gemini._enabled:
        flag("WARNING", "Gemini", "Gemini not enabled — checking fallback")

    section("5.2 Deep Forensic Analysis (actual call)")
    try:
        t0 = time.time()
        finding = await gemini.deep_forensic_analysis(
            file_path=TEST_IMAGE_PATH,
            exif_summary={"camera_make": "test", "datetime_original": "2026:01:01 12:00:00"},
        )
        elapsed = time.time() - t0

        ok(f"  Analysis completed in {elapsed:.1f}s")
        ok(f"  Model used: {finding.model_used}")
        ok(f"  Content type: {finding.file_type_assessment}")
        ok(f"  Confidence: {finding.confidence:.3f}")
        ok(f"  Description: {finding.content_description[:150]}...")

        if finding.manipulation_signals:
            ok(f"  Manipulation signals: {finding.manipulation_signals[:3]}")
        if finding.detected_objects:
            ok(f"  Detected objects: {finding.detected_objects[:5]}")
        if hasattr(finding, "_extracted_text") and finding._extracted_text:
            ok(f"  Extracted text: {finding._extracted_text[:3]}")
        if hasattr(finding, "_authenticity_verdict"):
            ok(f"  Authenticity verdict: {finding._authenticity_verdict}")

        if finding.error:
            flag("WARNING", "Gemini.analysis", f"Error: {finding.error}")

        # Check finding dict conversion
        finding_dict = finding.to_finding_dict("Agent1")
        ok(f"  Finding dict keys: {list(finding_dict.keys())[:10]}...")

        if not finding_dict.get("reasoning_summary"):
            flag("WARNING", "Gemini.dict", "Empty reasoning_summary in finding dict")

    except Exception as e:
        flag("CRITICAL", "Gemini.analysis", str(e))
        traceback.print_exc()

    section("5.3 File Content Identification")
    try:
        t0 = time.time()
        finding = await gemini.identify_file_content(
            file_path=TEST_IMAGE_PATH,
            agent_context="Testing file content identification",
        )
        elapsed = time.time() - t0
        ok(f"  Completed in {elapsed:.1f}s")
        ok(f"  Content: {finding.content_description[:150]}")
        ok(f"  Confidence: {finding.confidence:.3f}")
        if finding.error:
            flag("WARNING", "Gemini.identify", f"Error: {finding.error}")
    except Exception as e:
        flag("CRITICAL", "Gemini.identify", str(e))


# ══════════════════════════════════════════════════════════════════════════
#  TEST 6: Arbiter Deliberation
# ══════════════════════════════════════════════════════════════════════════
async def test_arbiter():
    header("TEST 6: Arbiter Deliberation & Report Generation")

    config = get_settings()
    session_id = uuid4()

    section("6.1 Create Agent Results (mock data)")
    # Create realistic mock agent results
    agent_results = {
        "Agent1": {
            "findings": [
                {
                    "agent_id": "Agent1",
                    "finding_type": "ela_analysis",
                    "confidence_raw": 0.85,
                    "status": "CONFIRMED",
                    "reasoning_summary": "ELA shows uniform compression across image — no manipulation detected",
                    "metadata": {
                        "tool_name": "ela_full_image",
                        "ela_mean": 3.2,
                        "ela_max": 12,
                        "anomaly_detected": False,
                        "court_defensible": True,
                    },
                    "evidence_refs": [],
                    "calibrated_probability": 0.85,
                },
                {
                    "agent_id": "Agent1",
                    "finding_type": "frequency_analysis",
                    "confidence_raw": 0.78,
                    "status": "CONFIRMED",
                    "reasoning_summary": "Frequency domain shows natural distribution — no GAN artifacts",
                    "metadata": {
                        "tool_name": "frequency_domain_analysis",
                        "anomaly_score": 0.12,
                        "gan_artifact_detected": False,
                        "court_defensible": True,
                    },
                    "evidence_refs": [],
                    "calibrated_probability": 0.78,
                },
                {
                    "agent_id": "Agent1",
                    "finding_type": "noise_fingerprint",
                    "confidence_raw": 0.72,
                    "status": "CONFIRMED",
                    "reasoning_summary": "Noise fingerprint consistent — single source",
                    "metadata": {
                        "tool_name": "noise_fingerprint",
                        "verdict": "CONSISTENT",
                        "noise_consistency_score": 0.91,
                        "court_defensible": True,
                    },
                    "evidence_refs": [],
                    "calibrated_probability": 0.72,
                },
            ],
            "reflection_report": {"all_tasks_complete": True, "court_defensible": True},
            "react_chain": [],
        },
        "Agent3": {
            "findings": [
                {
                    "agent_id": "Agent3",
                    "finding_type": "object_detection",
                    "confidence_raw": 0.88,
                    "status": "CONFIRMED",
                    "reasoning_summary": "Objects detected — scene context normal",
                    "metadata": {
                        "tool_name": "object_detection",
                        "objects_found": 2,
                        "scene_consistent": True,
                        "court_defensible": True,
                    },
                    "evidence_refs": [],
                    "calibrated_probability": 0.88,
                },
            ],
            "reflection_report": {"all_tasks_complete": True, "court_defensible": True},
            "react_chain": [],
        },
        "Agent5": {
            "findings": [
                {
                    "agent_id": "Agent5",
                    "finding_type": "exif_analysis",
                    "confidence_raw": 0.65,
                    "status": "CONFIRMED",
                    "reasoning_summary": "Limited EXIF data — WEBP format",
                    "metadata": {
                        "tool_name": "exif_extract",
                        "exif_fields_found": 3,
                        "exif_fields_expected": 12,
                        "has_gps": False,
                        "court_defensible": True,
                    },
                    "evidence_refs": [],
                    "calibrated_probability": 0.65,
                },
            ],
            "reflection_report": {"all_tasks_complete": True, "court_defensible": True},
            "react_chain": [],
        },
    }

    section("6.2 Run Arbiter Deliberation")
    arbiter = CouncilArbiter(
        session_id=session_id,
        config=config,
    )

    try:
        t0 = time.time()
        report = await arbiter.deliberate(agent_results, case_id="TEST-CASE-001")
        elapsed = time.time() - t0
        ok(f"Arbiter deliberation completed in {elapsed:.1f}s")

        section("6.3 Report Validation")
        # Validate report structure
        assert isinstance(report, ForensicReport), "Report is not ForensicReport"
        ok("Report type: ForensicReport")
        ok(f"Report ID: {report.report_id}")
        ok(f"Session ID: {report.session_id}")
        ok(f"Case ID: {report.case_id}")

        # Executive summary
        if report.executive_summary:
            ok(f"Executive summary: {len(report.executive_summary)} chars")
            ok(f"  Preview: {report.executive_summary[:150]}...")
        else:
            flag("CRITICAL", "Arbiter.report", "Empty executive_summary")

        # Verdict
        ok(f"Overall verdict: {report.overall_verdict}")
        ok(f"Overall confidence: {report.overall_confidence:.3f}")
        ok(f"Overall error rate: {report.overall_error_rate:.3f}")
        ok(f"Manipulation probability: {report.manipulation_probability:.3f}")

        # Per-agent findings
        ok(f"Per-agent findings: {list(report.per_agent_findings.keys())}")
        for agent_id, findings in report.per_agent_findings.items():
            ok(f"  {agent_id}: {len(findings)} findings")

        # Per-agent metrics
        if report.per_agent_metrics:
            ok(f"Per-agent metrics: {list(report.per_agent_metrics.keys())}")
            for agent_id, metrics in report.per_agent_metrics.items():
                ok(
                    f"  {agent_id}: tools={metrics.get('total_tools_called', 0)}, "
                    f"success={metrics.get('tools_succeeded', 0)}, "
                    f"confidence={metrics.get('confidence_score', 0):.3f}"
                )
        else:
            flag("WARNING", "Arbiter.metrics", "No per-agent metrics")

        # Per-agent summary
        if report.per_agent_summary:
            ok(f"Per-agent summary present: {list(report.per_agent_summary.keys())}")
        else:
            flag("WARNING", "Arbiter.summary", "No per-agent summary")

        # Per-agent analysis (Groq narratives)
        if report.per_agent_analysis:
            ok(f"Per-agent narratives: {list(report.per_agent_analysis.keys())}")
            for agent_id, narrative in report.per_agent_analysis.items():
                ok(f"  {agent_id}: {len(narrative)} chars")
        else:
            flag("WARNING", "Arbiter.narratives", "No per-agent Groq narratives")

        # Verdict sentence & key findings
        if report.verdict_sentence:
            ok(f"Verdict sentence: {report.verdict_sentence[:150]}")
        else:
            flag("WARNING", "Arbiter.verdict_sentence", "Empty verdict_sentence")

        if report.key_findings:
            ok(f"Key findings: {len(report.key_findings)}")
            for kf in report.key_findings[:3]:
                ok(f"  - {kf[:100]}")
        else:
            flag("WARNING", "Arbiter.key_findings", "Empty key_findings")

        if report.reliability_note:
            ok(f"Reliability note: {report.reliability_note[:100]}")

        # Uncertainty statement
        if report.uncertainty_statement:
            ok(f"Uncertainty: {report.uncertainty_statement[:100]}")

        # Confidence range
        ok(
            f"Confidence range: [{report.confidence_min:.3f}, {report.confidence_max:.3f}], std={report.confidence_std_dev:.3f}"
        )

        # Coverage
        ok(f"Applicable agents: {report.applicable_agent_count}")
        if report.skipped_agents:
            ok(f"Skipped agents: {report.skipped_agents}")
        if report.analysis_coverage_note:
            ok(f"Coverage note: {report.analysis_coverage_note[:100]}")

        # Cross-modal
        ok(f"Cross-modal confirmed: {len(report.cross_modal_confirmed)}")
        ok(f"Contested findings: {len(report.contested_findings)}")

        # Cryptographic signature
        section("6.4 Cryptographic Signing")
        signed_report = await arbiter.sign_report(report)
        ok(f"Report hash: {signed_report.report_hash[:16]}...")
        ok(f"Signature: {signed_report.cryptographic_signature[:32]}...")
        ok(f"Signed UTC: {signed_report.signed_utc}")

        if not signed_report.cryptographic_signature:
            flag("CRITICAL", "Arbiter.signing", "Empty cryptographic signature")
        if not signed_report.report_hash:
            flag("CRITICAL", "Arbiter.signing", "Empty report hash")

    except Exception as e:
        flag("CRITICAL", "Arbiter.deliberate", str(e))
        traceback.print_exc()


# ══════════════════════════════════════════════════════════════════════════
#  TEST 7: Full Pipeline Integration
# ══════════════════════════════════════════════════════════════════════════
async def test_full_pipeline():
    header("TEST 7: Full Pipeline (Agent1 + Agent3 + Agent5 + Arbiter)")

    config = get_settings()
    session_id = uuid4()
    wm = WorkingMemory(redis_client=None, custody_logger=None)
    em = EpisodicMemory(qdrant_client=None, custody_logger=None)
    cl = CustodyLogger(postgres_client=None)
    from core.persistence.storage import LocalStorageBackend

    es = EvidenceStore(
        postgres_client=None,
        storage_backend=LocalStorageBackend(storage_path="./storage/evidence"),
        custody_logger=cl,
    )
    artifact = await create_evidence_artifact(config)

    section("7.1 Run All Active Agents Concurrently")

    async def run_one(agent_class, agent_id):
        agent = agent_class(
            agent_id=agent_id,
            session_id=session_id,
            evidence_artifact=artifact,
            config=config,
            working_memory=wm,
            episodic_memory=em,
            custody_logger=cl,
            evidence_store=es,
        )
        if not agent.supports_uploaded_file:
            return agent_id, [], True  # skipped

        try:
            # Initial
            await agent.run_investigation()
            # Deep
            await agent.run_deep_investigation()
            return agent_id, agent._findings, False
        except Exception as e:
            return agent_id, [], str(e)

    t0 = time.time()
    results = await asyncio.gather(
        run_one(Agent1Image, "Agent1"),
        run_one(Agent3Object, "Agent3"),
        run_one(Agent5Metadata, "Agent5"),
        return_exceptions=True,
    )
    elapsed = time.time() - t0
    ok(f"All agents completed in {elapsed:.1f}s")

    section("7.2 Compile Results for Arbiter")
    arbiter_input = {}
    for r in results:
        if isinstance(r, BaseException):
            flag("CRITICAL", "Pipeline", f"Agent raised exception: {r}")
            continue
        agent_id, findings, error = r
        if error and error != True:
            flag("WARNING", f"Pipeline.{agent_id}", f"Error: {error}")
            continue

        if error == True:
            ok(f"  {agent_id}: SKIPPED (file type)")
            continue

        # Normalize findings to dicts
        normalized = []
        for f in findings:
            if hasattr(f, "model_dump"):
                normalized.append(f.model_dump(mode="json"))
            elif isinstance(f, dict):
                normalized.append(f)
            else:
                normalized.append(vars(f))

        arbiter_input[agent_id] = {
            "findings": normalized,
            "reflection_report": {},
            "react_chain": [],
        }
        ok(f"  {agent_id}: {len(normalized)} findings")

    section("7.3 Run Arbiter on Real Agent Data")
    try:
        arbiter = CouncilArbiter(session_id=session_id, config=config)
        t0 = time.time()
        report = await asyncio.wait_for(
            arbiter.deliberate(arbiter_input, case_id="FULL-PIPELINE-TEST"),
            timeout=150.0,
        )
        elapsed = time.time() - t0
        ok(f"Arbiter completed in {elapsed:.1f}s")
        ok(f"Verdict: {report.overall_verdict}")
        ok(f"Confidence: {report.overall_confidence:.3f}")
        ok(f"Findings: {sum(len(f) for f in report.per_agent_findings.values())} total")

        # Sign
        signed = await arbiter.sign_report(report)
        ok(
            f"Signed: hash={signed.report_hash[:16]}..., sig={signed.cryptographic_signature[:32]}..."
        )

    except TimeoutError:
        flag("CRITICAL", "Pipeline.arbiter", "Arbiter timed out after 150s")
    except Exception as e:
        flag("CRITICAL", "Pipeline.arbiter", str(e))
        traceback.print_exc()


# ══════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════
async def main():
    header("FORENSIC COUNCIL — COMPREHENSIVE SYSTEM TEST")
    print(f"Test image: {TEST_IMAGE_PATH}")
    print(f"Exists: {os.path.exists(TEST_IMAGE_PATH)}")

    if not os.path.exists(TEST_IMAGE_PATH):
        fail(f"Test image not found at {TEST_IMAGE_PATH}")
        # Try to find it
        for root, dirs, files in os.walk(str(Path(__file__).parent)):
            for f in files:
                if f.endswith((".webp", ".jpg", ".png", ".jpeg")):
                    found = os.path.join(root, f)
                    print(f"  Found: {found}")

    config = get_settings()
    print(f"LLM Provider: {config.llm_provider}")
    print(f"LLM Model: {config.llm_model}")
    print(f"LLM Key: {'SET' if config.llm_api_key else 'NOT SET'}")
    print(f"Gemini Key: {'SET' if config.gemini_api_key else 'NOT SET'}")
    print(f"Gemini Model: {config.gemini_model}")

    # Run tests in order
    agent1, findings = await test_agent1_initial()
    if agent1:
        await test_agent1_deep(agent1)
    await test_other_agents()
    await test_groq_synthesis()
    await test_gemini()
    await test_arbiter()
    await test_full_pipeline()

    # Summary
    header("TEST SUMMARY")
    critical = [i for i in issues if i["severity"] == "CRITICAL"]
    warnings = [i for i in issues if i["severity"] == "WARNING"]

    print(f"\n  Critical issues: {len(critical)}")
    for i in critical:
        fail(f"  [{i['location']}] {i['message']}")

    print(f"\n  Warnings: {len(warnings)}")
    for i in warnings:
        warn(f"  [{i['location']}] {i['message']}")

    if not critical:
        print(f"\n{C.GREEN}{C.BOLD}  ALL CRITICAL TESTS PASSED{C.END}")
    else:
        print(f"\n{C.RED}{C.BOLD}  {len(critical)} CRITICAL ISSUE(S) FOUND{C.END}")

    return issues


if __name__ == "__main__":
    issues = asyncio.run(main())


# Proper pytest wrapper for CI/linting
@pytest.mark.requires_docker
@pytest.mark.requires_network
@pytest.mark.slow
def test_system_smoke_runs_without_crash():
    """
    Gate: system test runner must complete without unhandled exception.

    This is a smoke test that verifies the system test can run.
    Full system tests require a running Docker stack with all services.
    """
    issues = asyncio.run(main())
    critical = [i for i in issues if i["severity"] == "CRITICAL"]
    assert critical == [], f"System test found critical issues: {critical}"

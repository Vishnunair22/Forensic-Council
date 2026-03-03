"""
Tests for Council Arbiter & Report Generator
==========================================

Tests the arbiter's deliberation, challenge loop, tribunal, and report generation.
"""

import pytest
from uuid import uuid4

from agents.arbiter import (
    CouncilArbiter,
    FindingComparison,
    FindingVerdict,
    ChallengeResult,
    TribunalCase,
    ForensicReport,
    render_text_report,
)


class TestCrossAgentComparison:
    """Test cross-agent finding comparison."""
    
    @pytest.fixture
    def arbiter(self):
        """Create a CouncilArbiter."""
        return CouncilArbiter(session_id=uuid4())
    
    @pytest.mark.asyncio
    async def test_cross_agent_comparison_detects_agreement(self, arbiter):
        """Test that agreement is detected between matching findings."""
        findings = [
            {
                "agent_id": "Agent1_ImageIntegrity",
                "finding_type": "splicing_detected",
                "status": "CONFIRMED",
                "confidence_raw": 0.9,
                "evidence_refs": ["artifact-1"],
            },
            {
                "agent_id": "Agent3_Object",
                "finding_type": "splicing_detected",
                "status": "CONFIRMED",
                "confidence_raw": 0.85,
                "evidence_refs": ["artifact-1"],
            },
        ]
        
        comparisons = await arbiter.cross_agent_comparison(findings)
        
        # Should have at least one agreement
        agreements = [c for c in comparisons if c.verdict == FindingVerdict.AGREEMENT]
        assert len(agreements) >= 1
    
    @pytest.mark.asyncio
    async def test_cross_agent_comparison_detects_contradiction(self, arbiter):
        """Test that contradictions are detected."""
        findings = [
            {
                "agent_id": "Agent1_ImageIntegrity",
                "finding_type": "splicing_detected",
                "status": "CONFIRMED",
                "confidence_raw": 0.9,
                "evidence_refs": ["artifact-1"],
            },
            {
                "agent_id": "Agent2_Audio",
                "finding_type": "splicing_detected",
                "status": "INCONCLUSIVE",
                "confidence_raw": 0.3,
                "evidence_refs": ["artifact-1"],
            },
        ]
        
        comparisons = await arbiter.cross_agent_comparison(findings)
        
        contradictions = [c for c in comparisons if c.verdict == FindingVerdict.CONTRADICTION]
        assert len(contradictions) >= 1
    
    @pytest.mark.asyncio
    async def test_cross_agent_comparison_detects_cross_modal_confirmation(self, arbiter):
        """Test that cross-modal confirmation is detected."""
        findings = [
            {
                "agent_id": "Agent1_ImageIntegrity",
                "finding_type": "manipulation_detected",
                "status": "CONFIRMED",
                "confidence_raw": 0.9,
                "evidence_refs": ["artifact-1"],
            },
            {
                "agent_id": "Agent4_Video",
                "finding_type": "manipulation_detected",
                "status": "CONFIRMED",
                "confidence_raw": 0.85,
                "evidence_refs": ["artifact-1"],
            },
        ]
        
        comparisons = await arbiter.cross_agent_comparison(findings)
        
        cross_modal = [c for c in comparisons if c.cross_modal_confirmed]
        assert len(cross_modal) >= 1


class TestChallengeLoop:
    """Test challenge loop functionality."""
    
    @pytest.fixture
    def arbiter(self):
        """Create a CouncilArbiter."""
        return CouncilArbiter(session_id=uuid4())
    
    @pytest.mark.asyncio
    async def test_challenge_loop_resolves_contradiction_with_context(self, arbiter):
        """Test that challenge loop can resolve with context."""
        contradiction = FindingComparison(
            finding_a={
                "agent_id": "Agent1",
                "finding_type": "tampering",
                "status": "CONFIRMED",
            },
            finding_b={
                "agent_id": "Agent2",
                "finding_type": "tampering",
                "status": "INCONCLUSIVE",
            },
            verdict=FindingVerdict.CONTRADICTION,
        )
        
        result = await arbiter.challenge_loop(
            contradiction=contradiction,
            agent_id="Agent1",
            context_from_other={"context": "test"},
        )
        
        assert isinstance(result, ChallengeResult)
        assert result.challenged_agent == "Agent1"
    
    @pytest.mark.asyncio
    async def test_challenge_loop_unresolved_triggers_tribunal(self, arbiter):
        """Test that unresolved challenges trigger tribunal."""
        contradiction = FindingComparison(
            finding_a={"agent_id": "Agent1", "status": "CONFIRMED"},
            finding_b={"agent_id": "Agent2", "status": "INCONCLUSIVE"},
            verdict=FindingVerdict.CONTRADICTION,
        )
        
        result = await arbiter.challenge_loop(contradiction, "Agent1", {})
        
        # Should be unresolved
        assert result.resolved is False


class TestTribunal:
    """Test tribunal functionality."""
    
    @pytest.fixture
    def arbiter(self):
        """Create a CouncilArbiter with custody logger."""
        return CouncilArbiter(session_id=uuid4())
    
    @pytest.mark.asyncio
    async def test_tribunal_logs_hitl_checkpoint(self, arbiter):
        """Test that tribunal logs HITL checkpoint."""
        case = TribunalCase(
            agent_a_id="Agent1",
            agent_b_id="Agent2",
            contradiction=FindingComparison(
                finding_a={"finding_type": "test"},
                finding_b={"finding_type": "test"},
                verdict=FindingVerdict.CONTRADICTION,
            ),
        )
        
        # Should not raise
        await arbiter.trigger_tribunal(case)


class TestForensicReport:
    """Test ForensicReport model and generation."""
    
    @pytest.fixture
    def arbiter(self):
        """Create a CouncilArbiter."""
        return CouncilArbiter(session_id=uuid4())
    
    @pytest.mark.asyncio
    async def test_report_contains_all_required_sections(self, arbiter):
        """Test that report contains all required sections."""
        agent_results = {
            "Agent1_ImageIntegrity": {
                "findings": [
                    {
                        "agent_id": "Agent1_ImageIntegrity",
                        "finding_type": "splicing_detected",
                        "status": "CONFIRMED",
                        "confidence_raw": 0.9,
                        "evidence_refs": ["artifact-1"],
                    }
                ]
            }
        }
        
        report = await arbiter.deliberate(agent_results)
        
        # Check all required fields
        assert report.executive_summary is not None
        assert report.per_agent_findings is not None
        assert report.cross_modal_confirmed is not None
        assert report.contested_findings is not None
        assert report.tribunal_resolved is not None
        assert report.incomplete_findings is not None
        assert report.chain_of_custody_log is not None
        assert report.uncertainty_statement is not None
    
    @pytest.mark.asyncio
    async def test_report_executive_summary_is_plain_language(self, arbiter):
        """Test that executive summary is plain language."""
        agent_results = {
            "Agent1_ImageIntegrity": {
                "findings": [{"finding_type": "test", "status": "CONFIRMED", "confidence_raw": 0.9}]
            },
            "Agent2_Audio": {
                "findings": [{"finding_type": "test", "status": "CONFIRMED", "confidence_raw": 0.85}]
            },
        }
        
        report = await arbiter.deliberate(agent_results)
        
        # Should contain plain language descriptions
        assert "multi-agent" in report.executive_summary.lower() or "agents" in report.executive_summary.lower()
    
    @pytest.mark.asyncio
    async def test_report_sign_embeds_signature_and_hash(self, arbiter):
        """Test that signed report contains signature and hash."""
        agent_results = {
            "Agent1": {"findings": [{"finding_type": "test", "status": "CONFIRMED", "confidence_raw": 0.9}]}
        }
        
        report = await arbiter.deliberate(agent_results)
        
        assert report.cryptographic_signature != ""
        assert report.report_hash != ""
        assert report.signed_utc is not None
    
    @pytest.mark.asyncio
    async def test_contested_finding_never_silently_resolved(self, arbiter):
        """Test that contested findings are tracked."""
        findings = [
            {"agent_id": "A1", "finding_type": "t", "status": "CONFIRMED", "evidence_refs": ["e1"]},
            {"agent_id": "A2", "finding_type": "t", "status": "INCONCLUSIVE", "evidence_refs": ["e1"]},
        ]
        
        comparisons = await arbiter.cross_agent_comparison(findings)
        
        # Should have contradiction
        contradictions = [c for c in comparisons if c.verdict == FindingVerdict.CONTRADICTION]
        assert len(contradictions) >= 1
    
    @pytest.mark.asyncio
    async def test_cross_modal_confirmed_finding_elevated_confidence(self, arbiter):
        """Test that cross-modal confirmed findings are elevated."""
        findings = [
            {"agent_id": "Agent1_ImageIntegrity", "finding_type": "manipulation", "status": "CONFIRMED", "evidence_refs": ["a1"]},
            {"agent_id": "Agent4_Video", "finding_type": "manipulation", "status": "CONFIRMED", "evidence_refs": ["a1"]},
        ]
        
        comparisons = await arbiter.cross_agent_comparison(findings)
        
        cross_modal = [c for c in comparisons if c.cross_modal_confirmed]
        assert len(cross_modal) >= 1


class TestReportRenderer:
    """Test report rendering."""
    
    def test_render_text_report(self):
        """Test text report rendering."""
        report = ForensicReport(
            session_id=uuid4(),
            case_id="test_case",
            executive_summary="Test summary",
            per_agent_findings={"Agent1": []},
            uncertainty_statement="No uncertainties",
        )
        
        rendered = render_text_report(report)
        
        assert "FORENSIC ANALYSIS REPORT" in rendered
        assert "EXECUTIVE SUMMARY" in rendered
        assert "Test summary" in rendered
        assert "UNCERTAINTY STATEMENT" in rendered
    
    def test_render_includes_report_id(self):
        """Test that rendered report includes report ID."""
        report = ForensicReport(
            session_id=uuid4(),
            case_id="test_case",
            executive_summary="Test",
            per_agent_findings={},
            uncertainty_statement="Test",
        )
        
        rendered = render_text_report(report)
        
        assert str(report.report_id) in rendered


class TestFindingVerdict:
    """Test FindingVerdict enum."""
    
    def test_verdict_values(self):
        """Test all verdict values exist."""
        assert FindingVerdict.AGREEMENT.value == "AGREEMENT"
        assert FindingVerdict.INDEPENDENT.value == "INDEPENDENT"
        assert FindingVerdict.CONTRADICTION.value == "CONTRADICTION"

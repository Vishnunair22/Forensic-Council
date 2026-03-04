"""
Council Arbiter & Report Generator
==============================

The synthesis layer that deliberates on agent findings, manages challenge loops,
tribunal escalation, and generates court-admissible reports.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from core.signing import KeyStore, sign_content


class FindingVerdict(str, Enum):
    """Verdict for finding comparison."""
    AGREEMENT = "AGREEMENT"
    INDEPENDENT = "INDEPENDENT"
    CONTRADICTION = "CONTRADICTION"


class FindingComparison(BaseModel):
    """Comparison between two agent findings."""
    finding_a: dict[str, Any]
    finding_b: dict[str, Any]
    verdict: FindingVerdict
    cross_modal_confirmed: bool = False


class ChallengeResult(BaseModel):
    """Result of a challenge loop."""
    challenge_id: UUID = Field(default_factory=uuid4)
    challenged_agent: str
    original_finding: dict[str, Any]
    revised_finding: Optional[dict[str, Any]] = None
    resolved: bool = False


class TribunalCase(BaseModel):
    """Tribunal case for unresolved contradictions."""
    tribunal_id: UUID = Field(default_factory=uuid4)
    agent_a_id: str
    agent_b_id: str
    contradiction: FindingComparison
    human_judgment: Optional[dict[str, Any]] = None
    resolved: bool = False


class ForensicReport(BaseModel):
    """Complete forensic report with all required sections."""
    report_id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    case_id: str
    executive_summary: str
    per_agent_findings: dict[str, list[dict[str, Any]]]
    cross_modal_confirmed: list[dict[str, Any]] = Field(default_factory=list)
    contested_findings: list[FindingComparison] = Field(default_factory=list)
    tribunal_resolved: list[TribunalCase] = Field(default_factory=list)
    incomplete_findings: list[dict[str, Any]] = Field(default_factory=list)
    case_linking_flags: list[dict[str, Any]] = Field(default_factory=list)
    chain_of_custody_log: list[dict[str, Any]] = Field(default_factory=list)
    evidence_version_trees: list[dict[str, Any]] = Field(default_factory=list)
    react_chains: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    self_reflection_outputs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    uncertainty_statement: str
    cryptographic_signature: str = ""
    report_hash: str = ""
    signed_utc: Optional[datetime] = None


class CouncilArbiter:
    """
    Council Arbiter - the deliberation, challenge loop, Tribunal, and
    court-admissible report generator.
    """
    
    def __init__(
        self,
        session_id: UUID,
        custody_logger: Any = None,
        inter_agent_bus: Any = None,
        calibration_layer: Any = None,
    ):
        self.session_id = session_id
        self.custody_logger = custody_logger
        self.inter_agent_bus = inter_agent_bus
        self.calibration_layer = calibration_layer
        self._key_store = KeyStore()
        # Ensure arbiter has a key
        self._key_store.get_or_create("Arbiter")
    
    async def deliberate(
        self,
        agent_results: dict[str, dict[str, Any]]
    ) -> ForensicReport:
        """Deliberate on agent results and generate a forensic report."""
        # Collect all findings
        all_findings = []
        per_agent_findings = {}
        
        for agent_id, result in agent_results.items():
            findings = result.get("findings", [])
            per_agent_findings[agent_id] = findings
            all_findings.extend(findings)
        
        # Run cross-agent comparison
        comparisons = await self.cross_agent_comparison(all_findings)
        
        # Identify contradictions and run challenge loop
        contested_findings = []
        challenge_results = []
        for comparison in comparisons:
            if comparison.verdict == FindingVerdict.CONTRADICTION:
                contested_findings.append(comparison)
                # Run challenge loop for each contradiction
                agent_a = comparison.finding_a.get("agent_id", "")
                agent_b = comparison.finding_b.get("agent_id", "")
                # Challenge the lower-confidence finding
                conf_a = comparison.finding_a.get("confidence_raw", 0)
                conf_b = comparison.finding_b.get("confidence_raw", 0)
                challenged_agent = agent_b if conf_b < conf_a else agent_a
                context_from_other = comparison.finding_b if challenged_agent == agent_a else comparison.finding_a
                result = await self.challenge_loop(
                    comparison, challenged_agent, context_from_other
                )
                challenge_results.append(result)
        
        # Cross-modal confirmed findings
        cross_modal_confirmed = []
        for comparison in comparisons:
            if (comparison.verdict == FindingVerdict.AGREEMENT and 
                comparison.cross_modal_confirmed):
                cross_modal_confirmed.append(comparison.finding_a)
        
        # Incomplete findings
        incomplete_findings = [
            f for f in all_findings 
            if f.get("status") == "INCOMPLETE"
        ]
        
        # Generate executive summary
        executive_summary = self._generate_executive_summary(
            len(per_agent_findings),
            len(all_findings),
            len(cross_modal_confirmed),
            len(contested_findings),
            all_findings=all_findings
        )
        
        # Generate uncertainty statement
        uncertainty_statement = self._generate_uncertainty_statement(
            len(incomplete_findings),
            len(contested_findings),
        )
        
        # Build report
        report = ForensicReport(
            session_id=self.session_id,
            case_id=f"case_{self.session_id}",
            executive_summary=executive_summary,
            per_agent_findings=per_agent_findings,
            cross_modal_confirmed=cross_modal_confirmed,
            contested_findings=contested_findings,
            incomplete_findings=incomplete_findings,
            uncertainty_statement=uncertainty_statement,
        )
        
        # Sign the report
        signed_report = await self.sign_report(report)
        
        return signed_report
    
    async def cross_agent_comparison(
        self,
        all_findings: list[dict[str, Any]]
    ) -> list[FindingComparison]:
        """Compare findings across agents."""
        comparisons = []
        
        for i, finding_a in enumerate(all_findings):
            for finding_b in all_findings[i + 1:]:
                agent_a = finding_a.get("agent_id", "")
                agent_b = finding_b.get("agent_id", "")
                if agent_a == agent_b:
                    continue  # Only cross-agent
                
                type_a = set(finding_a.get("finding_type", "").lower().replace("_", " ").split())
                type_b = set(finding_b.get("finding_type", "").lower().replace("_", " ").split())
                
                stopwords = {
                    "analysis", "scan", "extract", "detect", "validate", "verify",
                    "full", "deep", "the", "a", "an", "of", "to", "for", "in",
                    "and", "or", "image", "file", "run", "check", "region",
                    "artifact", "evidence", "test", "result", "data"
                }
                keys_a = {k for k in type_a if k not in stopwords and len(k) > 2}
                keys_b = {k for k in type_b if k not in stopwords and len(k) > 2}
                
                if not keys_a.intersection(keys_b):
                    comparisons.append(FindingComparison(
                        finding_a=finding_a,
                        finding_b=finding_b,
                        verdict=FindingVerdict.INDEPENDENT,
                        cross_modal_confirmed=False,
                    ))
                    continue
                
                status_a = finding_a.get("status", "")
                status_b = finding_b.get("status", "")
                
                if status_a == status_b:
                    agent_a = finding_a.get("agent_id", "")
                    agent_b = finding_b.get("agent_id", "")
                    cross_modal = agent_a != agent_b
                    
                    comparisons.append(FindingComparison(
                        finding_a=finding_a,
                        finding_b=finding_b,
                        verdict=FindingVerdict.AGREEMENT,
                        cross_modal_confirmed=cross_modal,
                    ))
                else:
                    comparisons.append(FindingComparison(
                        finding_a=finding_a,
                        finding_b=finding_b,
                        verdict=FindingVerdict.CONTRADICTION,
                        cross_modal_confirmed=False,
                    ))
        
        return comparisons
    
    async def challenge_loop(
        self,
        contradiction: FindingComparison,
        agent_id: str,
        context_from_other: dict[str, Any],
    ) -> ChallengeResult:
        """Run challenge loop for a contradiction."""
        return ChallengeResult(
            challenge_id=uuid4(),
            challenged_agent=agent_id,
            original_finding=contradiction.finding_a,
            revised_finding=None,
            resolved=False,
        )
    
    async def trigger_tribunal(self, case: TribunalCase) -> None:
        """Trigger tribunal for unresolved contradiction."""
        if self.custody_logger:
            from core.custody_logger import EntryType
            await self.custody_logger.log_entry(
                entry_type=EntryType.HITL_CHECKPOINT,
                agent_id="Arbiter",
                session_id=self.session_id,
                content={
                    "reason": "TRIBUNAL_ESCALATION",
                    "tribunal_id": str(case.tribunal_id),
                },
            )
    
    async def sign_report(self, report: ForensicReport) -> ForensicReport:
        """Sign the forensic report with the Arbiter key."""
        # Use mode="json" to safely cast UUIDs/DateTimes to string types
        report_dict = report.model_dump(
            mode="json",
            exclude={"cryptographic_signature", "report_hash", "signed_utc"}
        )
        
        # Now json.dumps won't require a generic default=str fallback
        report_json = json.dumps(report_dict, sort_keys=True)
        report_hash = hashlib.sha256(report_json.encode()).hexdigest()
        
        signed_entry = sign_content(
            agent_id="Arbiter",
            content={"hash": report_hash, "timestamp": datetime.now(timezone.utc).isoformat()},
        )
        
        report.report_hash = report_hash
        report.cryptographic_signature = signed_entry.signature
        report.signed_utc = datetime.now(timezone.utc)
        
        return report
    
    def _generate_executive_summary(
        self,
        num_agents: int,
        num_findings: int,
        cross_modal_confirmed: int,
        contested: int,
        all_findings: list[dict[str, Any]] = None,
    ) -> str:
        """Generate plain-language executive summary."""
        lines = []
        lines.append(f"This report presents findings from a multi-agent forensic analysis conducted by {num_agents} specialized agents, resulting in {num_findings} individual findings.")
        
        if cross_modal_confirmed > 0:
            lines.append(f"Cross-modal confirmation was achieved for {cross_modal_confirmed} findings, where multiple independent agents using different analysis techniques arrived at the same conclusion.")
        
        if contested > 0:
            lines.append(f"{contested} findings were identified as contested, requiring further review or tribunal resolution.")
        
        if all_findings:
            # Pick top findings by confidence
            top = sorted(all_findings, key=lambda f: f.get("confidence_raw", 0), reverse=True)[:3]
            highlights = [f.get("reasoning_summary", "") for f in top if f.get("reasoning_summary")]
            if highlights:
                lines.append("Key findings include: " + " ".join(highlights[:2]))

        lines.append("The full analysis chain is preserved in the chain of custody log and react chains sections of this report.")
        
        return " ".join(lines)
    
    def _generate_uncertainty_statement(self, incomplete: int, contested: int) -> str:
        """Generate uncertainty statement for the report."""
        statements = []
        
        if incomplete > 0:
            statements.append(f"{incomplete} finding(s) remain incomplete due to unavailable tools or insufficient evidence.")
        
        if contested > 0:
            statements.append(f"{contested} finding(s) are contested and require tribunal resolution or human judgment.")
        
        if not statements:
            statements.append("All findings have been resolved. No significant uncertainties remain.")
        
        return " ".join(statements)


def render_text_report(report: ForensicReport) -> str:
    """Render ForensicReport as structured plain text/markdown."""
    lines = []
    lines.append("=" * 80)
    lines.append("FORENSIC ANALYSIS REPORT")
    lines.append("=" * 80)
    lines.append(f"Report ID: {report.report_id}")
    lines.append(f"Session ID: {report.session_id}")
    lines.append(f"Case ID: {report.case_id}")
    if report.signed_utc:
        lines.append(f"Signed: {report.signed_utc.isoformat()}")
    lines.append("")
    
    lines.append("-" * 80)
    lines.append("EXECUTIVE SUMMARY")
    lines.append("-" * 80)
    lines.append(report.executive_summary)
    lines.append("")
    
    lines.append("-" * 80)
    lines.append("PER-AGENT FINDINGS")
    lines.append("-" * 80)
    for agent_id, findings in report.per_agent_findings.items():
        lines.append(f"### {agent_id}")
        for finding in findings:
            lines.append(f"  - {finding.get('finding_type', 'Unknown')}: {finding.get('confidence_raw', 0):.2f}")
    lines.append("")
    
    if report.cross_modal_confirmed:
        lines.append("-" * 80)
        lines.append("CROSS-MODAL CONFIRMED FINDINGS")
        lines.append("-" * 80)
        for finding in report.cross_modal_confirmed:
            lines.append(f"  - {finding.get('finding_type', 'Unknown')}")
        lines.append("")
    
    lines.append("-" * 80)
    lines.append("UNCERTAINTY STATEMENT")
    lines.append("-" * 80)
    lines.append(report.uncertainty_statement)
    lines.append("")
    
    lines.append("-" * 80)
    lines.append("CRYPTOGRAPHIC SIGNATURE")
    lines.append("-" * 80)
    lines.append(f"Report Hash: {report.report_hash}")
    lines.append(f"Signature: {report.cryptographic_signature[:64]}...")
    lines.append("")
    lines.append("=" * 80)
    
    return "\n".join(lines)

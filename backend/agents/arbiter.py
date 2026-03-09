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

from core.config import Settings, get_settings
from core.llm_client import LLMClient
from core.logging import get_logger
from core.signing import KeyStore, sign_content

logger = get_logger(__name__)


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
    contested_findings: list[dict[str, Any]] = Field(default_factory=list)
    tribunal_resolved: list[TribunalCase] = Field(default_factory=list)
    incomplete_findings: list[dict[str, Any]] = Field(default_factory=list)
    stub_findings: list[dict[str, Any]] = Field(default_factory=list)  # Stub/implemented tool results
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
        agent_factory: Any = None,
        config: Settings | None = None,
    ):
        self.session_id = session_id
        self.custody_logger = custody_logger
        self.inter_agent_bus = inter_agent_bus
        self.calibration_layer = calibration_layer
        self.agent_factory = agent_factory
        self.config = config or get_settings()
        self._key_store = KeyStore()
        # Ensure arbiter has a key
        self._key_store.get_or_create("Arbiter")
    
    async def deliberate(
        self,
        agent_results: dict[str, dict[str, Any]],
        case_id: str = "",
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
                contested_findings.append(comparison.model_dump(mode="json"))
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
        seen_ids = set()
        cross_modal_confirmed = []
        for comparison in comparisons:
            if (comparison.verdict == FindingVerdict.AGREEMENT and 
                comparison.cross_modal_confirmed):
                fid = comparison.finding_a.get("finding_id")
                if fid not in seen_ids:
                    seen_ids.add(fid)
                    cross_modal_confirmed.append(comparison.finding_a)
        
        # Incomplete findings (excluding stub results which are not court-defensible)
        incomplete_findings = [
            f for f in all_findings 
            if f.get("status") == "INCOMPLETE"
        ]
        
        # Stub findings - results from unimplemented tools
        # These are tracked separately and excluded from verdict calculation
        stub_findings = [
            f for f in all_findings
            if f.get("stub_result") == True
        ]
        
        # Log warning if stub findings are present
        if stub_findings:
            logger.warning(
                f"Report contains {len(stub_findings)} stub findings that should not be used for verdicts",
                stub_count=len(stub_findings),
            )
        
        # Generate executive summary
        executive_summary = await self._generate_executive_summary(
            len(per_agent_findings),
            len(all_findings),
            len(cross_modal_confirmed),
            len(contested_findings),
            all_findings=all_findings
        )
        
        # Generate uncertainty statement
        uncertainty_statement = await self._generate_uncertainty_statement(
            len(incomplete_findings),
            len(contested_findings),
        )
        
        # Build report
        report = ForensicReport(
            session_id=self.session_id,
            case_id=case_id or f"case_{self.session_id}",
            executive_summary=executive_summary,
            per_agent_findings=per_agent_findings,
            cross_modal_confirmed=cross_modal_confirmed,
            contested_findings=contested_findings,
            incomplete_findings=incomplete_findings,
            stub_findings=stub_findings,  # Include stub findings for transparency
            uncertainty_statement=uncertainty_statement,
        )
        
        return report
    
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
                    "the", "a", "an", "of", "to", "for", "in", "and", "or",
                    "full", "deep", "run", "check", "test", "result", "data", "file"
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
        """
        Run challenge loop for a contradiction.
        
        When agents disagree, the lower-confidence finding is challenged.
        The challenged agent is re-invoked with the contradicting context
        and asked to reconsider their finding.
        
        Args:
            contradiction: The contradiction between two findings
            agent_id: ID of the agent being challenged
            context_from_other: The contradicting finding's data as context
            
        Returns:
            ChallengeResult with the outcome of the challenge
        """
        from core.custody_logger import EntryType
        from core.logging import get_logger
        
        logger = get_logger(__name__)
        challenge_id = uuid4()
        
        logger.info(
            "Starting challenge loop",
            challenge_id=str(challenge_id),
            challenged_agent=agent_id,
            contradicting_agent=context_from_other.get("agent_id", "unknown"),
        )
        
        # Log challenge initiation
        if self.custody_logger:
            await self.custody_logger.log_entry(
                entry_type=EntryType.INTER_AGENT_CALL,
                agent_id="Arbiter",
                session_id=self.session_id,
                content={
                    "action": "challenge_initiated",
                    "challenge_id": str(challenge_id),
                    "challenged_agent": agent_id,
                    "contradiction_type": contradiction.verdict.value,
                    "original_finding_type": contradiction.finding_a.get("finding_type"),
                    "contradicting_finding_type": contradiction.finding_b.get("finding_type"),
                },
            )
        
        # Try to re-invoke the challenged agent if factory is available
        revised_finding = None
        resolved = False
        
        if self.agent_factory:
            try:
                # Create challenge context for the agent
                challenge_context = {
                    "challenge_id": str(challenge_id),
                    "challenged_finding": contradiction.finding_a,
                    "contradicting_finding": context_from_other,
                    "reason": "Cross-agent contradiction detected",
                    "request": "Re-examine your finding considering the contradicting evidence",
                }
                
                # Re-invoke the challenged agent
                logger.info(
                    "Re-invoking challenged agent",
                    agent_id=agent_id,
                    challenge_id=str(challenge_id),
                )
                
                revised_result = await self.agent_factory.reinvoke_agent(
                    agent_id=agent_id,
                    session_id=self.session_id,
                    challenge_context=challenge_context,
                )
                
                if revised_result and "findings" in revised_result:
                    # Find the revised finding matching the original
                    original_type = contradiction.finding_a.get("finding_type")
                    for finding in revised_result["findings"]:
                        if finding.get("finding_type") == original_type:
                            revised_finding = finding
                            break
                    
                    # If no matching type, take the first finding
                    if revised_finding is None and revised_result["findings"]:
                        revised_finding = revised_result["findings"][0]
                    
                    # Check if contradiction is resolved
                    if revised_finding:
                        # Compare revised finding with the contradicting one
                        revised_status = revised_finding.get("status", "")
                        contradicting_status = context_from_other.get("status", "")
                        
                        # If both now agree, contradiction is resolved
                        if revised_status == contradicting_status:
                            resolved = True
                            logger.info(
                                "Challenge resolved - findings now agree",
                                challenge_id=str(challenge_id),
                                agreed_status=revised_status,
                            )
                        else:
                            # Check if confidence changed significantly
                            original_conf = contradiction.finding_a.get("confidence_raw", 0)
                            revised_conf = revised_finding.get("confidence_raw", 0)
                            
                            if abs(revised_conf - original_conf) > 0.1:
                                # Agent changed its confidence significantly
                                # This is partial resolution - acknowledge the revision
                                resolved = True
                                logger.info(
                                    "Challenge partially resolved - confidence adjusted",
                                    challenge_id=str(challenge_id),
                                    original_confidence=original_conf,
                                    revised_confidence=revised_conf,
                                )
                
                # Log the challenge outcome
                if self.custody_logger:
                    await self.custody_logger.log_entry(
                        entry_type=EntryType.SELF_REFLECTION,
                        agent_id=agent_id,
                        session_id=self.session_id,
                        content={
                            "action": "challenge_completed",
                            "challenge_id": str(challenge_id),
                            "resolved": resolved,
                            "has_revised_finding": revised_finding is not None,
                        },
                    )
                
            except Exception as e:
                logger.error(
                    "Challenge loop failed",
                    challenge_id=str(challenge_id),
                    error=str(e),
                    agent_id=agent_id,
                )
                # Log failure but still return result
                if self.custody_logger:
                    await self.custody_logger.log_entry(
                        entry_type=EntryType.ERROR,
                        agent_id="Arbiter",
                        session_id=self.session_id,
                        content={
                            "action": "challenge_failed",
                            "challenge_id": str(challenge_id),
                            "error": str(e),
                        },
                    )
        else:
            logger.warning(
                "No agent factory available for challenge loop",
                challenge_id=str(challenge_id),
                agent_id=agent_id,
            )
        
        return ChallengeResult(
            challenge_id=challenge_id,
            challenged_agent=agent_id,
            original_finding=contradiction.finding_a,
            revised_finding=revised_finding,
            resolved=resolved,
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
    
    async def _generate_executive_summary(
        self,
        num_agents: int,
        num_findings: int,
        cross_modal_confirmed: int,
        contested: int,
        all_findings: list[dict[str, Any]] = None,
    ) -> str:
        """
        Generate an executive summary.

        When LLM is configured (Groq recommended), uses the model to write
        a structured, plain-language summary from actual finding data.
        Falls back to a deterministic template if LLM is unavailable.
        """
        if self.config.llm_api_key and self.config.llm_provider != "none":
            try:
                result = await self._llm_executive_summary(
                    num_agents, num_findings, cross_modal_confirmed,
                    contested, all_findings or []
                )
                if result:
                    return result
            except Exception as exc:
                logger.warning("LLM executive summary failed, using template: %s", exc)

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
    ) -> str:
        """Generate executive summary using LLM synthesis."""
        client = LLMClient(self.config)

        # Build structured findings digest for the model
        top_findings = sorted(
            [f for f in all_findings if not f.get("stub_result")],
            key=lambda f: f.get("confidence_raw", 0),
            reverse=True,
        )[:8]

        findings_digest = []
        for f in top_findings:
            findings_digest.append({
                "agent": f.get("agent_id", "unknown"),
                "type": f.get("finding_type", "unknown"),
                "confidence": round(f.get("confidence_raw", 0), 3),
                "summary": f.get("reasoning_summary", ""),
                "status": f.get("status", ""),
                "cross_modal": f.get("cross_modal_confirmed", False),
            })

        system_prompt = """You are the Council Arbiter writing the Executive Summary section of a court-admissible forensic evidence report.

Your summary must be:
- Factual and grounded only in the structured findings data provided
- Written in formal, precise legal/forensic language
- 3-5 paragraphs covering: (1) scope of analysis, (2) key confirmed findings with confidence levels, (3) contested or inconclusive findings, (4) overall evidential weight and recommended next steps
- Free of speculation — only state what the data shows
- Explicit about limitations and uncertainties

Do NOT use bullet points. Write in continuous prose paragraphs."""

        user_content = f"""Forensic analysis statistics:
- Agents deployed: {num_agents}
- Total findings: {num_findings}
- Cross-modal confirmed (multiple agents agree): {cross_modal_confirmed}
- Contested findings (agents disagree): {contested}

Top findings by confidence:
{json.dumps(findings_digest, indent=2)}

Write the Executive Summary for this forensic report."""

        return await client.generate_synthesis(
            system_prompt=system_prompt,
            user_content=user_content,
            max_tokens=800,
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
            top = sorted(all_findings, key=lambda f: f.get("confidence_raw", 0), reverse=True)[:3]
            highlights = [f.get("reasoning_summary", "") for f in top if f.get("reasoning_summary")]
            if highlights:
                lines.append("Key findings include: " + " ".join(highlights[:2]))
        lines.append(
            "The full analysis chain is preserved in the chain of custody log and "
            "ReAct chains sections of this report."
        )
        return " ".join(lines)
    
    async def _generate_uncertainty_statement(self, incomplete: int, contested: int) -> str:
        """
        Generate the uncertainty and limitations statement.

        Uses LLM to produce a nuanced, legally-aware statement when configured.
        Falls back to deterministic template otherwise.
        """
        if self.config.llm_api_key and self.config.llm_provider != "none" and (incomplete > 0 or contested > 0):
            try:
                result = await self._llm_uncertainty_statement(incomplete, contested)
                if result:
                    return result
            except Exception as exc:
                logger.warning("LLM uncertainty statement failed, using template: %s", exc)

        return self._template_uncertainty_statement(incomplete, contested)

    async def _llm_uncertainty_statement(self, incomplete: int, contested: int) -> str:
        """Generate uncertainty statement using LLM."""
        client = LLMClient(self.config)

        system_prompt = """You are the Council Arbiter writing the Limitations and Uncertainty section of a forensic report.

Be specific and legally precise. Explain what the uncertainties mean for the evidential value of the report.
Write 2-3 sentences only. Do not use bullet points."""

        user_content = (
            f"Incomplete findings (tools unavailable or evidence insufficient): {incomplete}\n"
            f"Contested findings (agents disagree, not yet resolved): {contested}\n\n"
            "Write the uncertainty and limitations statement."
        )

        return await client.generate_synthesis(
            system_prompt=system_prompt,
            user_content=user_content,
            max_tokens=200,
        )

    def _template_uncertainty_statement(self, incomplete: int, contested: int) -> str:
        """Deterministic uncertainty template fallback."""
        statements = []
        if incomplete > 0:
            statements.append(
                f"{incomplete} finding(s) remain incomplete due to unavailable tools "
                "or insufficient evidence."
            )
        if contested > 0:
            statements.append(
                f"{contested} finding(s) are contested and require tribunal resolution "
                "or human judgment."
            )
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

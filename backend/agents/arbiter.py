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


class AgentMetrics(BaseModel):
    """Per-agent performance metrics computed at arbiter deliberation time."""
    agent_id: str
    agent_name: str
    total_tools_called: int = 0
    tools_succeeded: int = 0
    tools_failed: int = 0
    tools_not_applicable: int = 0    # tools that don't apply to this file type (not errors)
    error_rate: float = 0.0          # 0.0–1.0 (failed / applicable tools run)
    confidence_score: float = 0.0    # avg confidence across real applicable findings
    finding_count: int = 0
    skipped: bool = False            # True when file type not applicable


class ForensicReport(BaseModel):
    """Complete forensic report with all required sections."""
    report_id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    case_id: str
    executive_summary: str
    per_agent_findings: dict[str, list[dict[str, Any]]]
    per_agent_metrics: dict[str, Any] = Field(
        default_factory=dict,
        description="Per-agent tool success rates, error rates, and confidence scores.",
    )
    per_agent_analysis: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Per-agent Groq-synthesised narrative comparing initial vs deep findings. "
            "Keyed by agent_id. Only present for active agents."
        ),
    )
    overall_confidence: float = 0.0
    overall_error_rate: float = 0.0
    overall_verdict: str = "REVIEW REQUIRED"
    cross_modal_confirmed: list[dict[str, Any]] = Field(default_factory=list)
    contested_findings: list[dict[str, Any]] = Field(default_factory=list)
    tribunal_resolved: list[TribunalCase] = Field(default_factory=list)
    incomplete_findings: list[dict[str, Any]] = Field(default_factory=list)
    stub_findings: list[dict[str, Any]] = Field(default_factory=list)
    gemini_vision_findings: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Deep vision findings produced by Google Gemini (Agents 1, 3, 5 deep pass). "
            "Compiled separately for review; also present inside per_agent_findings."
        ),
    )
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
    
    # ── Shared agent name map ────────────────────────────────────────────
    _AGENT_NAMES: dict[str, str] = {
        "Agent1": "Image Forensics",
        "Agent2": "Audio Forensics",
        "Agent3": "Object Detection",
        "Agent4": "Video Forensics",
        "Agent5": "Metadata Forensics",
    }

    async def deliberate(
        self,
        agent_results: dict[str, dict[str, Any]],
        case_id: str = "",
    ) -> ForensicReport:
        """Deliberate on agent results and generate a forensic report.

        Only ACTIVE agents (those that ran real tools on the evidence) are used
        for Groq synthesis.  Skipped agents (file type not applicable) are
        excluded from the executive summary and verdict calculation but their
        skip findings are kept in per_agent_findings for transparency.

        Computes per-agent metrics (tool success/failure rates, confidence) and
        overall verdict from aggregated confidence + error rates.
        """
        _SKIP_FINDING_TYPES = {"file type not applicable", "format not supported"}

        def _is_skipped_agent(findings: list[dict[str, Any]]) -> bool:
            """True when all findings are file-type-not-applicable stubs."""
            if not findings:
                return True
            return all(
                str(f.get("finding_type", "")).lower() in _SKIP_FINDING_TYPES
                for f in findings
            )

        def _deduplicate_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
            """Remove duplicate findings with same finding_type produced by same tool."""
            seen: set[str] = set()
            out: list[dict[str, Any]] = []
            for f in findings:
                key = (
                    str(f.get("agent_id", "")),
                    str(f.get("finding_type", "")),
                    str(f.get("metadata", {}).get("tool_name", "") if isinstance(f.get("metadata"), dict) else ""),
                )
                if key not in seen:
                    seen.add(key)
                    out.append(f)
            return out

        def _compute_agent_metrics(
            agent_id: str, findings: list[dict[str, Any]], skipped: bool
        ) -> "AgentMetrics":
            agent_name = self._AGENT_NAMES.get(agent_id, agent_id)
            if skipped:
                return AgentMetrics(
                    agent_id=agent_id, agent_name=agent_name, skipped=True,
                    total_tools_called=0, tools_succeeded=0, tools_failed=0,
                    tools_not_applicable=0, error_rate=0.0,
                    confidence_score=0.0, finding_count=0,
                )
            real = [f for f in findings if str(f.get("finding_type","")).lower() not in _SKIP_FINDING_TYPES]
            total = len(real)

            not_applicable_flags = (
                "ela_not_applicable", "ghost_not_applicable",
            )
            def _is_not_applicable(f: dict) -> bool:
                meta = f.get("metadata") or {}
                return any(meta.get(flag) for flag in not_applicable_flags)

            def _is_failed(f: dict) -> bool:
                if _is_not_applicable(f):
                    return False  # not-applicable is expected, not a failure
                meta = f.get("metadata") or {}
                return (
                    meta.get("court_defensible") is False
                    or f.get("status") == "INCOMPLETE"
                )

            not_applicable = sum(1 for f in real if _is_not_applicable(f))
            failed = sum(1 for f in real if _is_failed(f))
            # Applicable = ran and was expected to produce a real result
            applicable = total - not_applicable
            succeeded = applicable - failed
            error_rate = round(failed / applicable, 3) if applicable > 0 else 0.0
            # Confidence only over findings that actually ran (not not-applicable, not failed)
            conf_scores = [
                f.get("calibrated_probability") or f.get("confidence_raw") or 0.0
                for f in real
                if not _is_not_applicable(f) and not _is_failed(f)
            ]
            confidence = round(sum(conf_scores) / len(conf_scores), 3) if conf_scores else 0.0
            return AgentMetrics(
                agent_id=agent_id, agent_name=agent_name, skipped=False,
                total_tools_called=total, tools_succeeded=succeeded,
                tools_failed=failed, tools_not_applicable=not_applicable,
                error_rate=error_rate, confidence_score=confidence,
                finding_count=total,
            )

        # Helper: call optional step-progress hook if set externally
        async def _step(msg: str) -> None:
            hook = getattr(self, "_step_hook", None)
            if hook is not None:
                try:
                    await hook(msg)
                except Exception:
                    pass

        # ── Partition agents into active vs skipped ───────────────────────
        await _step("Gathering all agent findings…")
        all_findings: list[dict[str, Any]] = []
        per_agent_findings: dict[str, list[dict[str, Any]]] = {}
        per_agent_metrics: dict[str, Any] = {}
        active_agent_results: dict[str, dict[str, Any]] = {}
        gemini_findings_by_agent: dict[str, list[dict[str, Any]]] = {}

        for agent_id, result in agent_results.items():
            raw_findings = result.get("findings", [])
            deduped = _deduplicate_findings(raw_findings)
            skipped = _is_skipped_agent(deduped)
            per_agent_findings[agent_id] = deduped
            metrics = _compute_agent_metrics(agent_id, deduped, skipped)
            per_agent_metrics[agent_id] = metrics.model_dump()

            if not skipped:
                active_agent_results[agent_id] = {**result, "findings": deduped}
                all_findings.extend(deduped)
                agent_gemini = [
                    f for f in deduped
                    if isinstance(f, dict)
                    and f.get("metadata", {}).get("analysis_source") == "gemini_vision"
                ]
                if agent_gemini:
                    gemini_findings_by_agent[agent_id] = agent_gemini

        logger.info(
            f"Arbiter: {len(active_agent_results)} active agents, "
            f"{len(agent_results) - len(active_agent_results)} skipped, "
            f"{len(all_findings)} total findings"
        )

        # ── Compile Gemini findings list ──────────────────────────────────
        gemini_vision_findings: list[dict[str, Any]] = []
        for gf_list in gemini_findings_by_agent.values():
            gemini_vision_findings.extend(gf_list)
        if gemini_vision_findings:
            logger.info(f"Arbiter: {len(gemini_vision_findings)} Gemini vision findings across {len(gemini_findings_by_agent)} agent(s)")

        # ── Compute overall confidence + error rate ───────────────────────
        active_metrics = [
            m for m in per_agent_metrics.values()
            if not m.get("skipped") and m.get("total_tools_called", 0) > 0
        ]
        overall_confidence = round(
            sum(m["confidence_score"] for m in active_metrics) / len(active_metrics), 3
        ) if active_metrics else 0.0
        overall_error_rate = round(
            sum(m["error_rate"] for m in active_metrics) / len(active_metrics), 3
        ) if active_metrics else 0.0

        # ── Verdict ───────────────────────────────────────────────────────
        # CERTAIN:     high confidence, low error, no contested
        # LIKELY:      good confidence, acceptable error
        # UNCERTAIN:   moderate confidence or some errors
        # INCONCLUSIVE: low confidence or high errors
        # MANIPULATION DETECTED: confidence indicates tampering

        # Run cross-agent comparison
        await _step("Running cross-modal comparison…")
        comparisons = await self.cross_agent_comparison(all_findings)

        # Identify contradictions and run challenge loop
        await _step("Resolving contested evidence…")
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
            if f.get("stub_result") is True
        ]

        # Log warning if stub findings are present
        if stub_findings:
            logger.warning(
                f"Report contains {len(stub_findings)} stub findings that should not be used for verdicts",
                stub_count=len(stub_findings),
            )

        # ── Per-agent Groq narrative (initial vs deep comparison) ──────────
        await _step("Generating per-agent analysis via Groq…")
        per_agent_analysis: dict[str, str] = {}
        for agent_id, result in active_agent_results.items():
            findings = result.get("findings", [])
            if not findings:
                continue
            try:
                narrative = await self._generate_agent_narrative(
                    agent_id=agent_id,
                    findings=findings,
                    metrics=per_agent_metrics.get(agent_id, {}),
                )
                if narrative:
                    per_agent_analysis[agent_id] = narrative
            except Exception as narr_err:
                logger.warning(f"Per-agent narrative failed for {agent_id}: {narr_err}")

        # ── Contested / incomplete / stub ─────────────────────────────────
        contested_findings_count = len(contested_findings)

        # ── Verdict ───────────────────────────────────────────────────────
        await _step("Calibrating confidence scores and computing verdict…")
        if overall_confidence >= 0.80 and overall_error_rate <= 0.10 and contested_findings_count == 0:
            overall_verdict = "CERTAIN"
        elif overall_confidence >= 0.65 and overall_error_rate <= 0.20:
            overall_verdict = "LIKELY"
        elif overall_confidence >= 0.50 or (contested_findings_count > 0 and contested_findings_count <= 3):
            overall_verdict = "UNCERTAIN"
        elif overall_confidence < 0.50 and overall_error_rate > 0.40:
            overall_verdict = "INCONCLUSIVE"
        else:
            overall_verdict = "REVIEW REQUIRED"

        # Override verdict if strong manipulation signal detected across multiple agents
        manipulation_signals = sum(
            1 for f in all_findings
            if any(kw in str(f.get("finding_type","")).lower() for kw in
                   ("manipulation", "deepfake", "splice", "forgery", "gan", "tamper"))
            and (f.get("calibrated_probability") or f.get("confidence_raw") or 0) >= 0.70
        )
        if manipulation_signals >= 2:
            overall_verdict = "MANIPULATION DETECTED"

        logger.info(
            "Arbiter verdict: %s (confidence=%.2f, error_rate=%.2f, contested=%d, manipulation_signals=%d)",
            overall_verdict, overall_confidence, overall_error_rate,
            contested_findings_count, manipulation_signals,
        )

        # ── Executive summary via Groq — only active agents ───────────────
        await _step("Generating executive summary via Groq…")
        executive_summary = await self._generate_executive_summary(
            len(active_agent_results),
            len(all_findings),
            len(cross_modal_confirmed),
            len(contested_findings),
            all_findings=all_findings,
            gemini_findings=gemini_vision_findings,
            active_agent_metrics=active_metrics,
            overall_verdict=overall_verdict,
        )

        # ── Uncertainty statement ─────────────────────────────────────────
        await _step("Computing uncertainty bounds…")
        uncertainty_statement = await self._generate_uncertainty_statement(
            len(incomplete_findings),
            len(contested_findings),
            overall_error_rate=overall_error_rate,
        )

        # ── Build report ──────────────────────────────────────────────────
        await _step("Finalising court-ready report…")
        report = ForensicReport(
            session_id=self.session_id,
            case_id=case_id or f"case_{self.session_id}",
            executive_summary=executive_summary,
            per_agent_findings=per_agent_findings,
            per_agent_metrics=per_agent_metrics,
            per_agent_analysis=per_agent_analysis,
            overall_confidence=overall_confidence,
            overall_error_rate=overall_error_rate,
            overall_verdict=overall_verdict,
            cross_modal_confirmed=cross_modal_confirmed,
            contested_findings=contested_findings,
            incomplete_findings=incomplete_findings,
            stub_findings=stub_findings,
            gemini_vision_findings=gemini_vision_findings,
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
    
    # ── Agent name map ────────────────────────────────────────────────────
    _AGENT_FULL_NAMES: dict[str, str] = {
        "Agent1": "Image Integrity Agent (ELA · JPEG Ghost · Frequency Domain · Noise Fingerprint)",
        "Agent2": "Audio Forensics Agent (Speaker Diarization · Anti-Spoofing · Codec Fingerprint)",
        "Agent3": "Object Detection Agent (YOLO · Lighting Consistency · Contraband DB)",
        "Agent4": "Video Forensics Agent (Optical Flow · Face-Swap · Rolling Shutter)",
        "Agent5": "Metadata Forensics Agent (EXIF · GPS · Steganography · Hex Signature)",
    }

    async def _generate_agent_narrative(
        self,
        agent_id: str,
        findings: list[dict[str, Any]],
        metrics: dict[str, Any],
    ) -> str:
        """
        Generate a Groq-synthesised per-agent narrative that:
        - Compares initial vs deep analysis findings for this agent
        - Summarises tool successes and failures
        - States the agent's confidence score and error rate
        - Produces 2-3 plain-English paragraphs suitable for the result page

        Returns empty string if LLM is not configured.
        """
        if not (self.config.llm_api_key and self.config.llm_provider != "none"):
            return ""

        client = LLMClient(self.config)
        agent_full_name = self._AGENT_FULL_NAMES.get(agent_id, agent_id)
        confidence_pct  = round(metrics.get("confidence_score", 0) * 100)
        error_rate_pct  = round(metrics.get("error_rate", 0) * 100)
        tools_ok        = metrics.get("tools_succeeded", 0)
        tools_total     = metrics.get("total_tools_called", 0)

        # Split findings by phase
        initial_f = [f for f in findings
                     if (f.get("metadata") or {}).get("analysis_phase", "initial") == "initial"]
        deep_f    = [f for f in findings
                     if (f.get("metadata") or {}).get("analysis_phase") == "deep"]

        _NOT_APPLICABLE_FLAGS = ("ela_not_applicable", "ghost_not_applicable")
        _NOT_APPLICABLE_KEYS = {"ela_not_applicable", "ghost_not_applicable",
                                "ela_limitation_note", "ghost_limitation_note",
                                "file_format_note", "is_camera_format"}
        _STRIP_KEYS = {"stub_warning", "llm_synthesis", "llm_reasoning",
                       "synthesis_phase", "analysis_phase", "tool_name", "warning"}

        def _fmt(findings_list: list[dict]) -> str:
            out = []
            for f in findings_list[:12]:
                meta = f.get("metadata") or {}
                tool_name = meta.get("tool_name", f.get("finding_type", ""))
                is_na = any(meta.get(flag) for flag in _NOT_APPLICABLE_FLAGS)
                is_failed = (
                    not is_na
                    and meta.get("court_defensible") is False
                )
                # Collect the key metrics Groq needs to cite real numbers
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
                    elif isinstance(v, list) and len(v) <= 10 and all(
                        isinstance(x, (str, int, float, bool, dict)) for x in v
                    ):
                        key_metrics[k] = v
                entry = {
                    "tool":            tool_name,
                    "confidence":      round(f.get("confidence_raw", 0), 3),
                    "status":          f.get("status", ""),
                    "applicability":   "NOT_APPLICABLE" if is_na else ("FAILED" if is_failed else "RAN"),
                    "summary":         (f.get("reasoning_summary") or "")[:400],
                    "metrics":         key_metrics,
                }
                out.append(entry)
            return json.dumps(out, indent=2)

        tools_na = metrics.get("tools_not_applicable", 0)
        has_deep = bool(deep_f)
        comparison_section = ""
        if has_deep:
            comparison_section = (
                f"\n\nDeep analysis findings ({len(deep_f)} tool scans):\n{_fmt(deep_f)}"
            )

        system_prompt = f"""You are the Council Arbiter writing the per-agent analysis section of a forensic report.

Write 2-3 clear, plain-English paragraphs for the {agent_full_name}. Structure:

PARAGRAPH 1 — Initial analysis results:
- For each tool with applicability "RAN": cite the EXACT metric values from the "metrics" field and interpret them forensically. Do not paraphrase — state the actual numbers (e.g. "ELA found 3 localised anomaly regions with max deviation 14.2", "YOLO detected person (0.87), laptop (0.76)").
- For each tool with applicability "NOT_APPLICABLE": briefly explain why the tool does not apply to this file type (use the ela_limitation_note / ghost_limitation_note / file_format_note from metrics). Do NOT treat these as suspicious findings.
- For each tool with applicability "FAILED": state that it failed and what data is missing as a result.

PARAGRAPH 2 — Deep analysis and cross-validation (if deep analysis was run):
- What deep tools confirmed, expanded, or contradicted from initial analysis.
- Exact Gemini findings if present: content type, extracted text, detected objects, authenticity verdict.

PARAGRAPH 3 — Reliability and verdict:
- Agent confidence: {confidence_pct}%. Tool error rate: {error_rate_pct}% ({tools_ok} of {tools_total} tools succeeded, {tools_na} not applicable to file type).
- Plain-English verdict for this agent: AUTHENTIC / SUSPICIOUS / INCONCLUSIVE / NOT APPLICABLE.

Do NOT use bullet points. Write in continuous prose. Interpret numbers — do not paste raw JSON."""

        user_content = (
            f"Agent: {agent_full_name}\n"
            f"Confidence: {confidence_pct}%  |  Error rate: {error_rate_pct}%  |  "
            f"Tools succeeded: {tools_ok}/{tools_total}  |  Not applicable: {tools_na}\n\n"
            f"Initial analysis ({len(initial_f)} tool scans):\n{_fmt(initial_f)}"
            f"{comparison_section}\n\n"
            f"Write the per-agent analysis section."
        )

        try:
            return await client.generate_synthesis(
                system_prompt=system_prompt,
                user_content=user_content,
                max_tokens=600,
            )
        except Exception as e:
            logger.warning(f"Per-agent narrative Groq call failed for {agent_id}: {e}")
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

        When Groq is configured (recommended), uses the model to write
        a structured, plain-language summary from actual finding data,
        incorporating Gemini vision insights where available.
        Falls back to a deterministic template if LLM is unavailable.
        """
        if self.config.llm_api_key and self.config.llm_provider != "none":
            try:
                result = await self._llm_executive_summary(
                    num_agents, num_findings, cross_modal_confirmed,
                    contested, all_findings or [], gemini_findings or [],
                    active_agent_metrics or [], overall_verdict,
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
        """Generate executive summary using Groq LLM synthesis.

        Uses ONLY active agents (those that ran real tools).  Incorporates
        per-agent metrics and the computed verdict for a grounded summary.
        """
        client = LLMClient(self.config)

        # Build structured findings digest for the model
        top_findings = sorted(
            [f for f in all_findings if not f.get("stub_result")
             and f.get("metadata", {}).get("analysis_source") != "gemini_vision"],
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

        # Build Gemini vision digest
        gemini_digest = []
        for gf in (gemini_findings or [])[:4]:
            meta = gf.get("metadata", {})
            gemini_digest.append({
                "agent": gf.get("agent_id", "unknown"),
                "analysis_type": meta.get("analysis_type", "vision"),
                "model": meta.get("model_used", "gemini"),
                "confidence": round(gf.get("confidence_raw", 0), 3),
                "summary": gf.get("reasoning_summary", ""),
                "manipulation_signals": meta.get("manipulation_signals", []),
                "detected_objects": meta.get("detected_objects", []),
            })

        gemini_section = ""
        if gemini_digest:
            gemini_section = f"\n\nGemini vision deep analysis findings ({len(gemini_digest)} of {len(gemini_findings or [])}):\n{json.dumps(gemini_digest, indent=2)}"

        metrics_summary = ""
        if active_agent_metrics:
            metrics_summary = "\n\nAgent performance metrics (active agents only):\n" + json.dumps([
                {
                    "agent":           m.get("agent_name", m.get("agent_id","")),
                    "confidence":      f"{m.get('confidence_score',0)*100:.0f}%",
                    "error_rate":      f"{m.get('error_rate',0)*100:.0f}%",
                    "tools_ran":       m.get("tools_succeeded", 0),
                    "tools_failed":    m.get("tools_failed", 0),
                    "not_applicable":  m.get("tools_not_applicable", 0),
                    "total_tools":     m.get("total_tools_called", 0),
                    "findings":        m.get("finding_count", 0),
                }
                for m in active_agent_metrics if not m.get("skipped")
            ], indent=2)

        verdict_line = f"\n\nCouncil Arbiter computed verdict: {overall_verdict}" if overall_verdict else ""

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
    
    async def _generate_uncertainty_statement(
        self, incomplete: int, contested: int, overall_error_rate: float = 0.0
    ) -> str:
        """
        Generate the uncertainty and limitations statement.

        Uses LLM to produce a nuanced, legally-aware statement when configured.
        Falls back to deterministic template otherwise.
        """
        if self.config.llm_api_key and self.config.llm_provider != "none" and (incomplete > 0 or contested > 0 or overall_error_rate > 0.15):
            try:
                result = await self._llm_uncertainty_statement(incomplete, contested, overall_error_rate)
                if result:
                    return result
            except Exception as exc:
                logger.warning(f"LLM uncertainty statement failed, using template: {exc}")

        return self._template_uncertainty_statement(incomplete, contested, overall_error_rate)

    async def _llm_uncertainty_statement(
        self, incomplete: int, contested: int, overall_error_rate: float = 0.0
    ) -> str:
        """Generate uncertainty statement using LLM."""
        client = LLMClient(self.config)

        system_prompt = """You are the Council Arbiter writing the Limitations and Uncertainty section of a forensic report.

Be specific and legally precise. Explain what the uncertainties mean for the evidential value of the report.
Write 2-3 sentences only. Do not use bullet points."""

        user_content = (
            f"Incomplete findings (tools unavailable or evidence insufficient): {incomplete}\n"
            f"Contested findings (agents disagree, not yet resolved): {contested}\n"
            f"Overall tool error rate across active agents: {overall_error_rate*100:.1f}%\n\n"
            "Write the uncertainty and limitations statement."
        )

        return await client.generate_synthesis(
            system_prompt=system_prompt,
            user_content=user_content,
            max_tokens=200,
        )

    def _template_uncertainty_statement(
        self, incomplete: int, contested: int, overall_error_rate: float = 0.0
    ) -> str:
        """Deterministic uncertainty template fallback."""
        statements = []
        if overall_error_rate > 0.15:
            statements.append(
                f"Average tool error rate across active agents is {overall_error_rate*100:.0f}%, "
                "indicating some analysis dimensions may be incomplete or unreliable."
            )
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

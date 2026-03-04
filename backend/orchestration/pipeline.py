"""
Forensic Council Pipeline
=========================

End-to-end orchestration pipeline for forensic evidence analysis.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID, uuid4

from core.config import Settings, get_settings
from core.custody_logger import CustodyLogger, EntryType
from core.episodic_memory import EpisodicMemory
from core.evidence import EvidenceArtifact
from core.inter_agent_bus import InterAgentBus
from core.logging import get_logger
from core.react_loop import HumanDecision
from core.working_memory import WorkingMemory
from infra.evidence_store import EvidenceStore

from agents.agent1_image import Agent1Image
from agents.agent2_audio import Agent2Audio
from agents.agent3_object import Agent3Object
from agents.agent4_video import Agent4Video
from agents.agent5_metadata import Agent5Metadata
from agents.arbiter import CouncilArbiter, ForensicReport

from orchestration.session_manager import SessionManager, SessionStatus

logger = get_logger(__name__)


class AgentFactory:
    """
    Factory for creating and re-invoking forensic agents.
    
    Provides a clean interface for the Arbiter to re-invoke agents
    during challenge loops without needing direct knowledge of agent
    instantiation details.
    """
    
    def __init__(
        self,
        config: Settings,
        working_memory: WorkingMemory,
        episodic_memory: EpisodicMemory,
        custody_logger: CustodyLogger,
        evidence_store: EvidenceStore,
        inter_agent_bus: Optional[InterAgentBus] = None,
    ):
        self.config = config
        self.working_memory = working_memory
        self.episodic_memory = episodic_memory
        self.custody_logger = custody_logger
        self.evidence_store = evidence_store
        self.inter_agent_bus = inter_agent_bus
        self._evidence_artifact: Optional[EvidenceArtifact] = None
    
    def set_evidence_artifact(self, artifact: EvidenceArtifact) -> None:
        """Set the evidence artifact for agent re-invocation."""
        self._evidence_artifact = artifact
    
    async def reinvoke_agent(
        self,
        agent_id: str,
        session_id: UUID,
        challenge_context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Re-invoke an agent with challenge context.
        
        Args:
            agent_id: ID of the agent to re-invoke (Agent1-5)
            session_id: Session ID for the investigation
            challenge_context: Context from the contradicting finding
            
        Returns:
            Agent results including findings and reflection report
        """
        if self._evidence_artifact is None:
            raise ValueError("Evidence artifact not set - call set_evidence_artifact first")
        
        logger.info(
            "Re-invoking agent for challenge loop",
            agent_id=agent_id,
            session_id=str(session_id),
            challenge_id=challenge_context.get("challenge_id"),
        )
        
        # Create the appropriate agent class
        agent_class = self._get_agent_class(agent_id)
        
        # Build agent kwargs
        agent_kwargs = {
            "agent_id": agent_id,
            "session_id": session_id,
            "evidence_artifact": self._evidence_artifact,
            "config": self.config,
            "working_memory": self.working_memory,
            "episodic_memory": self.episodic_memory,
            "custody_logger": self.custody_logger,
            "evidence_store": self.evidence_store,
        }
        
        # Add inter_agent_bus for Agent2, Agent3, and Agent4
        if agent_id in ("Agent2", "Agent3", "Agent4") and self.inter_agent_bus:
            agent_kwargs["inter_agent_bus"] = self.inter_agent_bus
        
        # Create and run the agent
        agent = agent_class(**agent_kwargs)
        
        # Run investigation
        findings = await agent.run_investigation()
        
        # Return results in expected format
        return {
            "agent_id": agent_id,
            "findings": [f.model_dump() for f in findings],
            "reflection_report": (
                agent._reflection_report.model_dump()
                if hasattr(agent, '_reflection_report') and agent._reflection_report
                else {}
            ),
            "react_chain": getattr(agent, '_react_chain', []),
            "challenge_context": challenge_context,
        }
    
    def _get_agent_class(self, agent_id: str) -> type:
        """Get the agent class for a given agent ID."""
        agent_map = {
            "Agent1": Agent1Image,
            "Agent2": Agent2Audio,
            "Agent3": Agent3Object,
            "Agent4": Agent4Video,
            "Agent5": Agent5Metadata,
        }
        
        if agent_id not in agent_map:
            raise ValueError(f"Unknown agent_id: {agent_id}")
        
        return agent_map[agent_id]


class AgentLoopResult:
    """Result from running an agent's investigation loop."""
    def __init__(
        self,
        agent_id: str,
        findings: list[dict[str, Any]],
        reflection_report: dict[str, Any],
        react_chain: list[dict[str, Any]],
        error: Optional[str] = None,
    ):
        self.agent_id = agent_id
        self.findings = findings
        self.reflection_report = reflection_report
        self.react_chain = react_chain
        self.error = error


class ForensicCouncilPipeline:
    """
    End-to-end pipeline for forensic evidence analysis.
    
    Orchestrates:
    - Evidence ingestion and artifact creation
    - Multi-agent investigation (5 specialist agents)
    - Council arbiter deliberation
    - Report generation with cryptographic signing
    """
    
    def __init__(self, config: Optional[Settings] = None):
        """
        Initialize the pipeline with all required components.
        
        Args:
            config: Application settings. If not provided, loads from environment.
        """
        self.config = config or get_settings()
        
        # Initialize infrastructure
        self._setup_infrastructure()
        
        # Initialize components
        self.custody_logger: Optional[CustodyLogger] = None
        self.working_memory: Optional[WorkingMemory] = None
        self.episodic_memory: Optional[EpisodicMemory] = None
        self.inter_agent_bus: Optional[InterAgentBus] = None
        self.evidence_store: Optional[EvidenceStore] = None
        self.session_manager: Optional[SessionManager] = None
        self.arbiter: Optional[CouncilArbiter] = None
    
    def _setup_infrastructure(self) -> None:
        """Set up infrastructure connections."""
        from infra.redis_client import RedisClient
        
        self._redis = None
        self._qdrant = None
        self._postgres = None
        
        try:
            self._redis = RedisClient(
                host=self.config.redis_host,
                port=self.config.redis_port,
                db=self.config.redis_db,
                password=self.config.redis_password,
            )
        except Exception as e:
            logger.warning("Failed to connect to Redis", error=str(e))
    
    async def _initialize_components(self, session_id: UUID) -> None:
        """Initialize all components for a session."""
        from infra.qdrant_client import get_qdrant_client
        from infra.postgres_client import get_postgres_client
        
        if self._redis is not None and getattr(self._redis, '_client', None) is None:
            try:
                await self._redis.connect()
            except Exception as e:
                logger.warning("Failed to connect to Redis", error=str(e))
        
        if self._qdrant is None:
            try:
                self._qdrant = await get_qdrant_client()
            except Exception as e:
                logger.warning("Failed to connect to Qdrant", error=str(e))
                self._qdrant = None

        if self._postgres is None:
            try:
                self._postgres = await get_postgres_client()
            except Exception as e:
                logger.warning("Failed to connect to PostgreSQL", error=str(e))
                self._postgres = None
                
        # Initialize custody logger
        self.custody_logger = CustodyLogger(
            postgres_client=self._postgres,
        )
        
        from infra.storage import LocalStorageBackend
        from infra.evidence_store import EvidenceStore
        
        if self.evidence_store is None:
            self.evidence_store = EvidenceStore(
                postgres_client=self._postgres,
                storage_backend=LocalStorageBackend(storage_path=str(self.config.evidence_storage_path)),
                custody_logger=self.custody_logger,
            )
            
        # Initialize working memory
        self.working_memory = WorkingMemory(
            redis_client=self._redis,
            custody_logger=self.custody_logger,
        )
        
        # Initialize episodic memory
        self.episodic_memory = EpisodicMemory(
            qdrant_client=self._qdrant,
            custody_logger=self.custody_logger,
        )
        
        # Initialize inter-agent bus
        self.inter_agent_bus = InterAgentBus()
        
        # Initialize session manager
        self.session_manager = SessionManager(redis_client=self._redis)
        
        # Initialize agent factory for challenge loops
        self.agent_factory = AgentFactory(
            config=self.config,
            working_memory=self.working_memory,
            episodic_memory=self.episodic_memory,
            custody_logger=self.custody_logger,
            evidence_store=self.evidence_store,
            inter_agent_bus=self.inter_agent_bus,
        )
        
        # Initialize arbiter with agent factory
        self.arbiter = CouncilArbiter(
            session_id=session_id,
            custody_logger=self.custody_logger,
            inter_agent_bus=self.inter_agent_bus,
            agent_factory=self.agent_factory,
        )
    
    async def run_investigation(
        self,
        evidence_file_path: str,
        case_id: str,
        investigator_id: str,
    ) -> ForensicReport:
        """
        Run a complete forensic investigation on evidence.
        
        Steps:
        1. Ingest evidence → EvidenceArtifact (with hash)
        2. Create session_id UUID
        3. Instantiate all 5 agents with shared evidence artifact and session
        4. Run agents concurrently (asyncio.gather) — each runs full ReAct loop
        5. Collect all AgentLoopResults
        6. Pass to CouncilArbiter.deliberate()
        7. Return signed ForensicReport
        
        Args:
            evidence_file_path: Path to the evidence file
            case_id: Case identifier
            investigator_id: ID of the investigator running this analysis
            
        Returns:
            Signed ForensicReport with all findings
        """
        logger.info(
            "Starting forensic investigation",
            case_id=case_id,
            investigator_id=investigator_id,
            evidence_path=evidence_file_path,
        )
        
        # Step 1 & 2: Create session and ingest evidence
        session_id = uuid4()
        self._case_id = case_id
        self._started_at = datetime.now(timezone.utc).isoformat()
        
        await self._initialize_components(session_id)
        
        # Create evidence artifact
        evidence_artifact = await self._ingest_evidence(
            evidence_file_path,
            session_id,
            investigator_id,
        )
        
        # Set evidence artifact in agent factory for challenge loops
        if hasattr(self, 'agent_factory'):
            self.agent_factory.set_evidence_artifact(evidence_artifact)
        
        # Set evidence artifact in inter-agent bus for on-demand agent creation
        if hasattr(self, 'inter_agent_bus'):
            self.inter_agent_bus._evidence_artifact = evidence_artifact
            self.inter_agent_bus._session_id = session_id
        
        # Create session in manager
        await self.session_manager.create_session(
            session_id=session_id,
            case_id=case_id,
            investigator_id=investigator_id,
            agent_ids=["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"],
        )
        
        # Step 3 & 4: Instantiate and run all agents concurrently
        agent_results = await self._run_agents_concurrent(
            evidence_artifact=evidence_artifact,
            session_id=session_id,
        )
        
        # Step 5: Mark all agents as completed
        for aid in ["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"]:
            await self.session_manager.update_agent_status(
                session_id=session_id,
                agent_id=aid,
                status=SessionStatus.COMPLETED,
            )
        
        # Step 6: Run arbiter deliberation
        logger.info("Running council arbiter deliberation")
        
        # Build agent results dict for arbiter
        arbiter_results = {}
        for result in agent_results:
            if result.error is None:
                arbiter_results[result.agent_id] = {
                    "findings": result.findings,
                    "reflection_report": result.reflection_report,
                    "react_chain": result.react_chain,
                }
        
        # Run deliberation
        report = await self.arbiter.deliberate(arbiter_results)
        
        # Add additional fields to report
        report.case_linking_flags = await self._collect_case_linking_flags(
            session_id, evidence_artifact
        )
        report.chain_of_custody_log = await self._get_custody_log(session_id)
        report.evidence_version_trees = await self._get_version_trees(
            evidence_artifact.artifact_id
        )
        report.react_chains = {
            r.agent_id: r.react_chain for r in agent_results if r.error is None
        }
        report.self_reflection_outputs = {
            r.agent_id: r.reflection_report for r in agent_results if r.error is None
        }
        
        # Resign report after adding all fields
        report = await self.arbiter.sign_report(report)
        
        # Step 7: Return signed report
        await self.session_manager.set_final_report(
            session_id=session_id,
            report_id=report.report_id,
        )
        
        # Log completion
        if self.custody_logger:
            await self.custody_logger.log_entry(
                entry_type=EntryType.REPORT_SIGNED,
                agent_id="Arbiter",
                session_id=session_id,
                content={
                    "report_id": str(report.report_id),
                    "total_findings": sum(len(f) for f in report.per_agent_findings.values()),
                },
            )
        
        logger.info(
            "Investigation complete",
            report_id=str(report.report_id),
            session_id=str(session_id),
        )
        
        return report
    
    async def _ingest_evidence(
        self,
        file_path: str,
        session_id: UUID,
        investigator_id: str,
    ) -> EvidenceArtifact:
        """Ingest evidence file and create artifact."""
        file_path_obj = Path(file_path)
        
        # Store in evidence store
        stored_artifact = await self.evidence_store.ingest(
            file_path=file_path,
            session_id=session_id,
            agent_id=investigator_id,
            metadata={
                "mime_type": self._get_mime_type(file_path),
                "original_filename": file_path_obj.name,
            }
        )
        
        return stored_artifact
    
    async def _run_agents_concurrent(
        self,
        evidence_artifact: EvidenceArtifact,
        session_id: UUID,
    ) -> list[AgentLoopResult]:
        """Run all 5 specialist agents concurrently."""
        
        async def run_agent1() -> AgentLoopResult:
            try:
                agent = Agent1Image(
                    agent_id="Agent1",
                    session_id=session_id,
                    evidence_artifact=evidence_artifact,
                    config=self.config,
                    working_memory=self.working_memory,
                    episodic_memory=self.episodic_memory,
                    custody_logger=self.custody_logger,
                    evidence_store=self.evidence_store,
                )
                findings = await agent.run_investigation()
                return AgentLoopResult(
                    agent_id="Agent1",
                    findings=[f.model_dump() for f in findings],
                    # Safely access attributes with getattr in case the agent crashed mid-initialization
                    reflection_report=getattr(agent, '_reflection_report', None).model_dump() if getattr(agent, '_reflection_report', None) else {},
                    react_chain=getattr(agent, '_react_chain', []),
                )
            except Exception as e:
                logger.error("Agent1 failed", error=str(e))
                return AgentLoopResult(agent_id="Agent1", findings=[], reflection_report={}, react_chain=[], error=str(e))
        
        async def run_agent2() -> AgentLoopResult:
            try:
                agent = Agent2Audio(
                    agent_id="Agent2",
                    session_id=session_id,
                    evidence_artifact=evidence_artifact,
                    config=self.config,
                    working_memory=self.working_memory,
                    episodic_memory=self.episodic_memory,
                    custody_logger=self.custody_logger,
                    evidence_store=self.evidence_store,
                    inter_agent_bus=self.inter_agent_bus,
                )
                findings = await agent.run_investigation()
                return AgentLoopResult(
                    agent_id="Agent2",
                    findings=[f.model_dump() for f in findings],
                    # Safely access attributes with getattr in case the agent crashed mid-initialization
                    reflection_report=getattr(agent, '_reflection_report', None).model_dump() if getattr(agent, '_reflection_report', None) else {},
                    react_chain=getattr(agent, '_react_chain', []),
                )
            except Exception as e:
                logger.error("Agent2 failed", error=str(e))
                return AgentLoopResult(agent_id="Agent2", findings=[], reflection_report={}, react_chain=[], error=str(e))
        
        async def run_agent3() -> AgentLoopResult:
            try:
                agent = Agent3Object(
                    agent_id="Agent3",
                    session_id=session_id,
                    evidence_artifact=evidence_artifact,
                    config=self.config,
                    working_memory=self.working_memory,
                    episodic_memory=self.episodic_memory,
                    custody_logger=self.custody_logger,
                    evidence_store=self.evidence_store,
                    inter_agent_bus=self.inter_agent_bus,
                )
                findings = await agent.run_investigation()
                return AgentLoopResult(
                    agent_id="Agent3",
                    findings=[f.model_dump() for f in findings],
                    # Safely access attributes with getattr in case the agent crashed mid-initialization
                    reflection_report=getattr(agent, '_reflection_report', None).model_dump() if getattr(agent, '_reflection_report', None) else {},
                    react_chain=getattr(agent, '_react_chain', []),
                )
            except Exception as e:
                logger.error("Agent3 failed", error=str(e))
                return AgentLoopResult(agent_id="Agent3", findings=[], reflection_report={}, react_chain=[], error=str(e))
        
        async def run_agent4() -> AgentLoopResult:
            try:
                agent = Agent4Video(
                    agent_id="Agent4",
                    session_id=session_id,
                    evidence_artifact=evidence_artifact,
                    config=self.config,
                    working_memory=self.working_memory,
                    episodic_memory=self.episodic_memory,
                    custody_logger=self.custody_logger,
                    evidence_store=self.evidence_store,
                    inter_agent_bus=self.inter_agent_bus,
                )
                findings = await agent.run_investigation()
                return AgentLoopResult(
                    agent_id="Agent4",
                    findings=[f.model_dump() for f in findings],
                    # Safely access attributes with getattr in case the agent crashed mid-initialization
                    reflection_report=getattr(agent, '_reflection_report', None).model_dump() if getattr(agent, '_reflection_report', None) else {},
                    react_chain=getattr(agent, '_react_chain', []),
                )
            except Exception as e:
                logger.error("Agent4 failed", error=str(e))
                return AgentLoopResult(agent_id="Agent4", findings=[], reflection_report={}, react_chain=[], error=str(e))
        
        async def run_agent5() -> AgentLoopResult:
            try:
                agent = Agent5Metadata(
                    agent_id="Agent5",
                    session_id=session_id,
                    evidence_artifact=evidence_artifact,
                    config=self.config,
                    working_memory=self.working_memory,
                    episodic_memory=self.episodic_memory,
                    custody_logger=self.custody_logger,
                    evidence_store=self.evidence_store,
                )
                findings = await agent.run_investigation()
                return AgentLoopResult(
                    agent_id="Agent5",
                    findings=[f.model_dump() for f in findings],
                    # Safely access attributes with getattr in case the agent crashed mid-initialization
                    reflection_report=getattr(agent, '_reflection_report', None).model_dump() if getattr(agent, '_reflection_report', None) else {},
                    react_chain=getattr(agent, '_react_chain', []),
                )
            except Exception as e:
                logger.error("Agent5 failed", error=str(e))
                return AgentLoopResult(agent_id="Agent5", findings=[], reflection_report={}, react_chain=[], error=str(e))
        
        # Run all agents concurrently
        results = await asyncio.gather(run_agent1(), run_agent2(), run_agent3(), run_agent4(), run_agent5())
        return list(results)
    
    async def handle_hitl_decision(
        self,
        session_id: UUID,
        checkpoint_id: UUID,
        decision: HumanDecision,
    ) -> None:
        """
        Route human decision to correct agent's loop engine.
        
        Args:
            session_id: Session ID
            checkpoint_id: Checkpoint ID requiring human decision
            decision: Human decision (approve, reject, modify)
        """
        logger.info(
            "Handling HITL decision",
            session_id=str(session_id),
            checkpoint_id=str(checkpoint_id),
            decision=decision.decision_type,
        )
        
        # Get checkpoint info
        checkpoints = await self.session_manager.get_active_checkpoints(session_id)
        checkpoint = next((cp for cp in checkpoints if cp.checkpoint_id == checkpoint_id), None)
        
        if not checkpoint:
            raise ValueError(f"Checkpoint {checkpoint_id} not found")
        
        # Resolve in session manager
        await self.session_manager.resolve_checkpoint(
            checkpoint_id=checkpoint_id,
            decision={
                "status": decision.decision_type,
                "notes": decision.notes,
                "modified_content": decision.override_finding,
            },
        )
        
        # Log the decision
        if self.custody_logger:
            await self.custody_logger.log_entry(
                entry_type=EntryType.HITL_DECISION,
                agent_id=checkpoint.agent_id,
                session_id=session_id,
                content={
                    "checkpoint_id": str(checkpoint_id),
                    "decision": decision.decision_type,
                    "notes": decision.notes,
                },
            )
    
    async def _collect_case_linking_flags(
        self,
        session_id: UUID,
        evidence_artifact: EvidenceArtifact,
    ) -> list[dict[str, Any]]:
        """Collect case linking flags from episodic memory."""
        flags = []
        
        try:
            entries = await self.episodic_memory.get_by_session(session_id)
            for entry in entries:
                if entry.signature_type and "LINK" in entry.signature_type.value:
                    flags.append({
                        "flag_type": entry.signature_type.value,
                        "description": entry.description,
                        "artifact_id": str(entry.artifact_id),
                    })
        except Exception as e:
            logger.warning("Failed to collect case linking flags", error=str(e))
        
        return flags
    
    async def _get_custody_log(self, session_id: UUID) -> list[dict[str, Any]]:
        """Get chain of custody log for session."""
        try:
            chain = await self.custody_logger.get_session_chain(session_id)
            return [
                {
                    "entry_id": str(e.entry_id),
                    "entry_type": e.entry_type.value,
                    "agent_id": e.agent_id,
                    "timestamp_utc": e.timestamp_utc.isoformat(),
                    "content_hash": e.content_hash,
                }
                for e in chain
            ]
        except Exception as e:
            logger.warning("Failed to get custody log", error=str(e))
            return []
    
    async def _get_version_trees(
        self,
        artifact_id: UUID,
    ) -> list[dict[str, Any]]:
        """Get evidence version trees."""
        try:
            tree = await self.evidence_store.get_version_tree(artifact_id)
            if not tree:
                return []
            
            versions = tree.get_all_artifacts()
            return [
                {
                    "artifact_id": str(v.artifact_id),
                    "parent_id": str(v.parent_id) if v.parent_id else None,
                    "content_hash": v.content_hash,
                    "created_at": v.timestamp_utc.isoformat(),
                }
                for v in versions
            ]
        except Exception as e:
            logger.warning("Failed to get version trees", error=str(e))
            return []
    
    def _get_mime_type(self, file_path: str) -> str:
        """Get MIME type from file extension."""
        ext = Path(file_path).suffix.lower()
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".tiff": "image/tiff",
            ".webp": "image/webp",
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".flac": "audio/flac",
            ".mp4": "video/mp4",
            ".avi": "video/x-msvideo",
            ".mov": "video/quicktime",
            ".mkv": "video/x-matroska",
            ".pdf": "application/pdf",
        }
        return mime_types.get(ext, "application/octet-stream")

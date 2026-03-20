"""
ForensicAgent Base Class and Self-Reflection System.

Every specialist agent (1-5) extends this base class.
Provides common investigation workflow, self-reflection, and memory integration.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from core.config import Settings
from core.custody_logger import CustodyLogger, EntryType
from core.episodic_memory import EpisodicMemory, EpisodicEntry, ForensicSignatureType
from core.evidence import EvidenceArtifact
from core.inter_agent_bus import InterAgentCall, InterAgentCallType
from core.llm_client import LLMClient
from core.logging import get_logger
from core.react_loop import (
    AgentFinding,
    HITLCheckpointReason,
    HumanDecision,
    ReActLoopEngine,
    ReActLoopResult,
    create_llm_step_generator,
)
from core.tool_registry import ToolRegistry
from core.working_memory import WorkingMemory, WorkingMemoryState, Task, TaskStatus
from infra.evidence_store import EvidenceStore

logger = get_logger(__name__)


class SelfReflectionReport(BaseModel):
    """
    Report from self-reflection pass.
    
    Generated after each investigation to ensure quality and completeness.
    """
    all_tasks_complete: bool = Field(
        default=False,
        description="Whether all tasks in decomposition are complete"
    )
    incomplete_tasks: list[str] = Field(
        default_factory=list,
        description="List of incomplete task descriptions"
    )
    overconfident_findings: list[str] = Field(
        default_factory=list,
        description="Findings that may have inflated confidence"
    )
    untreated_absences: list[str] = Field(
        default_factory=list,
        description="Absence of expected data that wasn't analyzed"
    )
    deprioritized_avenues: list[str] = Field(
        default_factory=list,
        description="Investigation avenues that were deprioritized"
    )
    court_defensible: bool = Field(
        default=False,
        description="Whether findings are defensible in court"
    )
    reflection_notes: str = Field(
        default="",
        description="Additional notes from reflection"
    )



def _attach_llm_reasoning_to_findings(
    findings: list,
    react_chain: list,
) -> list:
    """
    Attach LLM THOUGHT reasoning to the AgentFinding that followed it.

    When the LLM drives the ReAct loop, each ACTION step is typically
    preceded by a THOUGHT step containing the LLM's interpretation of
    previous observations and its reasoning for choosing the next tool.

    This function matches each finding (created from a tool ACTION+OBSERVATION)
    to the THOUGHT step that immediately preceded that ACTION in the chain, and
    stores the LLM reasoning text in finding.metadata["llm_reasoning"].

    It also scans THOUGHT steps for explicit anomaly language and appends
    those insights to finding.reasoning_summary so they appear in the
    per-agent report cards.

    Args:
        findings: List of AgentFinding objects from the loop
        react_chain: Full list of ReActStep objects from the loop

    Returns:
        The same findings list with llm_reasoning populated where available
    """
    if not findings or not react_chain:
        return findings

    # Build index: tool_name -> list of THOUGHT contents that preceded it
    # Walk the chain and collect (thought_content, action_tool_name) pairs
    thought_before_action: list[tuple[str, str]] = []
    prev_thought = ""
    for step in react_chain:
        stype = step.step_type if hasattr(step, "step_type") else step.get("step_type", "")
        if stype == "THOUGHT":
            content = step.content if hasattr(step, "content") else step.get("content", "")
            prev_thought = content
        elif stype == "ACTION" and prev_thought:
            tool = step.tool_name if hasattr(step, "tool_name") else step.get("tool_name", "")
            if tool:
                thought_before_action.append((prev_thought, tool))
            prev_thought = ""

    # Map tool_name -> list of reasoning snippets (in order of occurrence)
    tool_reasoning: dict[str, list[str]] = {}
    for thought, tool in thought_before_action:
        tool_reasoning.setdefault(tool, []).append(thought)

    # Usage counters so we consume each reasoning entry at most once per finding
    tool_usage: dict[str, int] = {}

    # Anomaly signal words — thoughts containing these are especially important
    _ANOMALY_SIGNALS = (
        "anomal", "manipulat", "inconsisten", "suspicious", "unusual",
        "mismatch", "artifact", "synthetic", "deepfake", "edited",
        "absent", "missing", "unexpected", "flag",
    )

    for finding in findings:
        tool_name = finding.metadata.get("tool_name", "") if hasattr(finding, "metadata") else ""
        if not tool_name:
            continue

        idx = tool_usage.get(tool_name, 0)
        reasoning_list = tool_reasoning.get(tool_name, [])

        if idx < len(reasoning_list):
            thought_text = reasoning_list[idx]
            tool_usage[tool_name] = idx + 1

            # Store full LLM thought in metadata
            if hasattr(finding, "metadata") and isinstance(finding.metadata, dict):
                finding.metadata["llm_reasoning"] = thought_text

            # If the thought contains anomaly language, prepend a note to
            # reasoning_summary so it surfaces in the report card
            thought_lower = thought_text.lower()
            has_anomaly_signal = any(sig in thought_lower for sig in _ANOMALY_SIGNALS)
            if has_anomaly_signal and thought_text.strip():
                # Take the most relevant sentence (the one with the signal word)
                sentences = [s.strip() for s in thought_text.replace("\n", " ").split(".") if s.strip()]
                relevant = [s for s in sentences if any(sig in s.lower() for sig in _ANOMALY_SIGNALS)]
                if relevant:
                    insight = relevant[0][:200]
                    if hasattr(finding, "reasoning_summary"):
                        existing = finding.reasoning_summary or ""
                        if insight not in existing:
                            finding.reasoning_summary = f"[LLM] {insight}. {existing}".strip()

    return findings


class ForensicAgent(ABC):
    """
    Abstract base class for all forensic specialist agents.
    
    Provides:
    - Common investigation workflow via run_investigation()
    - Self-reflection system for quality assurance
    - Integration with working memory, episodic memory, and chain of custody
    - Tool registry management
    
    Subclasses must implement:
    - agent_name property
    - task_decomposition property
    - iteration_ceiling property
    - build_tool_registry() method
    - build_initial_thought() method
    """
    
    def __init__(
        self,
        agent_id: str,
        session_id: uuid.UUID,
        evidence_artifact: EvidenceArtifact,
        config: Settings,
        working_memory: WorkingMemory,
        episodic_memory: EpisodicMemory,
        custody_logger: CustodyLogger,
        evidence_store: EvidenceStore,
        inter_agent_bus: Any = None,
    ) -> None:
        """
        Initialize a forensic agent.
        
        Args:
            agent_id: Unique identifier for this agent instance
            session_id: Session ID for this investigation
            evidence_artifact: The primary evidence artifact to analyze
            config: Application configuration
            working_memory: Working memory for task tracking
            episodic_memory: Episodic memory for forensic signatures
            custody_logger: Chain of custody logger
            evidence_store: Evidence store for artifact management
            inter_agent_bus: Optional bus for inter-agent communication
        """
        self.agent_id = agent_id
        self.session_id = session_id
        self.evidence_artifact = evidence_artifact
        self.config = config
        self.working_memory = working_memory
        self.episodic_memory = episodic_memory
        self.custody_logger = custody_logger
        self.evidence_store = evidence_store
        self.inter_agent_bus = inter_agent_bus
        
        # Will be set during investigation
        self._tool_registry: ToolRegistry | None = None
        self._findings: list[AgentFinding] = []
        self._react_chain: list = []
        self._reflection_report: SelfReflectionReport | None = None

        # Tool context: keyed by tool_name, stores last result dict.
        # Handlers read from this to infer context from prior tool runs.
        self._tool_context: dict[str, Any] = {}

        # Error and success counters for per-agent confidence/error rate.
        self._tool_success_count: int = 0
        self._tool_error_count: int = 0

        # Groq-synthesized agent-level scores (set by _synthesize_findings_with_llm).
        # None until synthesis runs; investigation.py reads these for AGENT_COMPLETE.
        self._agent_confidence: float | None = None
        self._agent_error_rate: float | None = None
    
    # Abstract properties that must be overridden
    
    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Human-readable name of this agent."""
        pass
    
    @property
    @abstractmethod
    def task_decomposition(self) -> list[str]:
        """
        List of tasks this agent performs.
        Hardcoded per agent based on architecture document.
        """
        pass
    
    @property
    def deep_task_decomposition(self) -> list[str]:
        """
        Heavy/slow tasks that run in background after initial findings.
        
        Override in subclasses to define tasks that require ML model
        downloads, heavy CPU inference, or network calls. These run
        as a background pass after the agent returns initial findings.
        Default: empty (no deep pass).
        """
        return []
    
    @property
    @abstractmethod
    def iteration_ceiling(self) -> int:
        """Maximum iterations for the ReAct loop."""
        pass
    
    @property
    def supported_file_types(self) -> list[str]:
        """
        List of MIME type prefixes this agent supports.
        
        Override in subclasses to specify which file types the agent can analyze.
        Examples: ['image/'], ['audio/', 'video/'], ['image/', 'video/']
        Default: ['*'] (all file types - for metadata agent).
        
        Used by the pipeline to filter which agents should run for a given file.
        """
        return ['*']  # Default: support all file types
    
    @property
    def supports_uploaded_file(self) -> bool:
        """
        Check if this agent supports the uploaded evidence file type.
        
        Returns True if any of the agent's supported_file_types match
        the evidence file's MIME type, or if the agent supports all types.
        """
        if '*' in self.supported_file_types:
            return True
        
        mime_type = getattr(self.evidence_artifact, 'mime_type', '') or ''
        file_path = getattr(self.evidence_artifact, 'file_path', '') or ''
        
        # Check MIME type prefix match
        for supported in self.supported_file_types:
            if mime_type.lower().startswith(supported.lower()):
                return True
        
        # Check file extension as fallback
        audio_exts = ('.wav', '.mp3', '.flac', '.ogg', '.aac', '.m4a', '.wma')
        video_exts = ('.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm')
        image_exts = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp')
        
        file_lower = file_path.lower()
        for supported in self.supported_file_types:
            if 'image' in supported.lower():
                if any(file_lower.endswith(ext) for ext in image_exts):
                    return True
            elif 'audio' in supported.lower():
                if any(file_lower.endswith(ext) for ext in audio_exts):
                    return True
            elif 'video' in supported.lower():
                if any(file_lower.endswith(ext) for ext in video_exts):
                    return True
        
        return False
    
    # Abstract methods that must be overridden
    
    @abstractmethod
    async def build_tool_registry(self) -> ToolRegistry:
        """
        Build and return the tool registry for this agent.
        
        Returns:
            ToolRegistry with all tools this agent can use
        """
        pass
    
    @abstractmethod
    async def build_initial_thought(self) -> str:
        """
        Build the initial thought for the ReAct loop.
        
        Returns:
            String containing the opening thought for investigation
        """
        pass
    
    # Concrete methods shared by all agents
    
    async def run_investigation(self) -> list[AgentFinding]:
        """
        Run the full investigation workflow.

        Steps:
        1. Initialize working memory with task_decomposition (unless _skip_memory_init flag set)
        2. Log session start to CustodyLogger
        3. Build tool registry
        4. Check tool availability
        5. Build initial thought
        6. Run ReActLoopEngine
        7. Run self_reflection_pass()
        8. Return findings

        Returns:
            List of AgentFinding objects from the investigation
        """
        logger.info(
            "Starting investigation",
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            session_id=str(self.session_id),
            artifact_id=str(self.evidence_artifact.artifact_id),
        )
        
        # Step 1: Initialize working memory with task decomposition
        # (Skipped when subclass pre-initialized it for file-type validation)
        if not getattr(self, "_skip_memory_init", False):
            await self._initialize_working_memory()
        
        # Step 2: Log session start
        if self.custody_logger:
            await self.custody_logger.log_entry(
                agent_id=self.agent_id,
                session_id=self.session_id,
                entry_type=EntryType.THOUGHT,  # Using THOUGHT as session marker
                content={
                    "action": "session_start",
                    "agent_name": self.agent_name,
                    "evidence_artifact_id": str(self.evidence_artifact.artifact_id),
                    "task_count": len(self.task_decomposition),
                }
            )
        
        # Step 3: Build tool registry
        self._tool_registry = await self.build_tool_registry()

        # Step 3b: Inject live tool catalogue into working memory state so
        # the LLM always sees the actual registered tools (not a static list).
        # Unavailable tools are marked but included — the LLM should know
        # which tools exist even if they cannot be called right now.
        try:
            if self._tool_registry is not None:
                snapshot = [
                    {
                        "name": t.name,
                        "description": t.description,
                        "available": t.available,
                        "parameters": {
                            "type": "object",
                            "properties": {"artifact": {"type": "object", "description": "Evidence artifact to analyse"}},
                            "required": [],
                        },
                    }
                    for t in self._tool_registry.list_tools()
                ]
                await self.working_memory.update_state(
                    session_id=self.session_id,
                    agent_id=self.agent_id,
                    updates={"tool_registry_snapshot": snapshot},
                )
                logger.debug(
                    "Tool registry snapshot injected into working memory",
                    agent_id=self.agent_id,
                    tool_count=len(snapshot),
                    unavailable=[t["name"] for t in snapshot if not t["available"]],
                )
        except Exception as _snap_err:
            logger.warning(f"Could not inject tool registry snapshot: {_snap_err}")

        # Step 4: Check tool availability
        await self._check_tool_availability()
        
        # Step 5: Build initial thought
        initial_thought = await self.build_initial_thought()
        
        # Step 6: Run ReAct loop engine
        loop_engine = ReActLoopEngine(
            agent_id=self.agent_id,
            session_id=self.session_id,
            iteration_ceiling=self.iteration_ceiling,
            working_memory=self.working_memory,
            custody_logger=self.custody_logger,
            redis_client=None,  # HITL handled externally in production
        )
        
        # LLM reasoning in the ReAct loop is DISABLED by default.
        # Agents use the fast task-decomposition driver: iterate through
        # tasks, match each task to a tool, run the tool, collect findings.
        # This completes in ~15-30s instead of 60-180s with LLM.
        #
        # LLM (Groq) is called ONCE after all tools finish to synthesize
        # raw findings into rich forensic narratives (see Step 6b below).
        llm_generator = None
        if self.config.llm_enable_react_reasoning and self.config.llm_api_key:
            llm_client = LLMClient(self.config)
            evidence_context = {
                "mime_type": getattr(self.evidence_artifact, "mime_type", "unknown"),
                "file_name": getattr(self.evidence_artifact, "file_path", "unknown"),
                "file_size_bytes": getattr(self.evidence_artifact, "file_size", ""),
                "sha256": getattr(self.evidence_artifact, "sha256_hash", ""),
            }
            llm_generator = create_llm_step_generator(
                llm_client=llm_client,
                config=self.config,
                agent_name=self.agent_name,
                evidence_context=evidence_context,
            )
            logger.info(
                "LLM reasoning enabled for ReAct loop",
                agent_id=self.agent_id,
                llm_provider=self.config.llm_provider,
                llm_model=self.config.llm_model,
            )
        
        loop_result = await loop_engine.run(
            initial_thought=initial_thought,
            tool_registry=self._tool_registry,
            llm_generator=llm_generator  # None = fast task-decomposition driver
        )
        
        self._findings = loop_result.findings
        self._react_chain = loop_result.react_chain
        self._loop_result = loop_result

        # Step 6b: Post-analysis LLM synthesis.
        # Instead of calling the LLM on every ReAct iteration (slow, rate-limited),
        # we call Groq ONCE after all tools complete to synthesize raw findings
        # into coherent, court-grade forensic narratives.
        if (self.config.llm_enable_post_synthesis 
                and self.config.llm_api_key 
                and self.config.llm_provider != "none"
                and self._findings):
            try:
                await self._synthesize_findings_with_llm()
            except Exception as synth_err:
                logger.warning(
                    "Post-analysis LLM synthesis failed, raw findings preserved",
                    agent_id=self.agent_id,
                    error=str(synth_err),
                )

        # Step 7: Run self-reflection pass
        self._reflection_report = await self.self_reflection_pass(self._findings)
        
        # Step 8: Return findings
        logger.info(
            "Investigation complete",
            agent_id=self.agent_id,
            session_id=str(self.session_id),
            finding_count=len(self._findings),
            all_tasks_complete=self._reflection_report.all_tasks_complete,
        )
        
        return self._findings
    
    async def run_deep_investigation(self) -> list[AgentFinding]:
        """
        Run the deep/heavy investigation pass in background.
        
        Uses a SEPARATE working memory namespace (agent_id + '_deep') so
        deep tasks never bleed into the initial-pass task list.  Ensures the
        tool registry is available (builds it if the initial pass was skipped).
        Returns COMBINED findings from both initial and deep analysis.
        """
        deep_tasks = self.deep_task_decomposition
        if not deep_tasks:
            for f in self._findings:
                if "analysis_phase" not in f.metadata:
                    f.metadata["analysis_phase"] = "initial"
            return self._findings

        logger.info(
            "Starting deep investigation pass",
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            deep_task_count=len(deep_tasks),
            initial_finding_count=len(self._findings),
        )

        # Tag initial findings
        for f in self._findings:
            f.metadata["analysis_phase"] = "initial"

        # Ensure we have a tool registry (agent may not have run initial pass)
        if self._tool_registry is None:
            self._tool_registry = await self.build_tool_registry()

        # ISOLATED namespace for deep pass — avoids re-running initial tasks
        deep_agent_id = f"{self.agent_id}_deep"
        # Store so _record_tool_error can write to both namespaces during deep pass
        self._deep_wm_namespace = deep_agent_id

        await self.working_memory.initialize(
            session_id=self.session_id,
            agent_id=deep_agent_id,
            tasks=deep_tasks,
            iteration_ceiling=len(deep_tasks) + 5,
        )

        loop_engine = ReActLoopEngine(
            agent_id=deep_agent_id,
            session_id=self.session_id,
            iteration_ceiling=len(deep_tasks) + 5,
            working_memory=self.working_memory,
            custody_logger=self.custody_logger,
            redis_client=None,
        )

        # Build a rich initial thought that summarises what initial analysis found
        # so Gemini and other deep tools have full forensic context from the start.
        init_summary_parts = []
        for f in self._findings[:4]:  # top 4 initial findings
            ft = getattr(f, "finding_type", "")
            rs = getattr(f, "reasoning_summary", "") or ""
            conf = getattr(f, "confidence_raw", 0.0)
            if ft and rs:
                init_summary_parts.append(f"{ft} ({conf*100:.0f}%): {rs[:120]}")
        init_context = (
            " | ".join(init_summary_parts)
            if init_summary_parts
            else f"{len(self._findings)} initial finding(s) recorded."
        )

        loop_result = await loop_engine.run(
            initial_thought=(
                f"DEEP ANALYSIS PASS — {self.agent_name}. "
                f"Running {len(deep_tasks)} heavy forensic tools (ML models + Gemini AI vision). "
                f"Initial pass summary: {init_context}. "
                f"Deep tasks to execute: {'; '.join(deep_tasks)}. "
                f"For Gemini analysis: provide complete image understanding — content type, "
                f"all text, objects/weapons, interfaces, what is happening in the image, "
                f"cross-validate with EXIF metadata."
            ),
            tool_registry=self._tool_registry,
            llm_generator=None,
        )

        deep_findings = loop_result.findings

        # Normalize agent_id — strip _deep suffix so frontend groups correctly
        for f in deep_findings:
            if hasattr(f, "agent_id") and f.agent_id == deep_agent_id:
                f.agent_id = self.agent_id

        # Tag deep findings
        for f in deep_findings:
            f.metadata["analysis_phase"] = "deep"

        # Post-synthesis on deep findings — compare against initial findings
        if (
            self.config.llm_enable_post_synthesis
            and self.config.llm_api_key
            and self.config.llm_provider != "none"
            and deep_findings
        ):
            # Temporarily set self._findings to ALL (initial + deep) so the
            # synthesis prompt can reference initial findings for comparison.
            orig_findings = self._findings
            combined_for_synth = orig_findings + deep_findings
            self._findings = combined_for_synth
            try:
                await self._synthesize_findings_with_llm(phase="deep")
                # Extract back only deep findings (they're at the end)
                deep_findings = self._findings[len(orig_findings):]
                for f in deep_findings:
                    f.metadata["analysis_phase"] = "deep"
            except Exception as synth_ex:
                logger.warning(f"Deep synthesis failed, raw findings preserved: {synth_ex}",
                               agent_id=self.agent_id)
            self._findings = orig_findings

        # Store combined for the arbiter (initial + deep) but return ONLY deep
        # findings so the investigation route can show a fresh deep-only card
        # without duplicating the initial-analysis results.
        combined_findings = self._findings + deep_findings
        self._findings = combined_findings

        logger.info(
            "Deep investigation pass complete",
            agent_id=self.agent_id,
            deep_finding_count=len(deep_findings),
            total_finding_count=len(combined_findings),
        )

        # Return only the new deep findings — callers use self._findings for
        # the full combined set when building the arbiter payload.
        return deep_findings
    
    async def _initialize_working_memory(self) -> None:
        """Initialize working memory with task decomposition."""
        await self.working_memory.initialize(
            session_id=self.session_id,
            agent_id=self.agent_id,
            tasks=self.task_decomposition,
            iteration_ceiling=self.iteration_ceiling,
        )
        
        logger.debug(
            "Working memory initialized",
            agent_id=self.agent_id,
            task_count=len(self.task_decomposition),
        )
    
    async def _check_tool_availability(self) -> None:
        """Check and log tool availability."""
        if self._tool_registry is None:
            return
        
        tools = self._tool_registry.list_tools()
        unavailable_tools = [t for t in tools if not t.available]
        
        if unavailable_tools and self.custody_logger:
            await self.custody_logger.log_entry(
                agent_id=self.agent_id,
                session_id=self.session_id,
                entry_type=EntryType.TOOL_CALL,
                content={
                    "action": "tool_availability_check",
                    "unavailable_tools": [t.name for t in unavailable_tools],
                    "total_tools": len(tools),
                    "available_tools": len(tools) - len(unavailable_tools),
                }
            )
            
            logger.warning(
                "Some tools unavailable",
                agent_id=self.agent_id,
                unavailable=[t.name for t in unavailable_tools],
            )
    
    async def _record_tool_result(self, tool_name: str, result: dict) -> None:
        """
        Store a successful tool result in _tool_context and increment success counter.

        Call this in every handler after a non-error result so that subsequent
        handlers can read it for context inference.
        """
        self._tool_context[tool_name] = result
        self._tool_success_count += 1

    async def _record_tool_error(self, tool_name: str, error_msg: str) -> None:
        """
        Increment error counter and write last_tool_error to working memory
        so the heartbeat can broadcast a live ⚠️ progress update.

        Call this in handlers when a tool returns an error or is unavailable.
        """
        self._tool_error_count += 1
        display_name = tool_name.replace("_", " ").title()
        error_text = f"{display_name} failed — continuing…"
        try:
            await self.working_memory.update_state(
                session_id=self.session_id,
                agent_id=self.agent_id,
                updates={"last_tool_error": error_text},
            )
            # Also write to deep namespace so heartbeat surfaces errors during deep pass
            deep_ns = getattr(self, "_deep_wm_namespace", None)
            if deep_ns:
                await self.working_memory.update_state(
                    session_id=self.session_id,
                    agent_id=deep_ns,
                    updates={"last_tool_error": error_text},
                )
        except Exception:
            pass  # Never block the investigation on a bookkeeping failure

    async def _synthesize_findings_with_llm(self, phase: str = "initial") -> None:
        """
        Post-analysis Groq synthesis — grouped, structured, with agent confidence + error rate.

        Tools are batched into forensic groups (e.g. "Pixel-Level Integrity", "Temporal
        Edit Detection").  Groq returns a structured JSON object with:
          - verdict / confidence / error_rate at the agent level
          - per-section analysis paragraphs citing exact metric values
          - flag (ok/warn/bad/info) per section for frontend colour-coding
          - critical_findings list and court_notes

        Results are applied back to each finding:
          - reasoning_summary  ← section analysis prose
          - metadata.section_*  ← section id, label, flag, key_signal
          - metadata.agent_confidence / agent_error_rate stored on every finding
        self._agent_confidence and self._agent_error_rate are also set so
        investigation.py can broadcast them in AGENT_COMPLETE.

        Phase "deep" receives initial findings as comparison context and expects
        CONFIRMED / EXPANDED / CONTRADICTED verdicts in the analysis.

        This method must NEVER raise — raw findings are always preserved on failure.
        """
        import json as _json

        if not self._findings:
            return

        llm_client = LLMClient(self.config)

        evidence_context = {
            "mime_type": getattr(self.evidence_artifact, "mime_type", "unknown"),
            "file_name": getattr(self.evidence_artifact, "file_path", "unknown"),
        }

        # ── Per-agent tool groups ─────────────────────────────────────────────
        # Corroborating tools are batched together so Groq produces one coherent
        # paragraph per group instead of isolated per-tool sentences.
        # The agent_key strips the "_deep" suffix so deep-pass agents reuse the
        # same grouping as their initial-pass counterpart.
        agent_key = self.agent_id.replace("_deep", "")

        _TOOL_GROUPS: dict[str, list[dict]] = {
            "Agent1": [
                {
                    "id": "pixel_integrity",
                    "label": "Pixel-Level Integrity",
                    "tools": ["ela_full_image", "ela_anomaly_classify",
                              "jpeg_ghost_detect", "noise_fingerprint"],
                    "desc": "Compression-artifact and noise-consistency checks — primary manipulation signal for JPEG images.",
                },
                {
                    "id": "spectral",
                    "label": "Spectral & GAN Analysis",
                    "tools": ["frequency_domain_analysis", "deepfake_frequency_check"],
                    "desc": "FFT-based analysis for GAN generation artifacts and frequency-domain anomalies.",
                },
                {
                    "id": "structural",
                    "label": "Structural Manipulation",
                    "tools": ["copy_move_detect", "splicing_detect"],
                    "desc": "Copy-move and splice detection — regions cloned from within or outside the image.",
                },
                {
                    "id": "chain_of_custody",
                    "label": "Chain of Custody",
                    "tools": ["file_hash_verify", "adversarial_robustness_check"],
                    "desc": "File integrity since ingestion and anti-forensics evasion robustness.",
                },
                {
                    "id": "content",
                    "label": "Content Analysis",
                    "tools": ["analyze_image_content", "extract_text_from_image",
                              "extract_evidence_text"],
                    "desc": "Semantic image classification and OCR text extraction.",
                },
                {
                    "id": "deep_validation",
                    "label": "Deep-Pass Validation",
                    "tools": ["gemini_deep_forensic", "prnu_analysis",
                              "cfa_demosaicing", "sensor_db_query"],
                    "desc": "Gemini AI vision, PRNU sensor fingerprint, and CFA Bayer-pattern consistency.",
                },
            ],
            "Agent2": [
                {
                    "id": "voice_authenticity",
                    "label": "Voice Authenticity",
                    "tools": ["anti_spoofing_detect", "voice_clone_detect"],
                    "desc": "Synthetic/AI voice detection via anti-spoofing model and voice-clone heuristics.",
                },
                {
                    "id": "prosody",
                    "label": "Prosodic Analysis",
                    "tools": ["prosody_analyze", "prosody_analysis"],
                    "desc": "Fundamental frequency, jitter, shimmer, and HNR acoustic profile.",
                },
                {
                    "id": "edit_detection",
                    "label": "Temporal Edit Detection",
                    "tools": ["audio_splice_detect", "enf_analysis",
                              "background_noise_analysis"],
                    "desc": "Splice via signal continuity, ENF electrical-hum analysis, and ambient noise consistency — triple-corroboration of edit points.",
                },
                {
                    "id": "technical_provenance",
                    "label": "Technical Provenance",
                    "tools": ["codec_fingerprinting", "audio_visual_sync"],
                    "desc": "Codec chain re-encoding history and audio-visual lip-sync alignment.",
                },
                {
                    "id": "speaker_map",
                    "label": "Speaker Map",
                    "tools": ["speaker_diarize", "speaker_diarization"],
                    "desc": "Speaker count and segment timeline baseline.",
                },
            ],
            "Agent3": [
                {
                    "id": "object_inventory",
                    "label": "Object Inventory",
                    "tools": ["object_detection", "secondary_classification"],
                    "desc": "YOLO primary detection refined by CLIP zero-shot secondary classification.",
                },
                {
                    "id": "threat_assessment",
                    "label": "Threat Assessment",
                    "tools": ["contraband_database"],
                    "desc": "CLIP semantic search across weapon and contraband categories.",
                },
                {
                    "id": "scene_plausibility",
                    "label": "Scene Plausibility",
                    "tools": ["lighting_consistency", "scale_validation",
                              "scene_incongruence"],
                    "desc": "Lighting direction, scale proportion, and noise-variance compositing triad.",
                },
                {
                    "id": "structural_integrity",
                    "label": "Structural Integrity",
                    "tools": ["image_splice_check", "noise_fingerprint",
                              "splicing_detect"],
                    "desc": "DCT quantization and PRNU noise-fingerprint splice detection.",
                },
                {
                    "id": "document_analysis",
                    "label": "Document & Text Analysis",
                    "tools": ["object_text_ocr", "document_authenticity"],
                    "desc": "OCR on detected regions and font/background forgery consistency check.",
                },
                {
                    "id": "deep_corroboration",
                    "label": "Deep AI Corroboration",
                    "tools": ["gemini_deep_forensic", "adversarial_robustness_check"],
                    "desc": "Gemini vision scene analysis and adversarial robustness check.",
                },
            ],
            "Agent4": [
                {
                    "id": "temporal_integrity",
                    "label": "Temporal Integrity",
                    "tools": ["optical_flow_analysis", "optical_flow_analyze",
                              "frame_consistency_analysis", "frame_consistency",
                              "anomaly_classification"],
                    "desc": "Optical-flow anomaly windows, SSIM frame consistency, EXPLAINABLE/SUSPICIOUS classification.",
                },
                {
                    "id": "identity_manipulation",
                    "label": "Identity Manipulation",
                    "tools": ["face_swap_detection", "face_swap_detect"],
                    "desc": "DeepFace embedding face-swap detection — high-priority standalone check.",
                },
                {
                    "id": "ai_generation",
                    "label": "AI Generation Detection",
                    "tools": ["deepfake_frequency_check", "deepfake_frequency"],
                    "desc": "GAN artifact detection via frequency domain — distinct from face-swap, targets fully synthetic frames.",
                },
                {
                    "id": "container_forensics",
                    "label": "Container & Technical Provenance",
                    "tools": ["av_file_identity", "mediainfo_profile",
                              "rolling_shutter_validation", "rolling_shutter"],
                    "desc": "Codec chain, VFR flag, encoding tool, creation timestamps, and rolling-shutter consistency.",
                },
                {
                    "id": "robustness",
                    "label": "Adversarial Robustness",
                    "tools": ["adversarial_robustness_check"],
                    "desc": "Optical-flow analysis stability under Gaussian noise and brightness perturbation.",
                },
            ],
            "Agent5": [
                {
                    "id": "metadata_integrity",
                    "label": "Core Metadata Integrity",
                    "tools": ["exif_extract", "metadata_anomaly_score",
                              "timestamp_analysis", "extract_deep_metadata"],
                    "desc": "EXIF field audit, ML anomaly scoring, and timestamp cross-consistency check.",
                },
                {
                    "id": "provenance_chain",
                    "label": "Provenance Chain",
                    "tools": ["device_fingerprint_db", "c2pa_verify",
                              "reverse_image_search"],
                    "desc": "Device EXIF fingerprint, Content Credentials (C2PA), and prior online-appearance check.",
                },
                {
                    "id": "geospatial_validation",
                    "label": "Geospatial Validation",
                    "tools": ["gps_timezone_validate", "astronomical_api",
                              "get_physical_address"],
                    "desc": "GPS-timezone cross-check and astronomical sun-elevation validation.",
                },
                {
                    "id": "file_tampering",
                    "label": "File-Level Tampering",
                    "tools": ["file_structure_analysis", "hex_signature_scan",
                              "thumbnail_mismatch", "file_hash_verify"],
                    "desc": "File-format header, hidden software signatures, and EXIF thumbnail vs main-image post-capture edit detection.",
                },
                {
                    "id": "hidden_payload",
                    "label": "Hidden Payload",
                    "tools": ["steganography_scan"],
                    "desc": "LSB and DCT steganographic payload detection — standalone high-severity check.",
                },
            ],
        }

        tool_groups = _TOOL_GROUPS.get(agent_key, [])

        # ── Pre-compute confidence and error rate from raw tool results ────────
        success_count = self._tool_success_count
        error_count   = self._tool_error_count
        total_calls   = success_count + error_count

        _not_applicable_keys = (
            "ela_not_applicable", "ghost_not_applicable",
            "noise_fingerprint_not_applicable", "prnu_not_applicable",
        )
        defensible_scores = [
            f.confidence_raw for f in self._findings
            if f.metadata.get("court_defensible", True)
            and not any(f.metadata.get(k) for k in _not_applicable_keys)
        ]
        pre_confidence = (
            round(sum(defensible_scores) / len(defensible_scores), 3)
            if defensible_scores else 0.75
        )
        pre_error_rate = round(error_count / total_calls, 3) if total_calls > 0 else 0.0

        fallback_count = sum(
            1 for f in self._findings
            if "fallback" in str(f.metadata.get("backend", "")).lower()
        )

        # ── Select target findings for this phase ─────────────────────────────
        initial_findings = [f for f in self._findings
                            if f.metadata.get("analysis_phase", "initial") == "initial"]
        deep_findings    = [f for f in self._findings
                            if f.metadata.get("analysis_phase", "initial") == "deep"]
        target_findings  = deep_findings if phase == "deep" and deep_findings else self._findings
        digest_findings  = target_findings[:18]   # raised ceiling to cover all tools

        # ── Build tool→finding index ──────────────────────────────────────────
        tool_to_findings: dict[str, list] = {}
        for f in digest_findings:
            tname = f.metadata.get("tool_name", "")
            if tname:
                tool_to_findings.setdefault(tname, []).append(f)

        # ── Build grouped digest ───────────────────────────────────────────────
        _SKIP_META = {
            "tool_name", "stub_warning", "llm_synthesis", "llm_reasoning",
            "synthesis_phase", "analysis_phase",
            "section_id", "section_label", "section_flag",
            "section_key_signal", "agent_confidence", "agent_error_rate",
        }
        _ALWAYS_META = {
            "ela_not_applicable", "ela_limitation_note",
            "ghost_not_applicable", "ghost_limitation_note",
            "noise_fingerprint_not_applicable", "prnu_not_applicable",
            "court_defensible", "available",
        }

        def _compact_metrics(f) -> dict:
            out: dict = {}
            for k, v in f.metadata.items():
                if k.startswith("_") or k in _SKIP_META:
                    continue
                if k in _ALWAYS_META:
                    out[k] = v
                    continue
                if isinstance(v, (bool, int, float)):
                    out[k] = v
                elif isinstance(v, str) and len(v) < 200:
                    out[k] = v
                elif isinstance(v, list) and len(v) <= 8 and all(
                    isinstance(x, (str, int, float, bool)) for x in v
                ):
                    out[k] = v
            return out

        # Map tool names to their group id for back-application
        tool_to_group_id: dict[str, str] = {}
        for grp in tool_groups:
            for t in grp["tools"]:
                tool_to_group_id[t] = grp["id"]

        grouped_sections: list[dict] = []
        grouped_tool_names: set[str] = {t for g in tool_groups for t in g["tools"]}

        for grp in tool_groups:
            grp_findings = [f for f in digest_findings
                            if f.metadata.get("tool_name", "") in grp["tools"]]
            if not grp_findings:
                continue
            tools_data = []
            for f in grp_findings:
                not_applicable = (
                    f.metadata.get("ela_not_applicable")
                    or f.metadata.get("ghost_not_applicable")
                    or f.metadata.get("noise_fingerprint_not_applicable")
                    or f.metadata.get("prnu_not_applicable")
                )
                tools_data.append({
                    "tool":            f.metadata.get("tool_name", "unknown"),
                    "finding_type":    f.finding_type,
                    "confidence":      round(f.confidence_raw, 3),
                    "status":          f.status,
                    "applicability":   "NOT_APPLICABLE" if not_applicable else "RAN",
                    "court_defensible": f.metadata.get("court_defensible", False),
                    "backend":         f.metadata.get("backend", ""),
                    "metrics":         _compact_metrics(f),
                })
            grouped_sections.append({
                "id":          grp["id"],
                "label":       grp["label"],
                "description": grp["desc"],
                "tools_data":  tools_data,
            })

        # Ungrouped findings → "other" section so nothing is lost
        ungrouped = [f for f in digest_findings
                     if f.metadata.get("tool_name", "") not in grouped_tool_names]
        if ungrouped:
            grouped_sections.append({
                "id": "other",
                "label": "Supplementary Analysis",
                "description": "Additional tool results not grouped above.",
                "tools_data": [{
                    "tool":            f.metadata.get("tool_name", "unknown"),
                    "finding_type":    f.finding_type,
                    "confidence":      round(f.confidence_raw, 3),
                    "status":          f.status,
                    "applicability":   "RAN",
                    "court_defensible": f.metadata.get("court_defensible", False),
                    "backend":         f.metadata.get("backend", ""),
                    "metrics":         _compact_metrics(f),
                } for f in ungrouped],
            })

        if not grouped_sections:
            return

        # ── Initial-findings context for deep pass ────────────────────────────
        initial_context = ""
        if phase == "deep" and initial_findings:
            init_items = [{
                "tool":       f.metadata.get("tool_name", ""),
                "type":       f.finding_type,
                "confidence": round(f.confidence_raw, 3),
                "summary":    (f.reasoning_summary or "")[:200],
            } for f in initial_findings[:8]]
            initial_context = (
                f"\n\nINITIAL analysis findings (compare each deep section against these):\n"
                f"{_json.dumps(init_items, indent=2)}"
            )

        # ── Build system prompt ───────────────────────────────────────────────
        section_desc_lines = "\n".join(
            f'  • {g["label"]} ({g["id"]}): {g["desc"]}'
            for g in tool_groups
            if any(s["id"] == g["id"] for s in grouped_sections)
        )

        phase_instruction = (
            "For each section compare findings against the initial analysis — "
            "label each as CONFIRMED, EXPANDED, or CONTRADICTED. "
            "For Gemini findings quote content type, ALL extracted text, detected objects, narrative, and verdict."
            if phase == "deep"
            else
            "For each section synthesize ALL tools in that group into one coherent forensic analysis."
        )

        system_prompt = f"""You are {self.agent_name}, producing a STRUCTURED forensic evidence report.

TOOL GROUPS present in this evidence:
{section_desc_lines}

Pre-computed stats (use as baseline; refine with your analysis):
  • pre_confidence : {pre_confidence}
  • pre_error_rate : {pre_error_rate}
  • fallback_count : {fallback_count} tool(s) used inline OpenCV/numpy implementations (valid results, note reduced evidentiary weight)

RULES:
1. Write one section entry per group that has tool data.
2. {phase_instruction}
3. NOT_APPLICABLE tools: explain WHY (file-type reason) — do NOT flag as suspicious, do NOT reduce confidence. They are expected for this file type.
4. court_defensible=false tools that RAN and FAILED: state "Tool X failed — excluded from confidence."
5. backend contains "inline": note "inline implementation — supporting evidentiary weight." Do NOT count as a tool failure.
6. Cite EXACT numeric metric values (ela_mean, anomaly_score, match_count, etc.) in every analysis sentence.
7. Corroboration: when 2+ tools in the same group agree, explicitly state "corroborated by [tool]."
8. flag values: "bad" = manipulation/threat confirmed; "warn" = anomaly detected, inconclusive; "ok" = clean; "info" = chain-of-custody/context.
9. confidence: weighted mean ONLY of tools that actually RAN (applicability=RAN). NOT_APPLICABLE tools are EXCLUDED from confidence calculation — their absence does NOT lower confidence. If all applicable tools returned clean results with no manipulation signals, confidence MUST be ≥ 0.72. Range 0.0–1.0.
10. error_rate: ONLY tools with court_defensible=false that actually ran AND failed. NOT_APPLICABLE tools and inline implementations that produced valid results do NOT count as errors. Range 0.0–1.0.
11. critical_findings: list only when "bad" flag sections exist with clear manipulation evidence.
12. Do NOT write generic phrases — every sentence must reference specific tool output data.
13. verdict calibration — choose exactly one:
    • "AUTHENTIC": all applicable integrity checks pass (no editing signatures, no manipulation flags); absence of EXIF fields alone is NOT a reason for INCONCLUSIVE; NOT_APPLICABLE tools alone are NOT a reason for INCONCLUSIVE.
    • "LIKELY_MANIPULATED": 2+ independent tools produced "bad" flags with confirmed manipulation evidence.
    • "INCONCLUSIVE": genuinely mixed evidence (some indicators present, some absent) OR critical applicable tools failed. Do NOT use INCONCLUSIVE when all applicable tools returned clean results.

Be CONCISE — target ≤1400 tokens total. Respond ONLY with valid JSON (no markdown, no preamble):
{{
  "verdict": "AUTHENTIC|LIKELY_MANIPULATED|INCONCLUSIVE",
  "confidence": <float 0-1>,
  "error_rate": <float 0-1>,
  "reliability_note": "<≤20 words>",
  "sections": [
    {{
      "id": "<section_id>",
      "label": "<label>",
      "flag": "ok|warn|bad|info",
      "analysis": "<2-3 sentences with exact metric values>",
      "key_signal": "<1 sentence>"
    }}
  ],
  "critical_findings": ["<string>"],
  "court_notes": "<1 sentence>"
}}"""

        user_content = (
            f"Evidence file: {evidence_context['file_name']}\n"
            f"MIME type: {evidence_context['mime_type']}\n"
            f"Analysis phase: {phase.upper()}\n\n"
            f"Grouped tool findings:\n{_json.dumps(grouped_sections, indent=2)}"
            f"{initial_context}\n\nProduce the structured forensic synthesis."
        )

        logger.info(
            f"Running Groq {phase}-pass grouped synthesis",
            agent_id=self.agent_id,
            section_count=len(grouped_sections),
            pre_confidence=pre_confidence,
            pre_error_rate=pre_error_rate,
        )

        try:
            raw_response = await llm_client.generate_synthesis(
                system_prompt=system_prompt,
                user_content=user_content,
                max_tokens=1500,  # 3 agents × 1500 = 4500 TPM, within Groq free tier
                timeout_override=25.0,
            )
        except Exception as groq_err:
            logger.warning(f"Groq synthesis API call failed: {groq_err}",
                           agent_id=self.agent_id)
            return

        try:
            response_text = raw_response.strip()
            # Strip markdown fences if Groq wraps in ```json
            if response_text.startswith("```"):
                response_text = response_text.split("```", 2)[-1].lstrip("json").strip()
                if response_text.endswith("```"):
                    response_text = response_text[:-3].strip()

            start = response_text.find("{")
            end   = response_text.rfind("}") + 1
            if start < 0 or end <= start:
                logger.warning(
                    f"Groq grouped synthesis: no JSON object in response. Raw (first 300): {response_text[:300]!r}",
                    agent_id=self.agent_id,
                )
                return

            report = _json.loads(response_text[start:end])

            # ── Extract agent-level scores ────────────────────────────────────
            groq_confidence  = float(report.get("confidence", pre_confidence))
            groq_error_rate  = float(report.get("error_rate",  pre_error_rate))
            groq_verdict     = str(report.get("verdict", "INCONCLUSIVE"))
            reliability_note = str(report.get("reliability_note", ""))
            critical_list    = report.get("critical_findings", [])
            court_notes      = str(report.get("court_notes", ""))

            # Clamp
            groq_confidence = max(0.0, min(1.0, groq_confidence))
            groq_error_rate = max(0.0, min(1.0, groq_error_rate))

            # Store on instance so investigation.py can read them for AGENT_COMPLETE
            self._agent_confidence = groq_confidence
            self._agent_error_rate = groq_error_rate

            # ── Build section lookup ──────────────────────────────────────────
            sections_out: dict[str, dict] = {}
            for sec in report.get("sections", []):
                sid = sec.get("id", "")
                if sid:
                    sections_out[sid] = sec

            # ── Apply section analyses back to findings ────────────────────────
            synthesized = 0
            for f in digest_findings:
                tname = f.metadata.get("tool_name", "")
                gid   = tool_to_group_id.get(tname, "other")
                sec   = sections_out.get(gid) or sections_out.get("other")
                if not sec:
                    continue

                analysis    = sec.get("analysis", "").strip()
                key_signal  = sec.get("key_signal", "").strip()
                sec_flag    = sec.get("flag", "info")
                sec_label   = sec.get("label", "")

                if analysis:
                    f.reasoning_summary = analysis
                    synthesized += 1

                # Tag finding with section metadata
                f.metadata.update({
                    "llm_synthesis":     analysis,
                    "synthesis_phase":   phase,
                    "section_id":        gid,
                    "section_label":     sec_label,
                    "section_flag":      sec_flag,
                    "section_key_signal": key_signal,
                    "agent_confidence":  groq_confidence,
                    "agent_error_rate":  groq_error_rate,
                    "agent_verdict":     groq_verdict,
                    "reliability_note":  reliability_note,
                    "court_notes":       court_notes,
                    "critical_findings": critical_list,
                })

            logger.info(
                f"Groq {phase}-pass grouped synthesis complete — verdict={groq_verdict} conf={groq_confidence:.2f} err={groq_error_rate:.2f}",
                agent_id=self.agent_id,
                sections_returned=len(sections_out),
                synthesized_count=synthesized,
                total_findings=len(digest_findings),
            )
        except Exception as parse_err:
            logger.warning(
                f"Groq grouped synthesis parse failed — raw findings preserved: {parse_err}",
                agent_id=self.agent_id,
            )
    
    async def self_reflection_pass(
        self,
        findings: list[AgentFinding]
    ) -> SelfReflectionReport:
        """
        Perform self-reflection on investigation findings.
        
        Uses 5 structured reflection prompts:
        - RT1: All tasks complete?
        - RT2: Overconfident findings?
        - RT3: Absences treated as signals?
        - RT4: Deprioritized avenues?
        - RT5: Confidence court-defensible?
        
        Args:
            findings: List of findings from the investigation
            
        Returns:
            SelfReflectionReport with reflection results
        """
        logger.info(
            "Running self-reflection pass",
            agent_id=self.agent_id,
            session_id=str(self.session_id),
        )
        
        # Get current working memory state
        state = await self.working_memory.get_state(
            session_id=self.session_id,
            agent_id=self.agent_id
        )
        
        # Get evidence artifact for context
        evidence_context = await self._get_evidence_context_for_reflection()
        
        # RT1: Check if all tasks are complete
        incomplete_tasks = []
        all_tasks_complete = True
        
        if state:
            for task in state.tasks:
                if task.status != TaskStatus.COMPLETE:
                    all_tasks_complete = False
                    incomplete_tasks.append(task.description)
        
        # RT2: Check for overconfident findings
        overconfident_findings = []
        for finding in findings:
            if finding.confidence_raw > 0.95 and not finding.calibrated:
                overconfident_findings.append(
                    f"{finding.finding_type}: {finding.confidence_raw:.2f}"
                )
        
        # RT3: Check for untreated absences (absence as signal)
        # Absence of expected data can itself be evidence
        untreated_absences = await self._check_untreated_absences(
            findings=findings,
            state=state,
            evidence_context=evidence_context,
        )
        
        # RT4: Check for deprioritized avenues
        # Investigation paths that were skipped or deprioritized
        deprioritized_avenues = await self._check_deprioritized_avenues(
            findings=findings,
            state=state,
            evidence_context=evidence_context,
        )
        
        # RT5: Check if confidence is court-defensible
        court_defensible = (
            all_tasks_complete and
            len(overconfident_findings) == 0 and
            len(findings) > 0
        )
        
        # Build reflection notes
        reflection_notes = []
        if incomplete_tasks:
            reflection_notes.append(f"Incomplete tasks: {len(incomplete_tasks)}")
        if overconfident_findings:
            reflection_notes.append(f"Overconfident findings: {len(overconfident_findings)}")
        if court_defensible:
            reflection_notes.append("Findings are court-defensible")
        else:
            reflection_notes.append("Findings may need additional review")
        
        report = SelfReflectionReport(
            all_tasks_complete=all_tasks_complete,
            incomplete_tasks=incomplete_tasks,
            overconfident_findings=overconfident_findings,
            untreated_absences=untreated_absences,
            deprioritized_avenues=deprioritized_avenues,
            court_defensible=court_defensible,
            reflection_notes="; ".join(reflection_notes),
        )
        
        # Log self-reflection
        if self.custody_logger:
            await self.custody_logger.log_entry(
                agent_id=self.agent_id,
                session_id=self.session_id,
                entry_type=EntryType.SELF_REFLECTION,
                content={
                    "all_tasks_complete": all_tasks_complete,
                    "incomplete_task_count": len(incomplete_tasks),
                    "overconfident_finding_count": len(overconfident_findings),
                    "court_defensible": court_defensible,
                    "reflection_notes": report.reflection_notes,
                }
            )
        
        logger.info(
            "Self-reflection complete",
            agent_id=self.agent_id,
            all_tasks_complete=all_tasks_complete,
            court_defensible=court_defensible,
            untreated_absence_count=len(untreated_absences),
            deprioritized_avenue_count=len(deprioritized_avenues),
        )
        
        return report
    
    async def _get_evidence_context_for_reflection(self) -> dict[str, Any]:
        """Get evidence context for reflection analysis."""
        context = {
            "mime_type": getattr(self.evidence_artifact, 'mime_type', 'unknown'),
            "file_extension": '',
            "has_exif": False,
            "has_audio": False,
            "has_video": False,
            "has_gps": False,
        }
        
        # Get file extension
        file_path = getattr(self.evidence_artifact, 'file_path', '')
        if file_path and '.' in file_path:
            context["file_extension"] = file_path.lower().split('.')[-1]
        
        # Check for common metadata indicators
        metadata = getattr(self.evidence_artifact, 'metadata', {}) or {}
        if isinstance(metadata, dict):
            context["has_exif"] = bool(metadata.get('exif'))
            context["has_gps"] = bool(metadata.get('gps_latitude'))
        
        # Determine media type
        mime = context["mime_type"].lower()
        context["has_audio"] = any(x in mime for x in ['audio', 'wav', 'mp3', 'ogg'])
        context["has_video"] = any(x in mime for x in ['video', 'mp4', 'avi', 'mov'])
        
        return context
    
    async def _check_untreated_absences(
        self,
        findings: list[AgentFinding],
        state: WorkingMemoryState | None,
        evidence_context: dict[str, Any],
    ) -> list[str]:
        """
        RT3: Check for untreated absences - missing expected data that could be signals.
        
        Absence of expected forensic artifacts can itself be evidence of manipulation.
        For example: missing EXIF in a camera-original, missing noise in a photo,
        or missing codec metadata in a video.
        """
        absences = []
        
        # Get finding types we have
        finding_types = {f.finding_type.lower() for f in findings}
        
        # Check for expected EXIF in image files
        mime = evidence_context.get("mime_type", "").lower()
        ext = evidence_context.get("file_extension", "").lower()
        
        is_image = any(x in mime for x in ['image', 'jpeg', 'jpg', 'png', 'tiff'])
        is_image = is_image or ext in ['jpg', 'jpeg', 'png', 'tiff', 'bmp', 'gif']
        
        if is_image:
            # Camera-original images should have EXIF
            has_exif_analysis = any("exif" in ft for ft in finding_types)
            has_metadata = evidence_context.get("has_exif", False)
            
            if has_exif_analysis and not has_metadata:
                absences.append(
                    "MISSING_EXIF_DATA: Image file lacks EXIF metadata, "
                    "which is unusual for camera-original files. May indicate "
                    "re-saving or metadata stripping."
                )
            
            # Check for missing noise fingerprint analysis result
            has_noise_analysis = any("noise" in ft or "fingerprint" in ft for ft in finding_types)
            if not has_noise_analysis:
                absences.append(
                    "MISSING_PRNU_ANALYSIS: No camera sensor noise fingerprint analysis "
                    "performed. This is a key technique for detecting region insertion."
                )
        
        # Check for expected audio/video metadata
        is_video = evidence_context.get("has_video", False)
        is_audio = evidence_context.get("has_audio", False)
        
        if is_video or is_audio:
            # Should have codec information
            has_codec_analysis = any("codec" in ft for ft in finding_types)
            if not has_codec_analysis:
                absences.append(
                    "MISSING_CODEC_FINGERPRINT: No codec fingerprinting analysis. "
                    "Codec metadata changes can indicate re-encoding or editing."
                )
        
        # Check for GPS-related absences
        if evidence_context.get("has_gps"):
            # If GPS exists, should validate it
            has_gps_validation = any("gps" in ft or "timezone" in ft for ft in finding_types)
            if not has_gps_validation:
                absences.append(
                    "UNTREATED_GPS_DATA: GPS coordinates present but not validated "
                    "against timezone or astronomical data."
                )
        
        # Check for missing hash verification
        has_hash_verify = any("hash" in ft for ft in finding_types)
        if not has_hash_verify:
            absences.append(
                "MISSING_HASH_VERIFICATION: No cryptographic hash verification performed. "
                "Cannot establish chain-of-custody baseline."
            )
        
        return absences
    
    async def _check_deprioritized_avenues(
        self,
        findings: list[AgentFinding],
        state: WorkingMemoryState | None,
        evidence_context: dict[str, Any],
    ) -> list[str]:
        """
        RT4: Check for deprioritized investigation avenues.
        
        Tracks which lines of inquiry were identified but not pursued,
        either due to time constraints, resource limitations, or tool unavailability.
        """
        deprioritized = []
        
        if not state:
            return deprioritized
        
        # Check tasks that were never started or abandoned
        for task in state.tasks:
            if task.status == TaskStatus.PENDING:
                # Task was never started - could be deprioritized
                deprioritized.append(
                    f"PENDING_TASK: '{task.description}' was never started. "
                    f"This may indicate the investigation was cut short."
                )
            elif task.status == TaskStatus.IN_PROGRESS:
                # Task started but not completed
                deprioritized.append(
                    f"INCOMPLETE_TASK: '{task.description}' was started but not completed. "
                    f"Results may be partial or inconclusive."
                )
        
        # Get finding types
        finding_types = {f.finding_type.lower() for f in findings}
        mime = evidence_context.get("mime_type", "").lower()
        
        # Check for high-value but unperformed analyses based on media type
        is_image = any(x in mime for x in ['image', 'jpeg', 'jpg', 'png'])
        is_video = evidence_context.get("has_video", False)
        is_audio = evidence_context.get("has_audio", False)
        
        if is_image:
            # ELA is foundational for image forensics
            has_ela = any("ela" in ft for ft in finding_types)
            if not has_ela:
                deprioritized.append(
                    "UNPERFORMED_ELA: Error Level Analysis not performed. "
                    "This is a fundamental technique for detecting re-compression artifacts."
                )
            
            # Copy-move detection
            has_copymove = any("copy" in ft or "move" in ft or "clone" in ft for ft in finding_types)
            if not has_copymove:
                deprioritized.append(
                    "UNPERFORMED_COPY_MOVE: Copy-move detection not performed. "
                    "Cloned regions are a common manipulation technique."
                )
        
        if is_video:
            # Frame consistency is crucial for video
            has_frame_check = any("frame" in ft for ft in finding_types)
            if not has_frame_check:
                deprioritized.append(
                    "UNPERFORMED_FRAME_ANALYSIS: No frame-to-frame consistency analysis. "
                    "Frame-level discontinuities can indicate splicing."
                )
            
            # Deepfake detection
            has_deepfake = any("deepfake" in ft or "face" in ft for ft in finding_types)
            if not has_deepfake:
                deprioritized.append(
                    "UNPERFORMED_DEEPFAKE_CHECK: Deepfake detection not performed. "
                    "Face-swap GAN artifacts have characteristic spectral signatures."
                )
        
        if is_audio:
            # Prosody analysis
            has_prosody = any("prosody" in ft or "pitch" in ft or "rhythm" in ft for ft in finding_types)
            if not has_prosody:
                deprioritized.append(
                    "UNPERFORMED_PROSODY_ANALYSIS: Prosody analysis not performed. "
                    "Synthetic voices often show unnatural pitch patterns."
                )
        
        # Check for adversarial/robustness testing (applies to all types)
        has_robustness = any("adversarial" in ft or "robustness" in ft for ft in finding_types)
        if not has_robustness:
            deprioritized.append(
                "UNPERFORMED_ROBUSTNESS_CHECK: No adversarial robustness testing. "
                "Findings may not hold up against anti-forensic countermeasures."
            )
        
        return deprioritized
    
    async def query_episodic_memory(
        self,
        signature_type: ForensicSignatureType,
        query_embedding: list[float],
        limit: int = 10
    ) -> list[EpisodicEntry]:
        """
        Query episodic memory for similar forensic signatures.
        
        Args:
            signature_type: Type of forensic signature to query
            query_embedding: Vector embedding for similarity search
            limit: Maximum number of results
            
        Returns:
            List of matching EpisodicEntry objects
        """
        if self.custody_logger:
            await self.custody_logger.log_entry(
                agent_id=self.agent_id,
                session_id=self.session_id,
                entry_type=EntryType.MEMORY_READ,
                content={
                    "action": "query_episodic_memory",
                    "signature_type": signature_type.value,
                    "limit": limit,
                }
            )
        
        results = await self.episodic_memory.query(
            signature_type=signature_type,
            query_embedding=query_embedding,
            top_k=limit
        )
        
        return results
    
    async def store_episodic_finding(
        self,
        entry: EpisodicEntry,
        embedding: list[float]
    ) -> None:
        """
        Store a finding in episodic memory.
        
        Args:
            entry: The episodic entry to store
            embedding: Vector embedding for the entry
        """
        if self.custody_logger:
            await self.custody_logger.log_entry(
                agent_id=self.agent_id,
                session_id=self.session_id,
                entry_type=EntryType.MEMORY_WRITE,
                content={
                    "action": "store_episodic_finding",
                    "signature_type": entry.signature_type.value,
                    "session_id": str(entry.session_id),
                }
            )
        
        await self.episodic_memory.store(entry, embedding)
    
    async def flag_hitl(
        self,
        reason: HITLCheckpointReason,
        brief: str
    ) -> None:
        """
        Flag a Human-in-the-Loop checkpoint.
        
        Args:
            reason: Why the checkpoint is needed
            brief: Brief description for the investigator
        """
        logger.warning(
            "HITL checkpoint flagged",
            agent_id=self.agent_id,
            reason=reason.value,
            brief=brief,
        )
        
        # In production, this would trigger the actual HITL flow
        # For now, we just log it
        if self.custody_logger:
            await self.custody_logger.log_entry(
                agent_id=self.agent_id,
                session_id=self.session_id,
                entry_type=EntryType.HITL_CHECKPOINT,
                content={
                    "action": "flag_hitl",
                    "reason": reason.value,
                    "brief": brief,
                }
        )
    
    async def handle_inter_agent_call(
        self,
        call: "InterAgentCall"
    ) -> dict[str, Any]:
        """
        Handle an incoming inter-agent call.
        
        Default implementation: runs targeted sub-analysis based on call payload.
        Subclasses can override for specialized handling.
        
        Args:
            call: The inter-agent call request
            
        Returns:
            Dictionary containing findings from the sub-analysis
        """
        logger.info(
            "Handling inter-agent call",
            agent_id=self.agent_id,
            caller=call.caller_agent_id,
            call_type=call.call_type.value,
            call_id=str(call.call_id),
        )
        
        # Log the incoming call
        if self.custody_logger:
            await self.custody_logger.log_entry(
                agent_id=self.agent_id,
                session_id=self.session_id,
                entry_type=EntryType.INTER_AGENT_CALL,
                content={
                    "action": "handle_inter_agent_call",
                    "call_id": str(call.call_id),
                    "caller_agent_id": call.caller_agent_id,
                    "call_type": call.call_type.value,
                    "payload": call.payload,
                }
            )
        
        # Default implementation: return a summary based on payload
        # Subclasses should override this for specialized handling
        response = {
            "status": "acknowledged",
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "findings": [],
            "message": f"{self.agent_name} received call from {call.caller_agent_id}",
        }
        
        # If payload contains specific analysis requests, handle them
        if call.payload:
            timestamp_ref = call.payload.get("timestamp_ref")
            region_ref = call.payload.get("region_ref")
            context_finding = call.payload.get("context_finding")
            question = call.payload.get("question")
            
            if question:
                response["question_received"] = question
            
            if context_finding:
                response["context_received"] = context_finding
            
            # Subclasses should override to perform actual analysis
            response["analysis_performed"] = False
            response["note"] = "Subclass should override handle_inter_agent_call for actual analysis"
        
        return response

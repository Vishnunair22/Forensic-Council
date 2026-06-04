"""
Reflection Mixin for Forensic Agents.
Handles self-reflection audits (RT1-RT5) for investigation quality.
"""

from __future__ import annotations

import uuid
from typing import Any

from agents.reflection_models import SelfReflectionReport
from core.custody_logger import EntryType
from core.react_loop import AgentFinding
from core.structured_logging import get_logger
from core.working_memory import TaskStatus

logger = get_logger(__name__)


class AgentReflectionMixin:
    """
    Mixin implementing self-reflection audits (RT1-RT5).
    """

    agent_id: str
    session_id: uuid.UUID
    working_memory: Any
    custody_logger: Any
    evidence_artifact: Any

    async def self_reflection_pass(self, findings: list[AgentFinding]) -> SelfReflectionReport:
        """Perform self-reflection on investigation findings."""
        logger.info("Running self-reflection pass", agent_id=self.agent_id)

        state = await self.working_memory.get_state(
            session_id=self.session_id, agent_id=self.agent_id
        )
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
            confidence = finding.confidence_raw
            if confidence is not None and confidence > 0.95 and not finding.calibrated:
                overconfident_findings.append(
                    f"{finding.finding_type}: {finding.confidence_raw:.2f}"
                )

        # RT3: Check for untreated absences
        untreated_absences = await self._check_untreated_absences(
            findings=findings, state=state, evidence_context=evidence_context
        )

        # RT4: Check for deprioritized avenues
        deprioritized_avenues = await self._check_deprioritized_avenues(
            findings=findings, state=state, evidence_context=evidence_context
        )

        # RT5: Check if confidence is court-defensible
        court_defensible = bool(all_tasks_complete and not overconfident_findings and findings)

        reflection_notes = []
        if incomplete_tasks:
            reflection_notes.append(f"Incomplete tasks: {len(incomplete_tasks)}")
        if overconfident_findings:
            reflection_notes.append(f"Overconfident findings: {len(overconfident_findings)}")
        reflection_notes.append(
            "Findings are court-defensible" if court_defensible else "Findings may need review"
        )

        report = SelfReflectionReport(
            all_tasks_complete=all_tasks_complete,
            incomplete_tasks=incomplete_tasks,
            overconfident_findings=overconfident_findings,
            untreated_absences=untreated_absences,
            deprioritized_avenues=deprioritized_avenues,
            court_defensible=court_defensible,
            reflection_notes="; ".join(reflection_notes),
        )

        if self.custody_logger:
            await self.custody_logger.log_entry(
                agent_id=self.agent_id,
                session_id=self.session_id,
                entry_type=EntryType.SELF_REFLECTION,
                content={
                    "all_tasks_complete": all_tasks_complete,
                    "court_defensible": court_defensible,
                    "reflection_notes": report.reflection_notes,
                },
            )

        return report

    async def _get_evidence_context_for_reflection(self) -> dict[str, Any]:
        """Get evidence context for reflection analysis."""
        context = {
            "mime_type": getattr(self.evidence_artifact, "mime_type", "unknown"),
            "file_extension": "",
            "has_exif": False,
            "has_audio": False,
            "has_video": False,
            "has_gps": False,
        }
        file_path = getattr(self.evidence_artifact, "file_path", "")
        if file_path and "." in file_path:
            context["file_extension"] = file_path.lower().split(".")[-1]

        # EXIF presence must come from the actual exif_extract tool result, not the
        # artifact metadata — the latter is never populated with EXIF at ingest, so
        # reading it made has_exif permanently False and RT3 reported a spurious
        # MISSING_EXIF_DATA absence for every image that DID carry metadata.
        tool_ctx = getattr(self, "_tool_context", {}) or {}
        exif_result = tool_ctx.get("exif_extract") or {}
        if isinstance(exif_result, dict):
            verdict = str(exif_result.get("evidence_verdict") or exif_result.get("status") or "").upper()
            has_real_exif = verdict != "NOT_APPLICABLE" and any(
                exif_result.get(k)
                for k in (
                    "fields_extracted", "camera_make", "camera_model",
                    "datetime_original", "software", "gps_coordinates",
                )
            )
            context["has_exif"] = bool(has_real_exif)
            context["has_gps"] = bool(
                exif_result.get("gps_coordinates") or exif_result.get("latitude")
            )

        mime = context["mime_type"].lower()
        context["has_audio"] = any(x in mime for x in ["audio", "wav", "mp3", "ogg"])
        context["has_video"] = any(x in mime for x in ["video", "mp4", "avi", "mov"])
        return context

    async def _check_untreated_absences(
        self, findings: list[AgentFinding], state: Any, evidence_context: dict
    ) -> list[str]:
        """RT3 Check."""
        absences = []
        finding_types = {f.finding_type.lower() for f in findings}
        mime = evidence_context.get("mime_type", "").lower()
        ext = evidence_context.get("file_extension", "").lower()
        is_image = "image" in mime or ext in ["jpg", "jpeg", "png", "tiff"]

        # Scope absence checks to the agent that owns the axis. The reflection
        # pass runs per-agent, so flagging "MISSING_PRNU" on the metadata agent or
        # "MISSING_EXIF" on the integrity agent produced cross-axis noise the agent
        # is not responsible for (and cannot act on).
        agent_id = str(getattr(self, "agent_id", "") or "")

        if is_image:
            # EXIF/metadata absence is Agent 5's concern.
            if agent_id.startswith("Agent5"):
                if any("exif" in ft for ft in finding_types) and not evidence_context.get("has_exif"):
                    absences.append("MISSING_EXIF_DATA: Image file lacks EXIF metadata.")
            # Sensor-noise (PRNU) absence is Agent 1's concern.
            if agent_id.startswith("Agent1"):
                if not any("noise" in ft or "fingerprint" in ft for ft in finding_types):
                    absences.append("MISSING_PRNU_ANALYSIS: No sensor noise analysis performed.")
        if evidence_context.get("has_video") or evidence_context.get("has_audio"):
            if not any("codec" in ft for ft in finding_types):
                absences.append("MISSING_CODEC_FINGERPRINT: No codec analysis.")
        return absences

    async def _check_deprioritized_avenues(
        self, findings: list[AgentFinding], state: Any, evidence_context: dict
    ) -> list[str]:
        """RT4 Check."""
        deprioritized = []
        if not state:
            return []
        for task in state.tasks:
            if task.status == TaskStatus.PENDING:
                deprioritized.append(f"PENDING_TASK: '{task.description}' never started.")
            elif task.status == TaskStatus.IN_PROGRESS:
                deprioritized.append(f"INCOMPLETE_TASK: '{task.description}' abandoned.")
        return deprioritized

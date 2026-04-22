"""
Agent 2 - Audio Authenticity Agent.

MANDATE (strict): Speech/audio authenticity and AV sync ONLY.
Detects audio deepfakes, splices, re-encoding events, and
acoustic provenance anomalies. Does NOT perform sentiment
analysis — sentiment consistency is not a reliable authenticity
signal and must not influence forensic verdicts.
"""

from __future__ import annotations

import asyncio

from agents.base_agent import ForensicAgent
from core.handlers.audio import AudioHandlers
from core.inter_agent_bus import InterAgentCall, InterAgentCallType
from core.structured_logging import get_logger
from core.tool_registry import ToolRegistry

logger = get_logger(__name__)

class Agent2Audio(ForensicAgent):
    """
    Agent 2 - Audio Authenticity Agent.

    Mandate (STRICT): Speech/audio authenticity and AV sync ONLY.
    No sentiment analysis — segment-level acoustic provenance is the
    authoritative signal, not affective consistency.
    """

    @property
    def agent_name(self) -> str:
        return "Agent2_AudioForensics"

    @property
    def task_decomposition(self) -> list[str]:
        # PHASE 1: INITIAL ANALYSIS (Neural Refined)
        tasks = [
            "Run speaker_diarize to establish voice count baseline",
            "Run neural_prosody across full audio track for acoustic artifact screening",
            "Run audio_gen_signature to identify spectral TTS fingerprints",
            "Run codec_fingerprinting for re-encoding event detection",
        ]
        mime = getattr(self.evidence_artifact, "mime_type", "") or ""
        if mime.startswith("video/"):
            tasks.append("Run audio_visual_sync verification for video audio track")
        return tasks

    @property
    def deep_task_decomposition(self) -> list[str]:
        # voice_clone_detect and anti_spoofing_detect are intentionally absent here —
        # the ensemble handlers re-run them internally and read the Phase 1 result from
        # _tool_context before overwriting it, preserving the cross-phase comparison.
        return [
            "Run prosody_analyze for acoustic marker verification",
            "Run audio_splice_detect on audio segments",
            "Run enf_analysis for electrical network frequency splice detection",
            "Run background_noise_analysis to identify shift points",
            "Run voice_clone_deep_ensemble for cross-validated AI speech synthesis detection if Phase 1 flagged a suspicious voice signal",
            "Run anti_spoofing_deep_ensemble for reinforced anti-spoofing on low-confidence segments if Phase 1 flagged a spoofing signal",
            "Run gemini_deep_forensic for Neural Audio Audit and Acoustic Provenance",
        ]

    def _has_audio_suspicious_signal(self) -> bool:
        """Gate expensive Phase-2 ensemble tools on Phase-1 suspicious signals."""
        ctx = self._tool_context
        return any([
            ctx.get("neural_prosody", {}).get("manipulation_detected", False),
            ctx.get("voice_clone_detect", {}).get("verdict") in ("CLONE", "SYNTHETIC", "SUSPICIOUS"),
            ctx.get("anti_spoofing_detect", {}).get("verdict") in ("SPOOF", "SUSPICIOUS"),
            ctx.get("audio_splice_detect", {}).get("splice_detected", False),
            ctx.get("audio_gen_signature", {}).get("synthetic_detected", False),
            ctx.get("codec_fingerprinting", {}).get("re_encoding_detected", False),
        ])

    @property
    def iteration_ceiling(self) -> int:
        # Phase 1 ceiling only — deep pass has its own budget via run_deep_investigation.
        return self._compute_ceiling(len(self.task_decomposition))

    @property
    def supported_file_types(self) -> list[str]:
        return ["audio/", "video/"]

    async def build_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()

        # ── Domain Handlers (Decentralized) ──────────────────────────────────
        audio_h = AudioHandlers(self)
        registry.register_domain_handler(audio_h)

        async def voice_clone_deep_ensemble_handler(input_data: dict) -> dict:
            # Snapshot Phase 1 result NOW — before the deep re-run overwrites the key.
            initial_result = self._tool_context.get("voice_clone_detect", {})

            if not self._has_audio_suspicious_signal():
                result = {
                    "ensemble_skipped": True,
                    "reason": "No Phase-1 suspicious voice signal — deep ensemble not triggered",
                    "confidence": initial_result.get("confidence", 0.0),
                    "verdict": initial_result.get("verdict", "CLEAN"),
                    "available": True,
                    "deep_ensemble": True,
                }
                await self._record_tool_result("voice_clone_deep_ensemble", result)
                return result

            try:
                deep_result = await audio_h.voice_clone_detect_handler(input_data)
                if isinstance(deep_result, dict) and isinstance(initial_result, dict):
                    deep_result["deep_ensemble"] = True
                    deep_result["initial_verdict"] = initial_result.get("verdict", "unknown")
                    deep_result["initial_confidence"] = initial_result.get("confidence", 0.0)
                    if deep_result.get("verdict") != initial_result.get("verdict"):
                        deep_result["phase_disagreement"] = True
                if isinstance(deep_result, dict):
                    await self._record_tool_result("voice_clone_deep_ensemble", deep_result)
                return deep_result
            except Exception as e:
                await self._record_tool_error("voice_clone_deep_ensemble", str(e))
                return {"error": str(e), "available": False, "deep_ensemble": True}

        async def anti_spoofing_deep_ensemble_handler(input_data: dict) -> dict:
            # Snapshot Phase 1 result NOW — before the deep re-run overwrites the key.
            initial_result = self._tool_context.get("anti_spoofing_detect", {})

            if not self._has_audio_suspicious_signal():
                result = {
                    "ensemble_skipped": True,
                    "reason": "No Phase-1 suspicious spoofing signal — deep ensemble not triggered",
                    "confidence": initial_result.get("confidence", 0.0),
                    "verdict": initial_result.get("verdict", "GENUINE"),
                    "available": True,
                    "deep_ensemble": True,
                }
                await self._record_tool_result("anti_spoofing_deep_ensemble", result)
                return result

            try:
                deep_result = await audio_h.anti_spoofing_detection_handler(input_data)
                if isinstance(deep_result, dict) and isinstance(initial_result, dict):
                    deep_result["deep_ensemble"] = True
                    deep_result["initial_verdict"] = initial_result.get("verdict", "unknown")
                    deep_result["initial_confidence"] = initial_result.get("confidence", 0.0)
                    if deep_result.get("verdict") != initial_result.get("verdict"):
                        deep_result["phase_disagreement"] = True
                if isinstance(deep_result, dict):
                    await self._record_tool_result("anti_spoofing_deep_ensemble", deep_result)
                return deep_result
            except Exception as e:
                await self._record_tool_error("anti_spoofing_deep_ensemble", str(e))
                return {"error": str(e), "available": False, "deep_ensemble": True}

        registry.register("voice_clone_deep_ensemble", voice_clone_deep_ensemble_handler, "Deep ensemble voice clone detection")
        registry.register("anti_spoofing_deep_ensemble", anti_spoofing_deep_ensemble_handler, "Deep ensemble anti-spoofing detection")

        # ── Gemini Neural Audio Audit ─────────────────────────────────────────
        from core.gemini_client import GeminiVisionClient
        _gemini = GeminiVisionClient(self.config)

        async def gemini_deep_forensic_handler(input_data: dict) -> dict:
            """Neural audio forensic audit using Gemini Flash."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            try:
                # Dynamic context aggregation — digest all successful results so
                # Gemini has total visibility without per-tool code updates.
                context_summary = {}
                for t_name, t_res in self._tool_context.items():
                    if not t_res or (isinstance(t_res, dict) and t_res.get("error")):
                        continue
                    # Drop raw binary blobs and excessively large payloads only.
                    # Small lists (speaker segments, splice timestamps) are kept as-is.
                    clean_res = {
                        k: v for k, v in t_res.items()
                        if not isinstance(v, bytes) and len(str(v)) < 5000
                    }
                    context_summary[t_name] = clean_res

                # Pull Agent 4 temporal context for AV sync grounding on video files
                mime = getattr(artifact, "mime_type", "") or ""
                if self.working_memory and mime.startswith("video/"):
                    try:
                        agent4_context = await self.working_memory.get_agent_context(self.session_id, "Agent4")
                        temporal_data = agent4_context.get("temporal_analysis", {})
                        if temporal_data:
                            context_summary["temporal_audit"] = {
                                "frame_consistency": temporal_data.get("frame_consistency"),
                                "av_sync_offset_ms": temporal_data.get("av_sync_offset_ms"),
                                "splice_timestamps": temporal_data.get("splice_timestamps"),
                            }
                    except Exception as _ctx_err:
                        logger.warning(
                            f"{self.agent_id}: Agent4 temporal context retrieval failed — Gemini will proceed without video temporal grounding",
                            error=str(_ctx_err),
                        )

                finding = await _gemini.deep_forensic_analysis(
                    file_path=artifact.file_path,
                    exif_summary=context_summary,
                    model_hint="gemini-2.5-flash"
                )
                result = finding.to_finding_dict(self.agent_id)
                result["analysis_source"] = "gemini_flash"
                await self._record_tool_result("gemini_deep_forensic", result)

                # Early signal — unblock the Arbiter as soon as core audio verdicts are ready.
                if self._gemini_signal_callback:
                    try:
                        cb_result = self._gemini_signal_callback(result)
                        if asyncio.iscoroutine(cb_result):
                            await cb_result
                    except Exception as cb_err:
                        logger.debug(f"{self.agent_id}: Gemini signal callback failed", error=str(cb_err))

                return result
            except Exception as e:
                await self._record_tool_error("gemini_deep_forensic", str(e))
                return {"error": str(e), "analysis_source": "gemini_flash", "available": False}

        registry.register("gemini_deep_forensic", gemini_deep_forensic_handler, "Gemini Flash neural audio forensic audit")

        # ── Agent-Specific Handlers ──────────────────────────────────────────
        async def inter_agent_call_handler(input_data: dict) -> dict:
            bus = self.inter_agent_bus
            if not bus:
                return {"status": "error", "message": "No bus available"}
            call = InterAgentCall(
                caller_agent_id=self.agent_id,
                callee_agent_id=input_data.get("target_agent", "Agent4"),
                call_type=InterAgentCallType.COLLABORATIVE,
                payload={
                    "timestamp_ref": input_data.get("timestamp_ref"),
                    "question": input_data.get("question", "Confirm AV sync at flagged timestamp"),
                },
            )
            resp = await bus.send(call, self.custody_logger)
            await self._record_tool_result("inter_agent_call", resp)
            return resp

        registry.register("inter_agent_call", inter_agent_call_handler, "Inter-agent communication")

        return registry

    async def build_initial_thought(self) -> str:
        return (
            f"Starting audio forensics for {self.evidence_artifact.artifact_id}. "
            f"I will execute spectral, temporal, and ML-based "
            f"integrity checks to detect clones, splices, or encoding anomalies."
        )

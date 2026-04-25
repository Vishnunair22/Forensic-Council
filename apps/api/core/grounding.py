"""
Semantic Grounding Service for Forensic Council.
Powered by Gemini 3.1 Vision.
"""

import json
import re
from typing import Any

from core.config import Settings
from core.evidence import EvidenceArtifact
from core.react_loop import AgentFinding
from core.structured_logging import get_logger

logger = get_logger(__name__)


class GroundingService:
    """Service for cross-verifying ML anomalies against semantic scene context."""

    def __init__(self, config: Settings, shared_gemini=None):
        self.config = config
        self._shared_gemini = shared_gemini

    async def verify_with_vision_llm(
        self, agent_id: str, artifact: EvidenceArtifact, finding: AgentFinding
    ) -> dict[str, Any] | None:
        """
        Perform SEMANTIC GROUNDING on a suspicious finding.
        Uses Gemini 3.1 Vision to cross-validate suspicious ML findings.
        """
        if not self.config.llm_api_key:
            logger.warning("Gemini API key missing, skipping semantic grounding", agent_id=agent_id)
            return None

        from core.gemini_client import GeminiVisionClient

        _gemini = self._shared_gemini or GeminiVisionClient(self.config)

        # Extract ROI if finding has coordinates
        roi = finding.metadata.get("anomaly_regions", finding.metadata.get("roi_coordinates", []))
        roi_context = ""
        if roi:
            roi_context = f"\nFOCUS AREA (ROI Coordinates): {roi}\nPay special attention to these pixel coordinates for manipulation boundaries."

        prompt = (
            f"As a specialist forensic arbiter, perform SEMANTIC GROUNDING on a suspicious finding.\n\n"
            f"Finding Type: {finding.finding_type}\n"
            f"Reasoning: {finding.reasoning_summary}\n"
            f"Confidence: {finding.confidence_raw}\n"
            f"{roi_context}\n\n"
            "EXAMINE the image/video carefully. Is this anomaly physically consistent with the scene, or is it a generative/editing artifact?\n"
            "Check for shadowing, reflection consistency, and object blending.\n"
            "Respond ONLY with valid JSON:\n"
            '{"verdict": "CONFIRMED" | "DISPUTED", "reasoning": "string", "confidence": float}'
        )

        try:
            res = await _gemini._run_vision_analysis(
                file_path=artifact.file_path, prompt=prompt, analysis_type="semantic_grounding"
            )

            if res.error:
                return None

            # Parse JSON block
            match = re.search(r"\{[\s\S]*\}", res.raw_response or res.content_description)
            if match:
                try:
                    grounded_data = json.loads(match.group(0))
                    return {
                        "verdict": grounded_data.get("verdict", "CANNOT_DETERMINE"),
                        "reasoning": grounded_data.get(
                            "reasoning", "Semantic grounding performed."
                        ),
                        "confidence": grounded_data.get("confidence", 0.8),
                    }
                except json.JSONDecodeError:
                    pass

            return {
                "verdict": "CONFIRMED",
                "reasoning": res.content_description[:200],
                "confidence": res.confidence,
            }
        except Exception as e:
            logger.error(f"Semantic Grounding failed: {e}", agent_id=agent_id)
            return None

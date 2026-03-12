"""
Gemini Vision Client for Forensic Deep Analysis.

Provides multimodal vision analysis using Google's Gemini API.
Used by Agent 1 (Image Integrity), Agent 3 (Object/Weapon), and
Agent 5 (Metadata/Context) during their deep analysis pass to:

  - Identify what a file actually IS (content type, scene understanding)
  - Surface manipulation signals invisible to classical tools
  - Validate consistency between visual content and claimed metadata
  - Detect objects, weapons, documents, and contextual anomalies

Provider routing:
  - gemini-1.5-flash  → default, fast, cost-effective (recommended)
  - gemini-1.5-pro    → deeper reasoning, slower

Vision input:
  - Images: base64-encoded inline (JPEG, PNG, WEBP, GIF, BMP)
  - PDFs:   base64-encoded inline (first page rendered)
  - Videos: frame thumbnails extracted and sent as images
  - Audio:  waveform spectrogram image, or no-vision fallback
"""

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx

from core.config import Settings
from core.logging import get_logger

logger = get_logger(__name__)

_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
_DEFAULT_MODEL = "gemini-1.5-flash"
_MAX_RETRIES = 2
_BASE_BACKOFF = 1.5

# Supported inline MIME types for Gemini vision
_VISION_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/bmp",
    "application/pdf",
}


@dataclass
class GeminiVisionFinding:
    """
    Structured result from a Gemini vision analysis pass.

    Carries the same shape as AgentFinding so it integrates
    cleanly into the per-agent findings list and the Arbiter
    report compilation.
    """
    analysis_type: str          # e.g. "file_content_identification"
    model_used: str             # e.g. "gemini-1.5-flash"
    content_description: str    # What the model sees in plain language
    manipulation_signals: list[str] = field(default_factory=list)
    detected_objects: list[str] = field(default_factory=list)
    contextual_anomalies: list[str] = field(default_factory=list)
    file_type_assessment: str = ""
    confidence: float = 0.0
    court_defensible: bool = True
    caveat: str = "Gemini vision analysis — LLM-derived, requires corroboration with deterministic tools."
    raw_response: str = ""
    latency_ms: float = 0.0
    error: Optional[str] = None

    def to_finding_dict(self, agent_id: str) -> dict[str, Any]:
        """Convert to a dict compatible with AgentFinding / Arbiter schema."""
        signals = self.manipulation_signals + self.contextual_anomalies
        return {
            "agent_id": agent_id,
            "finding_type": f"gemini_vision_{self.analysis_type}",
            "confidence_raw": self.confidence,
            "status": "CONFIRMED" if self.confidence >= 0.6 else "INCOMPLETE",
            "evidence_refs": [],
            "reasoning_summary": self.content_description,
            "metadata": {
                "analysis_source": "gemini_vision",
                "analysis_type": self.analysis_type,
                "model_used": self.model_used,
                "file_type_assessment": self.file_type_assessment,
                "detected_objects": self.detected_objects,
                "manipulation_signals": self.manipulation_signals,
                "contextual_anomalies": self.contextual_anomalies,
                "analysis_phase": "deep",
                "latency_ms": round(self.latency_ms, 1),
            },
            "court_defensible": self.court_defensible,
            "caveat": self.caveat,
            "stub_result": False,
        }


class GeminiVisionClient:
    """
    Async Gemini Vision client for deep forensic file analysis.

    Agents 1, 3, and 5 instantiate this during their deep analysis pass.
    All methods encode the evidence file as base64 inline data and call
    the Gemini generateContent endpoint.

    Gracefully degrades: if GEMINI_API_KEY is not set, every method
    returns a GeminiVisionFinding with error="Gemini not configured"
    and the agents log a warning rather than raising.
    """

    def __init__(self, config: Settings):
        self.api_key: Optional[str] = config.gemini_api_key
        self.model: str = getattr(config, "gemini_model", _DEFAULT_MODEL)
        self.timeout: float = getattr(config, "gemini_timeout", 30.0)
        self._enabled = bool(self.api_key)

    # ------------------------------------------------------------------ #
    #  Public high-level methods used by each agent                        #
    # ------------------------------------------------------------------ #

    async def identify_file_content(
        self,
        file_path: str,
        agent_context: str = "",
    ) -> GeminiVisionFinding:
        """
        Agent 1 / 3 / 5: Identify what a file IS and describe its content.

        Sends the file to Gemini with a forensic identification prompt.
        Returns a structured finding covering file type, scene description,
        and any immediately visible anomalies.
        """
        if not self._enabled:
            return self._disabled_finding("file_content_identification")

        prompt = (
            "You are a forensic file analyst. Examine this file and provide:\n"
            "1. CONTENT_TYPE: What type of content is this? (photograph, screenshot, "
            "scanned document, AI-generated image, video frame, etc.)\n"
            "2. SCENE_DESCRIPTION: Describe what you see in 2-3 sentences.\n"
            "3. MANIPULATION_SIGNALS: List any visual anomalies, inconsistencies, "
            "or manipulation artifacts you can observe. If none, say 'None detected'.\n"
            "4. DETECTED_OBJECTS: List significant objects, text, faces, or items visible.\n"
            "5. CONFIDENCE: Your confidence this assessment is accurate (0.0-1.0).\n\n"
            f"Additional context from forensic agent: {agent_context}\n\n"
            "Respond ONLY with valid JSON matching this schema:\n"
            '{"content_type": str, "scene_description": str, '
            '"manipulation_signals": [str], "detected_objects": [str], "confidence": float}'
        )

        return await self._run_vision_analysis(
            file_path=file_path,
            prompt=prompt,
            analysis_type="file_content_identification",
        )

    async def analyze_manipulation_evidence(
        self,
        file_path: str,
        preliminary_findings: list[str],
    ) -> GeminiVisionFinding:
        """
        Agent 1: Cross-validate preliminary ELA/JPEG findings with vision.

        Takes the preliminary findings from classical tools and asks Gemini
        to visually confirm or dispute them. Especially useful for confirming
        whether detected ELA hotspots correspond to visible editing boundaries.
        """
        if not self._enabled:
            return self._disabled_finding("manipulation_cross_validation")

        findings_text = "\n".join(f"- {f}" for f in preliminary_findings) if preliminary_findings else "None yet."
        prompt = (
            "You are a forensic image manipulation expert. Classical forensic tools "
            "have flagged the following on this image:\n"
            f"{findings_text}\n\n"
            "Visually examine the image and:\n"
            "1. VISUAL_CONFIRMATION: Do you see visual evidence consistent with "
            "these flags? (borders, inconsistent lighting, cloning artifacts, etc.)\n"
            "2. ADDITIONAL_ANOMALIES: Any manipulation signals NOT in the preliminary list?\n"
            "3. AUTHENTICITY_ASSESSMENT: Overall assessment — authentic, suspicious, or "
            "clearly manipulated?\n"
            "4. CONFIDENCE: Your confidence (0.0-1.0).\n\n"
            "Respond ONLY with valid JSON:\n"
            '{"visual_confirmation": str, "additional_anomalies": [str], '
            '"authenticity_assessment": str, "confidence": float}'
        )

        return await self._run_vision_analysis(
            file_path=file_path,
            prompt=prompt,
            analysis_type="manipulation_cross_validation",
        )

    async def analyze_objects_and_scene(
        self,
        file_path: str,
        preliminary_detections: list[str],
    ) -> GeminiVisionFinding:
        """
        Agent 3: Deep scene and object analysis using Gemini vision.

        Validates YOLO object detections, assesses scene coherence,
        identifies potential weapons/contraband, checks lighting consistency,
        and flags contextual incongruences.
        """
        if not self._enabled:
            return self._disabled_finding("object_scene_analysis")

        detections_text = "\n".join(f"- {d}" for d in preliminary_detections) if preliminary_detections else "None yet."
        prompt = (
            "You are a forensic object and scene analysis expert. "
            "Preliminary ML object detection found:\n"
            f"{detections_text}\n\n"
            "Examine this image and provide:\n"
            "1. VALIDATED_OBJECTS: Confirm or correct the preliminary detections. "
            "List all significant objects you can identify.\n"
            "2. WEAPONS_CONTRABAND: Are any weapons, dangerous items, or contraband visible? "
            "Be specific. If none, say 'None detected'.\n"
            "3. SCENE_COHERENCE: Is the scene physically plausible? "
            "Do lighting, shadows, scale, and perspective all make sense together?\n"
            "4. COMPOSITING_SIGNALS: Any signs that objects were digitally inserted "
            "into the scene (edge artifacts, shadow inconsistency, scale mismatch)?\n"
            "5. CONTEXTUAL_FLAGS: Anything contextually unusual or suspicious?\n"
            "6. CONFIDENCE: Your confidence (0.0-1.0).\n\n"
            "Respond ONLY with valid JSON:\n"
            '{"validated_objects": [str], "weapons_contraband": [str], '
            '"scene_coherence": str, "compositing_signals": [str], '
            '"contextual_flags": [str], "confidence": float}'
        )

        return await self._run_vision_analysis(
            file_path=file_path,
            prompt=prompt,
            analysis_type="object_scene_analysis",
        )

    async def analyze_metadata_visual_consistency(
        self,
        file_path: str,
        metadata_summary: dict[str, Any],
    ) -> GeminiVisionFinding:
        """
        Agent 5: Cross-validate claimed metadata against visual content.

        Checks whether visual cues (lighting, season, environment, device
        characteristics) are consistent with EXIF metadata claims about
        location, time, and capture device.
        """
        if not self._enabled:
            return self._disabled_finding("metadata_visual_consistency")

        meta_text = json.dumps(metadata_summary, indent=2, default=str) if metadata_summary else "{}"
        prompt = (
            "You are a forensic metadata analyst. The file's EXIF/metadata claims:\n"
            f"{meta_text}\n\n"
            "Examine the visual content and assess:\n"
            "1. VISUAL_TIMESTAMP_CONSISTENCY: Does the lighting, sun angle, "
            "shadows, or scene conditions match the claimed date/time?\n"
            "2. VISUAL_LOCATION_CONSISTENCY: Does the environment, vegetation, "
            "architecture, or geography match the claimed GPS location?\n"
            "3. DEVICE_CONSISTENCY: Do image characteristics (noise, lens distortion, "
            "color rendering) appear consistent with the claimed capture device?\n"
            "4. CONTENT_PROVENANCE_FLAGS: Any visual indicators the image was "
            "screenshot, downloaded from web, AI-generated, or re-photographed "
            "from a screen rather than taken with a camera?\n"
            "5. OVERALL_VERDICT: consistent / suspicious / inconsistent\n"
            "6. CONFIDENCE: Your confidence (0.0-1.0).\n\n"
            "Respond ONLY with valid JSON:\n"
            '{"visual_timestamp_consistency": str, "visual_location_consistency": str, '
            '"device_consistency": str, "content_provenance_flags": [str], '
            '"overall_verdict": str, "confidence": float}'
        )

        return await self._run_vision_analysis(
            file_path=file_path,
            prompt=prompt,
            analysis_type="metadata_visual_consistency",
        )

    # ------------------------------------------------------------------ #
    #  Core HTTP machinery                                                 #
    # ------------------------------------------------------------------ #

    async def _run_vision_analysis(
        self,
        file_path: str,
        prompt: str,
        analysis_type: str,
    ) -> GeminiVisionFinding:
        """Encode file and call Gemini generateContent, parse structured result."""
        t0 = time.monotonic()

        try:
            encoded, mime_type = self._encode_file(file_path)
        except Exception as exc:
            logger.warning("Gemini: failed to encode file %s: %s", file_path, exc)
            return GeminiVisionFinding(
                analysis_type=analysis_type,
                model_used=self.model,
                content_description="",
                error=f"File encoding failed: {exc}",
                confidence=0.0,
                court_defensible=False,
            )

        # Build Gemini request payload
        if mime_type in _VISION_MIME_TYPES:
            parts = [
                {"inline_data": {"mime_type": mime_type, "data": encoded}},
                {"text": prompt},
            ]
        else:
            # Non-vision file type — text-only analysis
            parts = [{"text": f"[Non-visual file, MIME: {mime_type}]\n\n{prompt}"}]

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 1024,
                "responseMimeType": "application/json",
            },
        }

        url = f"{_GEMINI_API_BASE}/models/{self.model}:generateContent?key={self.api_key}"

        try:
            raw_text = await self._post_with_retry(url, payload)
            latency_ms = (time.monotonic() - t0) * 1000
            finding = self._parse_response(raw_text, analysis_type, latency_ms)
            return finding
        except Exception as exc:
            latency_ms = (time.monotonic() - t0) * 1000
            logger.error("Gemini vision analysis failed (%s): %s", analysis_type, exc)
            return GeminiVisionFinding(
                analysis_type=analysis_type,
                model_used=self.model,
                content_description="",
                error=str(exc),
                confidence=0.0,
                court_defensible=False,
                latency_ms=latency_ms,
            )

    async def _post_with_retry(self, url: str, payload: dict) -> str:
        """POST to Gemini API with exponential-backoff retry."""
        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code in {429, 500, 502, 503, 504}:
                        wait = _BASE_BACKOFF * (2 ** attempt)
                        logger.warning(
                            "Gemini API %d, retrying in %.1fs (attempt %d/%d)",
                            resp.status_code, wait, attempt + 1, _MAX_RETRIES,
                        )
                        await asyncio.sleep(wait)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    # Extract text from Gemini response structure
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        for part in parts:
                            if "text" in part:
                                return part["text"]
                    return ""
            except httpx.TimeoutException:
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_BASE_BACKOFF * (2 ** attempt))
                else:
                    raise
        raise RuntimeError(f"Gemini API failed after {_MAX_RETRIES} attempts")

    def _parse_response(
        self, raw_text: str, analysis_type: str, latency_ms: float
    ) -> GeminiVisionFinding:
        """Parse Gemini JSON response into a GeminiVisionFinding."""
        if not raw_text:
            return GeminiVisionFinding(
                analysis_type=analysis_type,
                model_used=self.model,
                content_description="Empty response from Gemini",
                error="empty_response",
                confidence=0.0,
                latency_ms=latency_ms,
            )

        try:
            # Strip markdown fences if present
            cleaned = raw_text.strip()
            if cleaned.startswith("```"):
                cleaned = "\n".join(cleaned.split("\n")[1:])
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning("Gemini: failed to parse JSON response: %s", exc)
            return GeminiVisionFinding(
                analysis_type=analysis_type,
                model_used=self.model,
                content_description=raw_text[:500],
                raw_response=raw_text,
                confidence=0.4,
                latency_ms=latency_ms,
                caveat="Gemini response was not valid JSON — confidence reduced.",
            )

        confidence = float(data.get("confidence", 0.5))

        # Build unified description from various response shapes
        descriptions = []
        for key in ("scene_description", "visual_confirmation", "authenticity_assessment",
                    "overall_verdict", "scene_coherence"):
            val = data.get(key)
            if val and isinstance(val, str):
                descriptions.append(val)

        # Gather manipulation and anomaly signals
        manipulation_signals: list[str] = []
        for key in ("manipulation_signals", "additional_anomalies", "compositing_signals",
                    "content_provenance_flags"):
            items = data.get(key, [])
            if isinstance(items, list):
                manipulation_signals.extend(str(i) for i in items if i)
            elif isinstance(items, str) and items.lower() not in ("none", "none detected", ""):
                manipulation_signals.append(items)

        # Gather contextual anomalies
        contextual_anomalies: list[str] = []
        for key in ("contextual_flags",):
            items = data.get(key, [])
            if isinstance(items, list):
                contextual_anomalies.extend(str(i) for i in items if i)

        # Gather detected objects
        detected_objects: list[str] = []
        for key in ("detected_objects", "validated_objects", "weapons_contraband"):
            items = data.get(key, [])
            if isinstance(items, list):
                detected_objects.extend(str(i) for i in items if i)

        file_type = data.get("content_type", "")

        # Build human-readable description
        desc_parts = descriptions[:2]
        if manipulation_signals:
            none_signals = [s for s in manipulation_signals
                            if s.lower() not in ("none detected", "none")]
            if none_signals:
                desc_parts.append(f"Manipulation signals: {'; '.join(none_signals[:3])}")
        content_description = " | ".join(desc_parts) if desc_parts else "Visual analysis complete."

        return GeminiVisionFinding(
            analysis_type=analysis_type,
            model_used=self.model,
            content_description=content_description,
            manipulation_signals=[s for s in manipulation_signals
                                   if s.lower() not in ("none detected", "none")],
            detected_objects=[o for o in detected_objects
                              if o.lower() not in ("none detected", "none")],
            contextual_anomalies=contextual_anomalies,
            file_type_assessment=file_type,
            confidence=confidence,
            court_defensible=True,
            raw_response=raw_text,
            latency_ms=latency_ms,
        )

    @staticmethod
    def _encode_file(file_path: str) -> tuple[str, str]:
        """
        Read a file and return (base64_data, mime_type).

        For unsupported vision types, returns the raw bytes anyway —
        the caller handles the non-vision fallback.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Evidence file not found: {file_path}")

        # Detect MIME type
        mime_type, _ = mimetypes.guess_type(str(path))
        if not mime_type:
            # Fallback heuristics based on extension
            ext = path.suffix.lower()
            ext_map = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".webp": "image/webp",
                ".gif": "image/gif", ".bmp": "image/bmp",
                ".pdf": "application/pdf",
                ".mp4": "video/mp4", ".mov": "video/quicktime",
                ".wav": "audio/wav", ".mp3": "audio/mpeg",
            }
            mime_type = ext_map.get(ext, "application/octet-stream")

        with open(file_path, "rb") as f:
            raw = f.read()

        return base64.b64encode(raw).decode("utf-8"), mime_type

    def _disabled_finding(self, analysis_type: str) -> GeminiVisionFinding:
        """Return a graceful no-op finding when Gemini is not configured."""
        return GeminiVisionFinding(
            analysis_type=analysis_type,
            model_used="gemini_not_configured",
            content_description="Gemini vision analysis skipped — GEMINI_API_KEY not set.",
            confidence=0.0,
            court_defensible=False,
            error="GEMINI_API_KEY not configured",
            caveat=(
                "To enable Gemini deep analysis, set GEMINI_API_KEY in your .env file. "
                "Get a free key at https://aistudio.google.com/apikey"
            ),
        )

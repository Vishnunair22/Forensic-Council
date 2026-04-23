"""
Gemini Vision Client for Forensic Deep Analysis.

Provides multimodal vision analysis using Google's Gemini API.
Used by Agent 1 (Image Integrity), Agent 3 (Object/Weapon), and
Agent 5 (Metadata/Context) during their deep analysis pass to:

  - Identify what a file actually IS (content type, scene understanding)
  - Surface manipulation signals invisible to classical tools
  - Validate consistency between visual content and claimed metadata
  - Detect objects, weapons, documents, and contextual anomalies

Provider routing (cascade - first available wins):
  1. gemini-2.5-flash -> default primary, 1M context, best price-performance
  2. gemini-2.5-flash-lite -> fastest stable 2.5 fallback
  3. gemini-2.0-flash -> previous-generation stable fallback
  4. gemini-2.0-flash-lite -> ultra-fast previous-generation fallback

Auto-cascade: 404 / 429 (quota) / "model not found" responses skip immediately to
the next model; other errors retry with backoff then cascade forward.
The chain is fully configurable via GEMINI_MODEL + GEMINI_FALLBACK_MODELS.

NOTE: Stable gemini-2.5-* and gemini-2.0-* models are the verified production
      standards. Preview models may have tighter quotas and deprecation windows.

Vision input:
  - Images: base64-encoded inline (JPEG, PNG, WEBP, GIF, BMP)
  - PDFs:   base64-encoded inline (first page rendered)
  - Videos: frame thumbnails extracted and sent as images
  - Audio:  waveform spectrogram image, or no-vision fallback
"""

import asyncio
import base64
import json
import mimetypes
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from core.config import Settings
from core.observability import get_tracer
from core.retry import CircuitBreaker
from core.structured_logging import get_logger

logger = get_logger(__name__)
_tracer = get_tracer("forensic-council.gemini")

_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
_MAX_RETRIES = 5
_BASE_BACKOFF = 2.0

_DEFAULT_MODEL = "gemini-2.5-flash"

_DEFAULT_FALLBACK_CHAIN = (
    "gemini-2.5-flash-lite,gemini-2.0-flash,gemini-2.0-flash-lite"
)

_THINKING_MODEL_PREFIXES = (
    "gemini-2.5",
)


class _ModelUnavailableError(Exception):
    """Raised when the API returns 404 or a 'model not found' body.

    Signals the cascade loop to skip immediately to the next model
    without backoff — the model simply does not exist on this API key.
    """


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

    analysis_type: str  # e.g. "file_content_identification"
    model_used: str  # e.g. "gemini-2.5-flash"
    content_description: str  # What the model sees in plain language
    manipulation_signals: list[str] = field(default_factory=list)
    detected_objects: list[str] = field(default_factory=list)
    contextual_anomalies: list[str] = field(default_factory=list)
    file_type_assessment: str = ""
    confidence: float = 0.0
    court_defensible: bool = True
    caveat: str = "Gemini vision analysis — LLM-derived, requires corroboration with deterministic tools."
    raw_response: str = ""
    latency_ms: float = 0.0
    error: str | None = None
    # Deep forensic analysis extras (populated by deep_forensic_analysis)
    _extracted_text: list[str] = field(default_factory=list)
    _interface_identification: str = ""
    _contextual_narrative: str = ""
    _authenticity_verdict: str = ""
    _metadata_visual_consistency: str = ""

    def to_finding_dict(self, agent_id: str) -> dict[str, Any]:
        """Convert to a dict compatible with AgentFinding / Arbiter schema."""
        tool_name = (
            "gemini_deep_forensic"
            if self.analysis_type == "deep_forensic_analysis"
            else f"gemini_{self.analysis_type}"
        )
        return {
            "agent_id": agent_id,
            "finding_type": f"gemini_vision_{self.analysis_type}",
            "confidence_raw": self.confidence,
            "status": "CONFIRMED"
            if (
                self.confidence >= 0.6
                or getattr(self, "_authenticity_verdict", "").upper()
                in ("SUSPICIOUS", "LIKELY_MANIPULATED", "AI_GENERATED")
            )
            else "INCOMPLETE",
            "evidence_refs": [],
            "reasoning_summary": self.content_description,
            "metadata": {
                "tool_name": tool_name,
                "analysis_source": "gemini_vision",
                "analysis_type": self.analysis_type,
                "model_used": self.model_used,
                "file_type_assessment": self.file_type_assessment,
                "detected_objects": self.detected_objects,
                "manipulation_signals": self.manipulation_signals,
                "contextual_anomalies": self.contextual_anomalies,
                # deep_forensic_analysis extras (populated if analysis_type == 'deep_forensic_analysis')
                "extracted_text": getattr(self, "_extracted_text", []),
                "interface_identification": getattr(
                    self, "_interface_identification", ""
                ),
                "contextual_narrative": getattr(self, "_contextual_narrative", ""),
                "authenticity_verdict": getattr(self, "_authenticity_verdict", ""),
                "metadata_visual_consistency": getattr(
                    self, "_metadata_visual_consistency", ""
                ),
                "analysis_phase": "deep",
                "latency_ms": round(self.latency_ms, 1),
                # Map authenticity_verdict to standard manipulation flags so the
                # arbiter's _is_direct_manip check registers Gemini findings.
                "manipulation_detected": getattr(
                    self, "_authenticity_verdict", ""
                ).upper()
                in ("SUSPICIOUS", "LIKELY_MANIPULATED"),
                "deepfake_detected": getattr(self, "_authenticity_verdict", "").upper()
                == "AI_GENERATED",
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

    Quota pooling: a class-level semaphore (``_quota_semaphore``) limits
    concurrent Gemini calls across all instances.  This prevents 5 agents
    running in parallel from all issuing requests simultaneously and
    saturating the free-tier RPM quota (10 RPM on gemini-2.5-flash).
    The concurrency limit is set once via ``configure_quota_pool()`` at
    startup and defaults to 2 if never called.
    """

    # Class-level quota semaphore — shared across all instances / agents.
    # Lazily created so it lives inside the running event loop.
    _quota_semaphore: asyncio.Semaphore | None = None
    _quota_limit: int = 2  # conservative default; overridden by configure_quota_pool()

    @classmethod
    def configure_quota_pool(cls, max_concurrent: int) -> None:
        """
        Set the process-wide Gemini concurrency limit.

        Call once at application startup (after the event loop is running).
        Subsequent calls reset the semaphore — only safe before any agent starts.
        """
        cls._quota_limit = max(1, max_concurrent)
        cls._quota_semaphore = asyncio.Semaphore(cls._quota_limit)
        logger.info(
            "Gemini quota pool configured",
            max_concurrent=cls._quota_limit,
        )

    @classmethod
    def _get_quota_semaphore(cls) -> asyncio.Semaphore:
        """Return (and lazily create) the shared concurrency semaphore."""
        if cls._quota_semaphore is None:
            cls._quota_semaphore = asyncio.Semaphore(cls._quota_limit)
        return cls._quota_semaphore

    def __init__(self, config: Settings):
        self.api_key: str | None = config.gemini_api_key
        self.model: str = getattr(config, "gemini_model", _DEFAULT_MODEL)
        # Build ordered fallback chain from comma-separated config string.
        # Duplicates and the primary model itself are removed; order is preserved.
        _chain_str: str = getattr(
            config, "gemini_fallback_models", _DEFAULT_FALLBACK_CHAIN
        )
        seen: set[str] = {self.model}
        _chain: list[str] = []
        for _raw in _chain_str.split(","):
            _m = _raw.strip()
            if _m and _m not in seen:
                seen.add(_m)
                _chain.append(_m)
        self.fallback_chain: list[str] = _chain
        self.timeout: float = getattr(config, "gemini_timeout", 40.0)

        # Check if key is missing or is the default placeholder from .env.example
        is_placeholder = self.api_key and "your_gemini_key" in self.api_key
        self._enabled = bool(self.api_key) and not is_placeholder

        # Circuit breaker: opens after 3 consecutive failures, recovers after 120s
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=120.0,
            half_open_max_calls=1
        )

    # ------------------------------------------------------------------ #
    #  Startup model validation                                            #
    # ------------------------------------------------------------------ #

    async def validate_model_availability(self) -> dict[str, bool]:
        """
        Check which models in the configured cascade are accessible on this API key.

        Uses the Gemini models.list endpoint to retrieve the set of available
        models without burning any quota. Models that are not available are
        removed from the fallback chain so the cascade doesn't hit avoidable 404s.

        Returns a dict mapping model name → available (bool).
        Called once at API startup.
        """
        if not self._enabled:
            logger.info("Gemini not configured — skipping model availability check")
            return {}

        available_models: set[str] = set()
        try:
            url = f"{_GEMINI_API_BASE}/models?key={self.api_key}&pageSize=100"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    for m in data.get("models", []):
                        # model name is like "models/gemini-2.5-flash"
                        name = m.get("name", "").replace("models/", "")
                        if name:
                            available_models.add(name)
                elif resp.status_code == 401:
                    logger.warning("Gemini API key is invalid — all Gemini grounding will be skipped")
                    self._enabled = False
                    return {}
                else:
                    logger.warning("Gemini models.list returned unexpected status", status=resp.status_code)
                    return {}
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            logger.warning("Gemini models.list unreachable at startup (will retry at runtime)", error=str(e))
            return {}
        except Exception as e:
            logger.warning("Gemini model validation failed", error=str(e))
            return {}

        # Validate configured cascade
        all_models = [self.model] + self.fallback_chain
        results: dict[str, bool] = {}
        unavailable: list[str] = []
        for model in all_models:
            # Strip any "models/" prefix for comparison
            short = model.replace("models/", "")
            is_available = short in available_models or model in available_models
            results[model] = is_available
            if not is_available:
                unavailable.append(model)

        if unavailable:
            logger.warning(
                "Gemini models not available on this API key — they will be skipped in cascade",
                unavailable=unavailable,
                available_count=len(available_models),
            )
            # Remove unavailable models from fallback chain
            self.fallback_chain = [m for m in self.fallback_chain if m not in unavailable]
            # If primary model is unavailable, promote first available fallback
            if self.model in unavailable and self.fallback_chain:
                self.model = self.fallback_chain.pop(0)
                logger.warning("Primary Gemini model unavailable — promoted fallback", new_primary=self.model)
            elif self.model in unavailable:
                logger.warning("No Gemini models available — disabling Gemini grounding")
                self._enabled = False
        else:
            logger.info("All configured Gemini models validated", models=all_models)

        return results

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
            finding = await self._local_forensic_fallback(file_path)
            finding.analysis_type = "file_content_identification"
            return finding

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
            finding = await self._local_forensic_fallback(file_path)
            finding.analysis_type = "manipulation_cross_validation"
            return finding

        findings_text = (
            "\n".join(f"- {f}" for f in preliminary_findings)
            if preliminary_findings
            else "None yet."
        )
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
            finding = await self._local_forensic_fallback(file_path)
            finding.analysis_type = "object_scene_analysis"
            return finding

        detections_text = (
            "\n".join(f"- {d}" for d in preliminary_detections)
            if preliminary_detections
            else "None yet."
        )
        prompt = (
            "You are a forensic scene analyst. Preliminary ML object detection found:\n"
            f"{detections_text}\n\n"
            "Examine this file and identify all "
            "relevant objects and contextual features. Specially confirm or correct the preliminary detections in your response. "
            "Address:\n\n"
            "1. VALIDATED_OBJECTS: List every clearly identifiable object. "
            "Be precise. Use a list of strings.\n"
            "2. WEAPONS_CONTRABAND: Are any weapons, dangerous items, or contraband visible? "
            "Be specific. If none, say 'None detected'.\n"
            "3. SCENE_COHERENCE: Is the scene physically plausible? "
            "Do lighting, shadows, scale, and perspective all make sense together?\n"
            "4. COMPOSITING_SIGNALS: Any signs that objects were digitally inserted "
            "into the scene (edge artifacts, shadow inconsistency, scale mismatch)?\n"
            "5. CONTEXTUAL_FLAGS: Anything contextually unusual or suspicious?\n"
            "6. CONFIDENCE: Your confidence (0.0-1.0).\n\n"
            "Respond ONLY with valid JSON:\n"
            '{"validated_objects": ["items"], "weapons_contraband": ["items"], '
            '"scene_coherence": "description", "compositing_signals": ["signals"], '
            '"contextual_flags": ["flags"], "confidence": 0.95}'
        )

        return await self._run_vision_analysis(
            file_path=file_path,
            prompt=prompt,
            analysis_type="object_scene_analysis",
        )

    async def deep_forensic_analysis(
        self,
        file_path: str,
        exif_summary: dict[str, Any] | None = None,
        model_hint: str | None = None,
        signal_callback: Any | None = None,
    ) -> GeminiVisionFinding:
        """
        Comprehensive deep forensic analysis — single call covering everything.

        Used by Agent 1 (Image Integrity), Agent 3 (Object/Weapon), and
        Agent 5 (Metadata/Context) during the deep analysis pass for image files.

        Returns a single rich finding that covers:
          - What the file IS (content type: photo, screenshot, web UI, document,
            AI-generated, etc.)
          - Full scene description including contextual meaning
          - All visible text (OCR-quality extraction)
          - Object inventory: every identifiable item, device, weapon, or person
          - Interface/UI identification (web app, mobile UI, desktop GUI, etc.)
          - Contextual narrative: what is going on / what action is depicted
          - Manipulation signals and forensic anomalies
          - Metadata cross-validation against visual cues (if exif_summary provided)
          - Overall authenticity verdict and confidence
        """
        if not self._enabled:
            return await self._local_forensic_fallback(file_path, exif_summary)

        if signal_callback:
            maybe_awaitable = signal_callback("Gemini deep forensic analysis started.")
            if hasattr(maybe_awaitable, "__await__"):
                await maybe_awaitable

        meta_section = ""
        if exif_summary:
            meta_text = json.dumps(exif_summary, indent=2, default=str)
            meta_section = (
                f"\n\nEXIF / metadata extracted from file:\n{meta_text}\n"
                "Cross-validate these claims against what you visually observe."
            )

        prompt = (
            "You are a senior forensic analyst performing a comprehensive examination "
            "of this file. Provide a thorough, court-grade analysis covering ALL of "
            "the following areas:\n\n"
            "1. CONTENT_TYPE: Classify the file precisely. Examples: 'photograph taken "
            "with a camera', 'screenshot of a web browser', 'screenshot of a mobile app', "
            "'scanned document', 'AI-generated image', 'screen recording frame', "
            "'screenshot of a desktop application', 'photograph of a physical document', "
            "'infographic', 'meme', etc. Be specific.\n\n"
            "2. SCENE_DESCRIPTION: Describe in detail what you see. What is the setting? "
            "What is happening? What is the overall context or narrative? If it is a "
            "screenshot, describe what application/website is shown and what action is "
            "being performed or displayed.\n\n"
            "3. EXTRACTED_TEXT: Extract ALL visible text from the image verbatim, "
            "preserving structure. Include UI labels, headings, body text, captions, "
            "URLs, usernames, timestamps, error messages, form fields, table data, "
            "watermarks — everything. If no text is present, return an empty list.\n\n"
            "4. DETECTED_OBJECTS: List every identifiable object, device, or item. "
            "Include: computers/laptops/phones/tablets, weapons (knives, firearms, etc.), "
            "vehicles, faces/people (describe without identifying), documents/IDs, "
            "currency, drugs/substances, clothing, furniture, logos/brands. "
            "For each object include its approximate location in the frame "
            "(e.g. 'laptop, center-left'). If none beyond the main scene, say 'None'.\n\n"
            "5. INTERFACE_IDENTIFICATION: If the image shows a digital interface, "
            "identify it precisely: application name (if recognisable), type of interface "
            "(web browser, mobile app, desktop app, terminal, map, social media, "
            "messaging, email client, etc.), and what the user is doing or what data "
            "is displayed.\n\n"
            "6. CONTEXTUAL_NARRATIVE: In 2-4 sentences, explain what is going on in this "
            "image. What event, activity, or situation does it depict? What is the forensic "
            "significance of its content?\n\n"
            "7. MANIPULATION_SIGNALS: List any visual forensic red flags: inconsistent "
            "lighting/shadows, copy-paste artifacts, edge blending issues, resolution "
            "inconsistencies, AI generation artefacts, metadata-visual mismatches, "
            "signs of cropping/compositing. If none, return empty list.\n\n"
            "8. METADATA_VISUAL_CONSISTENCY: If EXIF data is provided, assess whether "
            "the visual content is consistent with the claimed timestamp, location, and "
            "device. If no EXIF provided, return 'No metadata provided for cross-validation'.\n\n"
            "9. AUTHENTICITY_VERDICT: One of 'AUTHENTIC', 'SUSPICIOUS', 'LIKELY_MANIPULATED', "
            "'AI_GENERATED', or 'CANNOT_DETERMINE'.\n\n"
            "10. CONTRADICTION_AUDIT: Specifically list any contradictions between the "
            "provided tool results/metadata and what you see. For example: if EXIF says "
            "it is a 'Samsung S24' photo but you see 'iPhone' UI artifacts, or if the "
            "GPS says 'Dubai' but you see 'London' landmarks.\n\n"
            "11. CONFIDENCE: Your overall confidence in this analysis (0.0-1.0).\n\n"
            f"{meta_section}\n\n"
            "Respond ONLY with valid JSON matching this exact schema (no markdown, no "
            "preamble, just the JSON object):\n"
            "{\n"
            '  "content_type": "precise description",\n'
            '  "scene_description": "detailed description",\n'
            '  "extracted_text": ["verbatim text items"],\n'
            '  "detected_objects": ["object at location"],\n'
            '  "interface_identification": "app name and type",\n'
            '  "contextual_narrative": "depicted event and significance",\n'
            '  "manipulation_signals": ["forensic anomalies"],\n'
            '  "metadata_visual_consistency": "consistency assessment",\n'
            '  "contradiction_audit": ["specific contradiction identified"],\n'
            '  "authenticity_verdict": "AUTHENTIC",\n'
            '  "confidence": 0.95\n'
            "}"
        )

        return await self._run_vision_analysis(
            file_path=file_path,
            prompt=prompt,
            analysis_type="deep_forensic_analysis",
            model_hint=model_hint,
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
            finding = await self._local_forensic_fallback(file_path, metadata_summary)
            finding.analysis_type = "metadata_visual_consistency"
            return finding

        meta_text = (
            json.dumps(metadata_summary, indent=2, default=str)
            if metadata_summary
            else "{}"
        )
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
        model_hint: str | None = None,
    ) -> GeminiVisionFinding:
        """Encode file and call Gemini generateContent, parse structured result."""
        # Check circuit breaker before attempting API call
        if self._circuit_breaker.state == "OPEN":
            logger.warning(
                f"Gemini circuit breaker is OPEN — falling back to local analysis for {analysis_type}"
            )
            finding = await self._local_forensic_fallback(file_path)
            finding.analysis_type = analysis_type
            return finding

        t0 = time.monotonic()

        try:
            encoded, mime_type = self._encode_file(file_path)
        except Exception as exc:
            logger.warning(f"Gemini: failed to encode file {file_path}: {exc}")
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
                {"inlineData": {"mimeType": mime_type, "data": encoded}},
                {"text": prompt},
            ]
        else:
            # Non-vision file type — text-only analysis
            parts = [{"text": f"[Non-visual file, MIME: {mime_type}]\n\n{prompt}"}]

        generation_config: dict = {
            "temperature": 0.1,
            "maxOutputTokens": 8192,
            # NOTE: responseMimeType="application/json" is intentionally omitted.
            # When set alongside multimodal (image) input it causes Gemini 2.x to
            # enter a JSON-generation mode that suppresses visual perception,
            # producing "no visual content detected" responses even for valid images.
            # We rely on our own _parse_response() JSON extraction instead.
        }

        # Thinking models (2.5+, 3+) support thinkingConfig.
        # Enable chain-of-thought with a modest budget for forensic analysis —
        # visual reasoning improves accuracy for manipulation detection.
        # thinkingBudget=0 disables CoT; 1024 gives enough for structured reasoning
        # without excessive latency. Models that don't support it (2.0-) skip silently.
        if any(p in self.model for p in _THINKING_MODEL_PREFIXES):
            generation_config["thinkingConfig"] = {"thinkingBudget": 1024}

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": generation_config,
        }

        # ── Cascade: primary → fallback_chain ────────────────────────────
        # Build per-model (payload, url) pairs up-front so each model gets
        # the correct thinkingConfig for its generation family.
        def _model_entry(m: str, primary_payload: dict | None = None) -> tuple:
            url = f"{_GEMINI_API_BASE}/models/{m}:generateContent"
            if primary_payload is not None:
                return (m, primary_payload, url)
            gen_cfg: dict = {"temperature": 0.1, "maxOutputTokens": 8192}
            if any(p in m for p in _THINKING_MODEL_PREFIXES):
                gen_cfg["thinkingConfig"] = {"thinkingBudget": 1024}
            return (
                m,
                {"contents": [{"parts": parts}], "generationConfig": gen_cfg},
                url,
            )

        # Reorder cascade based on model_hint if provided
        primary_model = model_hint if model_hint and model_hint != self.model else self.model
        fallback_models = [m for m in self.fallback_chain if m != primary_model]
        if model_hint and model_hint == self.model: # hint is already primary
            pass
        elif model_hint and model_hint not in self.fallback_chain:
            # Hint is external/new, add it to the front
            pass
        elif model_hint:
            # Hint was in fallback, promote it
            if self.model != primary_model:
                fallback_models = [self.model] + [m for m in self.fallback_chain if m != primary_model]

        models_to_try = [_model_entry(primary_model, payload if primary_model == self.model else None)] + [
            _model_entry(m) for m in fallback_models
        ]

        last_exc: Exception = RuntimeError("no models attempted")
        # Acquire the process-wide quota semaphore before issuing any HTTP call.
        # This bounds concurrent Gemini requests across all agents/instances so
        # we don't saturate the free-tier RPM quota when 5 agents run in parallel.
        async with self._get_quota_semaphore():
            for attempt_model, attempt_payload, attempt_url in models_to_try:
                try:
                    m_t0 = time.monotonic()
                    raw_text = await asyncio.wait_for(
                        self._post_with_retry(
                            attempt_url,
                            attempt_payload,
                            model_name=attempt_model,
                        ),
                        timeout=self.timeout + 5,
                    )
                    m_latency = (time.monotonic() - m_t0) * 1000
                    finding = self._parse_response(raw_text, analysis_type, m_latency)
                    if attempt_model != self.model:
                        finding.model_used = attempt_model
                        finding.caveat = (
                            f"[Fallback: {attempt_model} — primary {self.model} unavailable] "
                            + finding.caveat
                        )
                    # Record success in circuit breaker
                    self._circuit_breaker.record_success()
                    return finding
                except _ModelUnavailableError as mue:
                    logger.warning(
                        f"Gemini model {attempt_model} not available — skipping to next. ({mue})"
                    )
                    last_exc = mue
                except Exception as exc:
                    logger.warning(
                        f"Gemini model {attempt_model} failed — trying next in chain. ({exc})"
                    )
                    last_exc = exc

        latency_ms = (time.monotonic() - t0) * 1000
        logger.error(
            f"All Gemini models exhausted for {analysis_type}. "
            f"Chain: {[self.model] + self.fallback_chain}. Last error: {last_exc}"
        )
        # Record failure in circuit breaker
        self._circuit_breaker.record_failure()
        return GeminiVisionFinding(
            analysis_type=analysis_type,
            model_used=self.model,
            content_description="",
            error=f"All Gemini models exhausted: {last_exc}",
            confidence=0.0,
            court_defensible=False,
            latency_ms=latency_ms,
        )

    async def _post_with_retry(
        self,
        url: str,
        payload: dict,
        model_name: str | None = None,
    ) -> str:
        """POST to Gemini API with exponential-backoff retry."""
        headers = {"x-goog-api-key": self.api_key}
        active_model = model_name or self.model
        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    if resp.status_code != 200:
                        error_detail = ""
                        try:
                            error_detail = resp.text
                        except Exception as e:
                            logger.debug("Could not read Gemini error response body", error=str(e))

                        # 404 means the model doesn't exist on this API key —
                        # raise immediately (no backoff) so the cascade loop
                        # can skip to the next model without waiting.
                        if resp.status_code == 404:
                            raise _ModelUnavailableError(
                                f"Model not found (404): {error_detail[:300]}"
                            )
                        # Also treat 400 "model not found" body as unavailable.
                        if resp.status_code == 400 and (
                            "not found" in error_detail.lower()
                            or "does not exist" in error_detail.lower()
                            or "not support" in error_detail.lower()
                        ):
                            raise _ModelUnavailableError(
                                f"Model unavailable (400): {error_detail[:300]}"
                            )
                        if resp.status_code == 503:
                            logger.warning(
                                f"Gemini model {active_model} unavailable (503) - cascading to next model. "
                                f"Detail: {error_detail[:200]}"
                            )
                            raise _ModelUnavailableError(
                                f"Model unavailable (503): {error_detail[:300]}"
                            )
                        if resp.status_code == 429:
                            # Quota exhausted for this model — cascade to next model
                            # instead of retrying on the same model (which will keep failing).
                            # Distinguish between rate-limit (retry) and quota-exceeded (cascade):
                            # If the error says "quota" or we've already retried once, cascade.
                            is_quota = "quota" in error_detail.lower()
                            if is_quota or attempt > 0:
                                logger.warning(
                                    f"Gemini model {self.model} quota exceeded (429) — cascading to next model. "
                                    f"Detail: {error_detail[:200]}"
                                )
                                raise _ModelUnavailableError(
                                    f"Quota exceeded (429): {error_detail[:300]}"
                                )
                            wait = _BASE_BACKOFF * (2**attempt)
                            logger.warning(
                                f"Gemini API rate limited (429) for model {self.model}. "
                                f"Retrying in {wait:.1f}s (attempt {attempt + 1}/{_MAX_RETRIES})..."
                            )
                            await asyncio.sleep(wait)
                            continue
                        elif resp.status_code in {500, 502, 503, 504}:
                            wait = _BASE_BACKOFF * (2**attempt)
                            logger.warning(
                                f"Gemini API error {resp.status_code} for model {self.model}. "
                                f"Retrying in {wait:.1f}s (attempt {attempt + 1}/{_MAX_RETRIES})..."
                            )
                            await asyncio.sleep(wait)
                            continue
                        else:
                            logger.error(
                                f"Gemini API non-retryable error {resp.status_code} for model {self.model}. "
                                f"Body: {error_detail[:1000]}"
                            )
                            if resp.status_code == 400:
                                safe_err = error_detail[:200].replace('"', "'").replace("\n", " ")
                                return '{"error": "' + safe_err + '", "content_description": "Gemini rejected the payload (400 Bad Request) — analysis skipped.", "confidence": 0, "file_type_assessment": "unknown"}'
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
            except (httpx.TimeoutException, httpx.ConnectError) as net_err:
                if attempt < _MAX_RETRIES - 1:
                    wait = _BASE_BACKOFF * (2**attempt)
                    logger.warning(
                        f"Gemini networking error ({type(net_err).__name__}) - retrying in {wait:.1f}s..."
                    )
                    await asyncio.sleep(wait)
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
            # Strip markdown fences and extract the first JSON object from the response.
            # Gemini 2.x sometimes wraps JSON in prose or ```json ... ``` blocks.
            cleaned = raw_text.strip()
            if "```" in cleaned:
                # Extract content between first ``` pair
                import re as _re

                fence_match = _re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
                if fence_match:
                    cleaned = fence_match.group(1).strip()
            # If it still doesn't start with '{', search for the first '{...}' block
            if not cleaned.startswith("{"):
                import re as _re

                obj_match = _re.search(r"\{[\s\S]*\}", cleaned)
                if obj_match:
                    cleaned = obj_match.group(0)
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning(f"Gemini: failed to parse JSON response: {exc}")
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

        # Build unified description — handle all response shapes including deep_forensic_analysis
        descriptions = []
        for key in (
            "scene_description",
            "visual_confirmation",
            "authenticity_assessment",
            "overall_verdict",
            "scene_coherence",
            "contextual_narrative",
        ):
            val = data.get(key)
            if val and isinstance(val, str):
                descriptions.append(val)

        # deep_forensic_analysis extras: interface + authenticity verdict
        iface = data.get("interface_identification", "")
        if (
            iface
            and isinstance(iface, str)
            and iface.lower() not in ("none", "n/a", "")
        ):
            descriptions.insert(0, f"Interface: {iface}")
        verdict = data.get("authenticity_verdict", "")
        if verdict and isinstance(verdict, str):
            descriptions.append(f"Verdict: {verdict}")
        meta_consistency = data.get("metadata_visual_consistency", "")
        if (
            meta_consistency
            and isinstance(meta_consistency, str)
            and meta_consistency.lower() not in ("none", "n/a", "")
        ):
            descriptions.append(f"Metadata consistency: {meta_consistency}")

        # Gather manipulation and anomaly signals
        manipulation_signals: list[str] = []
        for key in (
            "manipulation_signals",
            "additional_anomalies",
            "compositing_signals",
            "content_provenance_flags",
        ):
            items = data.get(key, [])
            if isinstance(items, list):
                manipulation_signals.extend(str(i) for i in items if i)
            elif isinstance(items, str) and items.lower() not in (
                "none",
                "none detected",
                "",
            ):
                manipulation_signals.append(items)

        # Gather contextual anomalies
        contextual_anomalies: list[str] = []
        for key in ("contextual_flags",):
            items = data.get(key, [])
            if isinstance(items, list):
                contextual_anomalies.extend(str(i) for i in items if i)

        # Gather detected objects (all variants)
        detected_objects: list[str] = []
        for key in ("detected_objects", "validated_objects", "weapons_contraband"):
            items = data.get(key, [])
            if isinstance(items, list):
                detected_objects.extend(str(i) for i in items if i)

        # Extracted text (deep_forensic_analysis only)
        extracted_text_items: list[str] = []
        raw_text_items = data.get("extracted_text", [])
        if isinstance(raw_text_items, list):
            extracted_text_items = [str(t) for t in raw_text_items if t]
        elif isinstance(raw_text_items, str) and raw_text_items:
            extracted_text_items = [raw_text_items]

        file_type = data.get("content_type", "")

        # Build human-readable description (cap at 3 desc parts to stay concise)
        desc_parts = descriptions[:3]
        if manipulation_signals:
            none_signals = [
                s
                for s in manipulation_signals
                if s.lower() not in ("none detected", "none")
            ]
            if none_signals:
                desc_parts.append(
                    f"Manipulation signals: {'; '.join(none_signals[:3])}"
                )
        content_description = (
            " | ".join(desc_parts) if desc_parts else "Visual analysis complete."
        )

        finding = GeminiVisionFinding(
            analysis_type=analysis_type,
            model_used=self.model,
            content_description=content_description,
            manipulation_signals=[
                s
                for s in manipulation_signals
                if s.lower() not in ("none detected", "none")
            ],
            detected_objects=[
                o
                for o in detected_objects
                if o.lower() not in ("none detected", "none")
            ],
            contextual_anomalies=contextual_anomalies,
            file_type_assessment=file_type,
            confidence=confidence,
            court_defensible=True,
            raw_response=raw_text,
            latency_ms=latency_ms,
            _extracted_text=extracted_text_items,
            _interface_identification=iface,
            _contextual_narrative=data.get("contextual_narrative", ""),
            _authenticity_verdict=verdict,
            _metadata_visual_consistency=meta_consistency,
        )
        return finding

    @staticmethod
    def _encode_file(file_path: str) -> tuple[str, str]:
        """
        Read a file and return (base64_data, mime_type).

        Images larger than 3 MB are downscaled before encoding so they fit
        comfortably within Gemini's inline-data size limits and avoid the
        silent "no visual content detected" failure that occurs when the
        base64 payload exceeds ~4 MB in a single generateContent call.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Evidence file not found: {file_path}")

        # Detect MIME type
        mime_type, _ = mimetypes.guess_type(str(path))
        if not mime_type:
            ext = path.suffix.lower()
            ext_map = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".webp": "image/webp",
                ".gif": "image/gif",
                ".bmp": "image/bmp",
                ".pdf": "application/pdf",
                ".mp4": "video/mp4",
                ".mov": "video/quicktime",
                ".wav": "audio/wav",
                ".mp3": "audio/mpeg",
            }
            mime_type = ext_map.get(ext, "application/octet-stream")

        with open(file_path, "rb") as f:
            raw = f.read()

        # Resize images that are too large for reliable inline-data delivery.
        # Gemini's effective inline limit is ~4 MB of base64 (~3 MB raw).
        # We only resize image types; PDFs and other formats are sent as-is.
        _IMAGE_MIME_TYPES = {
            "image/jpeg",
            "image/png",
            "image/webp",
            "image/bmp",
            "image/gif",
        }
        _MAX_RAW_BYTES = 3 * 1024 * 1024  # 3 MB
        if mime_type in _IMAGE_MIME_TYPES and len(raw) > _MAX_RAW_BYTES:
            try:
                import io

                from PIL import Image as _PImage

                img = _PImage.open(io.BytesIO(raw))
                # Convert palette/RGBA modes that don't survive JPEG re-encode
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                # Scale down proportionally until raw size is under limit
                scale = (_MAX_RAW_BYTES / len(raw)) ** 0.5
                new_w = max(256, int(img.width * scale))
                new_h = max(256, int(img.height * scale))
                img = img.resize((new_w, new_h), _PImage.LANCZOS)
                buf = io.BytesIO()
                save_format = "JPEG" if mime_type == "image/jpeg" else "PNG"
                save_mime = "image/jpeg" if save_format == "JPEG" else "image/png"
                img.save(buf, format=save_format, quality=85)
                raw = buf.getvalue()
                mime_type = save_mime
                logger.debug(
                    f"Gemini: resized large image {path.name} to {new_w}×{new_h} "
                    f"({len(raw) // 1024} KB) for inline encoding"
                )
            except Exception as resize_exc:
                # If resize fails, fall through and send original — better than failing entirely
                logger.warning(
                    f"Gemini: image resize failed for {file_path}: {resize_exc}"
                )

        # Handle Audio Files: Convert to Spectrogram Image for Gemini "Vision"
        if mime_type.startswith("audio/"):
            try:
                spectrogram_raw, spectrogram_mime = GeminiVisionClient._generate_spectrogram(file_path)
                return base64.b64encode(spectrogram_raw).decode("utf-8"), spectrogram_mime
            except Exception as audio_err:
                logger.warning(f"Gemini: spectrogram generation failed for {file_path}: {audio_err}")
                # Fall through to raw binary (Gemini 1.5+ sometimes handles raw audio)

        return base64.b64encode(raw).decode("utf-8"), mime_type

    @staticmethod
    def _generate_spectrogram(file_path: str) -> tuple[bytes, str]:
        """
        Generate a Mel-spectrogram image from an audio file.
        This allows Gemini 'Vision' models to analyze audio characteristics
        visually (detecting splices, frequency anomalies, and GAN artifacts).
        """
        import io

        import numpy as np
        import soundfile as sf
        from scipy import signal
        from PIL import Image as _PImage

        # Load audio without librosa. The Gemini path should be lightweight and
        # robust even when optional numba/librosa hooks are unavailable.
        y, sr = sf.read(file_path, dtype="float32", always_2d=False)
        if y.ndim > 1:
            y = y.mean(axis=1)
        if sr <= 0 or y.size == 0:
            raise ValueError("empty or invalid audio stream")
        y = y[: int(sr * 120)]  # cap at 2min

        nperseg = min(2048, max(256, int(sr * 0.05)))
        noverlap = min(nperseg - 1, nperseg // 2)
        _, _, spec = signal.spectrogram(
            y,
            fs=sr,
            window="hann",
            nperseg=nperseg,
            noverlap=noverlap,
            scaling="spectrum",
            mode="magnitude",
        )
        if spec.size == 0:
            raise ValueError("spectrogram produced no bins")
        spec_db = 20.0 * np.log10(np.maximum(spec, 1e-10))

        # Normalize to 0-255 for image conversion
        value_range = float(spec_db.max() - spec_db.min())
        if value_range <= 1e-9:
            img_data = np.zeros_like(spec_db, dtype=np.uint8)
        else:
            img_data = ((spec_db - spec_db.min()) / value_range * 255).astype(np.uint8)

        # Create image (greyscale spectrogram map)
        # Flip vertically so low frequencies are at the bottom
        img = _PImage.fromarray(np.flipud(img_data), mode="L")

        # Resize to a reasonable vision-friendly size (e.g., 1024 width)
        if img.width > 2048:
            new_w = 2048
            new_h = int(img.height * (new_w / img.width))
            img = img.resize((new_w, new_h), _PImage.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue(), "image/png"

    async def _local_forensic_fallback(
        self,
        file_path: str,
        exif_summary: dict[str, Any] | None = None,
    ) -> GeminiVisionFinding:
        """
        Local OpenCV/PIL fallback when Gemini API key is not configured.
        Extracts meaningful forensic signals from the image without any network call:
        - Image dimensions, colour stats, channel analysis
        - Basic content type classification from image statistics
        - Noise level, sharpness, compression artifacts
        - EXIF metadata cross-check if provided
        """
        t0 = time.monotonic()
        Path(file_path)

        try:
            import numpy as np
            from PIL import Image as PILImage

            img = PILImage.open(file_path).convert("RGB")
            arr = np.array(img, dtype=np.float32)
            h, w = arr.shape[:2]

            # Colour statistics
            arr.mean(axis=(0, 1)).tolist()
            std_rgb = arr.std(axis=(0, 1)).tolist()
            brightness = float(arr.mean())

            # Sharpness via Laplacian variance
            import cv2

            gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
            laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            is_blurry = laplacian_var < 100

            # Noise estimate via high-frequency residual
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            noise_residual = float(
                np.abs(gray.astype(float) - blurred.astype(float)).mean()
            )

            # JPEG artifact check: blockiness score
            block_diff = (
                float(np.abs(np.diff(gray.astype(float), axis=0)[7::8].mean()))
                if h > 16
                else 0.0
            )
            likely_jpeg_compressed = block_diff > 3.0

            # Colour uniformity (synthetic/AI images tend to have smoother distributions)
            channel_balance = max(std_rgb) - min(std_rgb)
            possibly_synthetic = channel_balance < 10 and laplacian_var > 500

            content_type = "unknown image"
            if w > 1200 and h > 800 and laplacian_var > 300:
                content_type = "high-resolution photograph"
            elif laplacian_var < 80:
                content_type = "blurry or low-quality image"
            elif possibly_synthetic:
                content_type = "possibly synthetic or AI-generated image"
            elif likely_jpeg_compressed and block_diff > 8:
                content_type = "heavily JPEG-compressed image"
            else:
                content_type = "digital image"

            scene_desc = (
                f"{content_type.capitalize()}, {w}×{h}px. "
                f"Mean brightness {brightness:.0f}/255 ({'dark' if brightness < 80 else 'bright' if brightness > 180 else 'mid-tone'}). "
                f"Sharpness score {laplacian_var:.0f} ({'blurry' if is_blurry else 'sharp'}). "
                f"Estimated noise level {noise_residual:.2f}."
            )

            manipulation_signals = []
            if noise_residual > 8:
                manipulation_signals.append(
                    f"Elevated noise residual ({noise_residual:.2f}) — possible double-compression or splicing"
                )
            if block_diff > 8:
                manipulation_signals.append(
                    f"Strong JPEG block boundary artifacts (score {block_diff:.1f}) — re-encoding likely"
                )
            if possibly_synthetic:
                manipulation_signals.append(
                    "Channel balance and sharpness profile consistent with synthetic/AI-generated content"
                )

            meta_notes = []
            if exif_summary:
                dt = exif_summary.get("datetime_original", "")
                make = exif_summary.get("camera_make", "")
                if make:
                    meta_notes.append(
                        f"Claimed device: {make} {exif_summary.get('camera_model', '')}"
                    )
                if dt:
                    meta_notes.append(f"Claimed capture time: {dt}")
                if not make and not dt:
                    meta_notes.append(
                        "No device or timestamp in EXIF — provenance cannot be verified from metadata"
                    )

            # Attempt lightweight OCR to extract any visible text
            ocr_text_lines: list[str] = []
            try:
                import pytesseract

                ocr_raw = pytesseract.image_to_string(img, config="--psm 3").strip()
                if ocr_raw:
                    ocr_text_lines = [
                        ln.strip() for ln in ocr_raw.splitlines() if len(ln.strip()) > 2
                    ][:10]
            except (OSError, RuntimeError) as e:
                logger.debug("Tesseract OCR unavailable in local fallback", error=str(e))
            except Exception as e:
                logger.debug("Tesseract OCR failed in local fallback", error=str(e))
            # EasyOCR fallback
            if not ocr_text_lines:
                try:
                    from tools.ocr_tools import _get_easyocr_reader

                    _reader = _get_easyocr_reader()
                    if _reader is not None:
                        _results = _reader.readtext(file_path, detail=0)
                        ocr_text_lines = [
                            str(t).strip() for t in _results if len(str(t).strip()) > 2
                        ][:10]
                except (ImportError, OSError, RuntimeError) as e:
                    logger.debug("EasyOCR unavailable in local fallback", error=str(e))
                except Exception as e:
                    logger.debug("EasyOCR failed in local fallback", error=str(e))

            ocr_summary = ""
            if ocr_text_lines:
                ocr_summary = (
                    f" Text visible in image: {' | '.join(ocr_text_lines[:6])}."
                )

            narrative = (
                f"Local forensic analysis (set GEMINI_API_KEY for full AI vision). {scene_desc}"
                + ocr_summary
                + " "
                + (
                    f"Metadata: {'; '.join(meta_notes)}."
                    if meta_notes
                    else "No EXIF metadata available."
                )
            )

            latency_ms = (time.monotonic() - t0) * 1000
            finding = GeminiVisionFinding(
                analysis_type="deep_forensic_analysis",
                model_used="local_opencv_fallback",
                content_description=narrative,
                manipulation_signals=manipulation_signals,
                detected_objects=[],
                contextual_anomalies=[],
                file_type_assessment=content_type,
                confidence=0.55,
                court_defensible=True,
                caveat=(
                    "Local fallback analysis — GEMINI_API_KEY not set. "
                    "Set GEMINI_API_KEY for AI-powered deep visual forensics. "
                    "Results are based on local image statistics only."
                ),
                raw_response="",
                latency_ms=latency_ms,
                _extracted_text=ocr_text_lines,
                _interface_identification="",
                _contextual_narrative=narrative,
                _authenticity_verdict="SUSPICIOUS"
                if manipulation_signals
                else "CANNOT_DETERMINE",
                _metadata_visual_consistency="; ".join(meta_notes)
                if meta_notes
                else "No EXIF for cross-validation",
            )
            return finding

        except Exception as exc:
            latency_ms = (time.monotonic() - t0) * 1000
            logger.warning(f"Local forensic fallback failed: {exc}")
            return GeminiVisionFinding(
                analysis_type="deep_forensic_analysis",
                model_used="local_fallback_error",
                content_description=f"Local analysis failed: {exc}",
                confidence=0.0,
                court_defensible=False,
                error=str(exc),
                latency_ms=latency_ms,
            )

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

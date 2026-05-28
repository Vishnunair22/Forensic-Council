Forensic Council — Resilience Plan (Free-Tier, No-GPU)
0. Design contract
Every existing call site that uses GeminiVisionClient(...) keeps working unchanged. We wrap it with VisionRouter (same public methods + same GeminiVisionFinding return type). Existing tests and arbiter.py degradation_flags logic continue to work without edits.

Order of fallback (vision):

gemini-2.5-flash → gemini-2.5-flash-lite → gemini-2.0-flash → gemini-2.0-flash-lite
   ↓  (all cascaded, all failed/quota-blocked)
Groq Vision  (meta-llama/llama-4-scout-17b-16e-instruct OR llama-3.2-90b-vision-preview)
   ↓
OpenRouter Vision (optional; default OFF):
   meta-llama/llama-3.2-11b-vision-instruct:free
   → qwen/qwen2.5-vl-7b-instruct:free
   → google/gemma-3-12b-it:free
   ↓
LocalEnsemble  (DETR + CLIP + EasyOCR + ELA/PRNU reuse + OpenCV stats)
   ↓
LegacyOpenCV   (= today's `_local_forensic_fallback`)
Order of fallback (text/synthesis):

Groq (LLM_MODEL → LLM_FALLBACK_MODELS)
   ↓
Gemini text (gemini_model)
   ↓
Cerebras (llama3.3-70b)        [NEW; default OFF if no key]
   ↓
Template (deterministic)
Templates also run in parallel with the LLM call (asyncio.wait FIRST_COMPLETED), so even when the LLM eventually succeeds we already have a usable fallback ready and emit it immediately if the LLM exceeds 12 s.

1. Files to create (4) and files to modify (8)
CREATE
Path	Purpose
apps/api/core/vision_router.py	Public vision facade — same surface as GeminiVisionClient, fans out to Gemini → Groq Vision → OpenRouter → LocalEnsemble
apps/api/core/vision_fallback_ensemble.py	Fuses DETR + CLIP + OCR + ELA/PRNU into a GeminiVisionFinding
apps/api/api/routes/health_providers.py	GET /api/v1/health/providers
apps/api/tests/integration/test_provider_cascade.py	A/B/C/D scenario tests
MODIFY
Path	Change
apps/api/core/config.py	+ groq_vision_*, openrouter_*, cerebras_*, vision_provider_chain, text_provider_chain settings
apps/api/.env.example (it lives at repo root)	document new keys
apps/api/agents/mixins/synthesis.py	swap GeminiVisionClient(...) → VisionRouter(...)
apps/api/core/llm_client.py	symmetric cross-provider for synthesis + Cerebras + remove 30 s sleep
apps/api/agents/arbiter_narrative.py	run t_arbiter() and _template_all in parallel via asyncio.wait
apps/api/core/provider_quota_guard.py	(no code change, just configured in main.py for new providers)
apps/api/api/main.py	configure new providers' quota + register /health/providers route
apps/api/scripts/verify_llm_keys.py	add Groq Vision + OpenRouter + Cerebras probes
2. Phase 1 — Local ensemble (replaces today's _local_forensic_fallback)
2.1 apps/api/core/vision_fallback_ensemble.py (NEW)
"""
Vision Fallback Ensemble — composite local-tool replacement for Gemini vision.

When all upstream vision providers (Gemini cascade, Groq Vision, OpenRouter)
are unavailable or quota-blocked, this module produces a GeminiVisionFinding-
shaped result by fusing CPU-only tools already shipped in the repo:

  * DETR object detection           (Apache-2.0, cached HF model)
  * CLIP zero-shot scene/content    (already used in agent3_object)
  * EasyOCR + Tesseract text extract
  * ELA / PRNU / Splicing reuse     (read from agent1's _tool_context)
  * OpenCV global stats (legacy)

Output confidence is capped at 0.65 (vs. legacy 0.55) because four
independent local signals corroborate the verdict.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from core.gemini_client import GeminiVisionFinding
from core.structured_logging import get_logger

logger = get_logger(__name__)

# Forensic-relevant CLIP prompt set — superset of clip_utils defaults
_CLIP_PROMPTS = [
    "an outdoor photograph taken with a camera",
    "an indoor photograph taken with a camera",
    "a portrait photograph of a person or face",
    "a screenshot of a mobile phone screen",
    "a screenshot of a desktop application",
    "a screenshot of a web browser",
    "a screenshot of a chat conversation",
    "a scanned document or printed page",
    "a passport or identification document",
    "a digitally generated or AI-generated image",
    "a crime scene photograph",
    "a photograph of a weapon or knife",
    "a photograph of a firearm or gun",
    "a photograph of a vehicle",
    "a meme or social-media image",
    "a surveillance camera frame",
]

# Mapping CLIP top-match → forensic_routing.image_category
_CATEGORY_MAP = {
    "outdoor photograph": "live_photograph",
    "indoor photograph":  "live_photograph",
    "portrait photograph": "live_photograph",
    "screenshot of a mobile": "screenshot",
    "screenshot of a desktop": "screenshot",
    "screenshot of a web browser": "screenshot",
    "screenshot of a chat": "screenshot",
    "scanned document": "document",
    "passport or identification": "document",
    "digitally generated": "ai_generated_suspect",
    "crime scene": "object_scene",
    "weapon or knife": "object_scene",
    "firearm or gun": "object_scene",
    "vehicle": "object_scene",
    "meme": "web_image",
    "surveillance camera": "web_image",
}


class VisionFallbackEnsemble:
    """Fuses local CPU tools into a GeminiVisionFinding."""

    def __init__(self, config: Any):
        self.config = config

    async def analyze(
        self,
        file_path: str,
        exif_summary: dict | None = None,
        is_screen_capture_like: bool = False,
        agent1_tool_context: dict | None = None,
    ) -> GeminiVisionFinding:
        t0 = time.monotonic()
        # Run all signals concurrently; each task is best-effort.
        results = await asyncio.gather(
            self._opencv_stats(file_path),
            self._clip_classify(file_path),
            self._detr_objects(file_path),
            self._ocr_text(file_path),
            return_exceptions=True,
        )
        opencv_r, clip_r, detr_r, ocr_r = [
            r if not isinstance(r, Exception) else {} for r in results
        ]

        # ── Fuse signals into GeminiVisionFinding fields ───────────────
        content_type = self._resolve_content_type(clip_r, opencv_r)
        scene_desc = self._build_scene_description(opencv_r, clip_r, detr_r)
        detected_objects = detr_r.get("objects", [])
        extracted_text = ocr_r.get("lines", [])
        interface_id = self._resolve_interface(clip_r, extracted_text)

        # Reuse Agent 1 forensic context (ELA, PRNU, splicing, copy-move).
        manipulation_signals = self._extract_manipulation_signals(
            agent1_tool_context or {}, opencv_r, is_screen_capture_like
        )

        # Confidence policy — fixed bands:
        # 4 healthy signals → 0.65
        # 3 healthy → 0.60   2 → 0.55   ≤1 → 0.45
        healthy = sum(1 for r in (opencv_r, clip_r, detr_r, ocr_r) if r)
        confidence = {4: 0.65, 3: 0.60, 2: 0.55}.get(healthy, 0.45)

        verdict = self._compute_verdict(manipulation_signals, clip_r)
        routing = self._compute_routing(clip_r, content_type)

        latency_ms = (time.monotonic() - t0) * 1000
        finding = GeminiVisionFinding(
            analysis_type="deep_forensic_analysis",
            model_used="local_ensemble_v2",
            content_description=scene_desc,
            manipulation_signals=manipulation_signals,
            detected_objects=detected_objects,
            contextual_anomalies=[],
            file_type_assessment=content_type,
            confidence=confidence,
            court_defensible=False,
            caveat=(
                "Composite local-tool ensemble (DETR + CLIP + OCR + ELA reuse). "
                "Set GEMINI_API_KEY (or GROQ_VISION_API_KEY / OPENROUTER_API_KEY) "
                "for grounded vision-language reasoning."
            ),
            raw_response="",
            latency_ms=latency_ms,
            _extracted_text=extracted_text,
            _interface_identification=interface_id,
            _contextual_narrative=scene_desc,
            _authenticity_verdict=verdict,
            _metadata_visual_consistency=self._metadata_consistency_note(exif_summary, opencv_r),
            _forensic_routing=routing,
            _forensic_specifics=self._domain_specifics(routing.get("image_category", "")),
        )
        return finding

    # ── component helpers (each isolated; failure of one ≠ failure of all) ──

    async def _opencv_stats(self, file_path: str) -> dict:
        """OpenCV global stats — sharpness, brightness, blockiness, channel balance."""
        try:
            import cv2
            import numpy as np
            from PIL import Image as PImg
            img = PImg.open(file_path).convert("RGB")
            arr = np.array(img)
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
            h, w = gray.shape
            lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            noise = float(np.abs(gray.astype(float) - blurred.astype(float)).mean())
            block = float(np.abs(np.diff(gray.astype(float), axis=0)[7::8].mean())) if h > 16 else 0.0
            std_rgb = arr.astype(float).std(axis=(0, 1)).tolist()
            return {
                "width": w, "height": h,
                "sharpness": lap_var, "noise": noise, "blockiness": block,
                "brightness": float(arr.mean()),
                "channel_balance": float(max(std_rgb) - min(std_rgb)),
            }
        except Exception as exc:
            logger.debug("opencv_stats failed", error=str(exc))
            return {}

    async def _clip_classify(self, file_path: str) -> dict:
        """Zero-shot CLIP scene classification."""
        try:
            from tools.clip_utils import get_clip_analyzer
            analyzer = get_clip_analyzer()
            res = await asyncio.to_thread(
                analyzer.analyze_image, file_path, _CLIP_PROMPTS,
            )
            return {
                "top_match": res.top_match,
                "top_confidence": res.top_confidence,
                "all_scores": res.all_scores[:5],
            }
        except Exception as exc:
            logger.debug("clip_classify failed", error=str(exc))
            return {}

    async def _detr_objects(self, file_path: str) -> dict:
        """DETR object detection — returns a list of 'class @ region' strings."""
        try:
            from tools.image_tools import detr_detect_objects  # add lightweight wrapper if absent
            objs = await asyncio.to_thread(detr_detect_objects, file_path)
            return {"objects": [f"{o['label']} ({o.get('region', 'center')})" for o in objs[:25]]}
        except ImportError:
            # DETR wrapper not yet exposed — fallback to no objects, not a failure
            return {}
        except Exception as exc:
            logger.debug("detr_objects failed", error=str(exc))
            return {}

    async def _ocr_text(self, file_path: str) -> dict:
        """Tesseract + EasyOCR composite text extraction."""
        lines: list[str] = []
        try:
            import pytesseract
            from PIL import Image as PImg
            raw = pytesseract.image_to_string(PImg.open(file_path), config="--psm 3").strip()
            lines = [ln.strip() for ln in raw.splitlines() if len(ln.strip()) > 2]
        except Exception as exc:
            logger.debug("tesseract failed", error=str(exc))
        if not lines:
            try:
                from tools.ocr_tools import _get_easyocr_reader
                reader = _get_easyocr_reader()
                if reader is not None:
                    res = await asyncio.to_thread(reader.readtext, file_path, detail=0)
                    lines = [str(t).strip() for t in res if len(str(t).strip()) > 2]
            except Exception as exc:
                logger.debug("easyocr failed", error=str(exc))
        return {"lines": lines[:25]} if lines else {}

    # ── fusion helpers ────────────────────────────────────────────────

    def _resolve_content_type(self, clip_r: dict, opencv_r: dict) -> str:
        top = (clip_r.get("top_match") or "").lower()
        if not top:
            if not opencv_r:
                return "unknown image"
            if opencv_r.get("sharpness", 0) < 80:
                return "blurry or low-quality image"
            return "digital image"
        return top

    def _build_scene_description(self, opencv_r, clip_r, detr_r) -> str:
        parts = []
        if clip_r.get("top_match"):
            parts.append(f"{clip_r['top_match']} (CLIP conf {clip_r['top_confidence']:.2f})")
        if opencv_r:
            parts.append(
                f"{opencv_r['width']}×{opencv_r['height']}px, "
                f"sharpness {opencv_r['sharpness']:.0f}, "
                f"brightness {opencv_r['brightness']:.0f}/255"
            )
        if detr_r.get("objects"):
            parts.append(f"Detected: {', '.join(detr_r['objects'][:5])}")
        return " | ".join(parts) or "Local ensemble analysis (no upstream vision provider)."

    def _resolve_interface(self, clip_r: dict, ocr_lines: list[str]) -> str:
        top = (clip_r.get("top_match") or "").lower()
        if "screenshot" in top:
            return top
        ui_hints = ["http://", "https://", "www.", "@", ".com", "Login", "Sign in", "Settings"]
        if any(any(h in ln for h in ui_hints) for ln in ocr_lines):
            return "digital interface (inferred from OCR)"
        return ""

    def _extract_manipulation_signals(self, ctx: dict, opencv_r: dict, is_screen: bool) -> list[str]:
        signals: list[str] = []
        # Reuse classical findings — these have already run in the initial pass
        ela = ctx.get("ela_anomaly_classifier", {})
        if ela.get("hotspot_count", 0) > 3:
            signals.append(f"ELA hotspots detected ({ela['hotspot_count']})")
        prnu = ctx.get("noise_fingerprint", {})
        if prnu.get("anomaly_score", 0) > 0.6:
            signals.append(f"PRNU anomaly score {prnu['anomaly_score']:.2f}")
        spl = ctx.get("splicing_detector", {})
        if spl.get("splice_detected"):
            signals.append("Splicing detector triggered (SRM residual)")
        cm = ctx.get("copy_move_detector", {})
        if cm.get("clusters", 0) > 0:
            signals.append(f"Copy-move clusters: {cm['clusters']}")
        # OpenCV thresholds (screenshot-aware, same as legacy)
        nt = 15 if is_screen else 8
        bt = 12 if is_screen else 8
        if opencv_r.get("noise", 0) > nt:
            signals.append(f"Elevated noise residual ({opencv_r['noise']:.2f})")
        if opencv_r.get("blockiness", 0) > bt:
            signals.append(f"JPEG block artifacts ({opencv_r['blockiness']:.1f})")
        return signals

    def _compute_verdict(self, signals: list[str], clip_r: dict) -> str:
        if "digitally generated" in (clip_r.get("top_match") or "").lower():
            return "AI_GENERATED"
        if len(signals) >= 2:
            return "SUSPICIOUS"
        if len(signals) == 1:
            return "CANNOT_DETERMINE"
        return "AUTHENTIC"

    def _compute_routing(self, clip_r: dict, content_type: str) -> dict:
        top = (clip_r.get("top_match") or content_type).lower()
        category = "object_scene"
        for needle, cat in _CATEGORY_MAP.items():
            if needle in top:
                category = cat
                break
        return {
            "image_category": category,
            "priority_signals": [],
            "skip_tools": [],
            "focus_regions": [],
        }

    def _metadata_consistency_note(self, exif: dict | None, opencv_r: dict) -> str:
        if not exif:
            return "No EXIF metadata provided for cross-validation."
        notes = []
        make = exif.get("camera_make", "")
        if make:
            notes.append(f"Claimed device: {make} {exif.get('camera_model','')}")
        dt = exif.get("datetime_original", "")
        if dt:
            notes.append(f"Claimed capture time: {dt}")
        return "; ".join(notes) if notes else "EXIF present but no device/timestamp."

    def _domain_specifics(self, category: str) -> str:
        return {
            "live_photograph": "Shadow direction and skin texture not validated locally.",
            "screenshot":      "UI element rendering not validated locally.",
            "document":        "Ink uniformity and baseline consistency not validated locally.",
            "ai_generated_suspect": "GAN-fingerprint analysis not performed locally.",
            "object_scene":    "Scale plausibility not validated locally.",
            "web_image":       "Reverse-image-search not performed locally.",
        }.get(category, "")
Note on tools.image_tools.detr_detect_objects — if the repo doesn't already expose a sync DETR helper, add a thin wrapper next to agent3_object.py that calls the existing object_detection tool used inside Agent 3 (it already uses DETR by default via YOLO_MODEL_NAME=detr-resnet-50 in MODEL_REGISTRY.md). Keep ≤30 lines.

3. Phase 2 — VisionRouter adds Groq-Vision + OpenRouter
3.1 apps/api/core/vision_router.py (NEW)
"""
Vision Router — single facade in front of:
  1. GeminiVisionClient (existing cascade)
  2. Groq Vision (Llama-3.2/4 Vision via OpenAI-compatible endpoint)
  3. OpenRouter free vision models (opt-in)
  4. VisionFallbackEnsemble (local CPU tools)
  5. GeminiVisionClient._local_forensic_fallback (legacy, last resort)

Public surface is identical to GeminiVisionClient — same method names,
same GeminiVisionFinding return type. Callers swap class import only.
"""

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import time
from pathlib import Path
from typing import Any

import httpx

from core.config import Settings
from core.gemini_client import GeminiVisionClient, GeminiVisionFinding
from core.llm_client import is_placeholder_secret
from core.provider_quota_guard import ProviderQuotaGuard
from core.retry import CircuitBreaker
from core.structured_logging import get_logger
from core.vision_fallback_ensemble import VisionFallbackEnsemble

logger = get_logger(__name__)


class VisionRouter:
    """Routes vision requests through configured provider chain."""

    # Default chain — overridden by Settings.vision_provider_chain
    _DEFAULT_CHAIN = ("gemini", "groq_vision", "openrouter", "local_ensemble")

    def __init__(self, config: Settings):
        self.config = config
        self._gemini = GeminiVisionClient(config)
        self._ensemble = VisionFallbackEnsemble(config)
        self._chain: list[str] = [
            p.strip() for p in
            (getattr(config, "vision_provider_chain", "") or ",".join(self._DEFAULT_CHAIN)).split(",")
            if p.strip()
        ]
        self._groq_vision_cb = CircuitBreaker(failure_threshold=3, recovery_timeout=120.0)
        self._openrouter_cb = CircuitBreaker(failure_threshold=3, recovery_timeout=120.0)

    # ── Public surface identical to GeminiVisionClient ──────────────────

    async def deep_forensic_analysis(
        self,
        file_path: str,
        exif_summary: dict | None = None,
        model_hint: str | None = None,
        signal_callback: Any | None = None,
        persona: str | None = None,
        is_screen_capture_like: bool = False,
        agent_id: str = "",
    ) -> GeminiVisionFinding:
        kwargs = dict(
            file_path=file_path, exif_summary=exif_summary, model_hint=model_hint,
            signal_callback=signal_callback, persona=persona,
            is_screen_capture_like=is_screen_capture_like, agent_id=agent_id,
        )
        for provider in self._chain:
            if provider == "gemini":
                if self._gemini._enabled:
                    finding = await self._gemini.deep_forensic_analysis(**kwargs)
                    if not finding.error and finding.model_used != "local_opencv_fallback":
                        return finding
            elif provider == "groq_vision":
                finding = await self._call_groq_vision(**kwargs)
                if finding is not None:
                    return finding
            elif provider == "openrouter":
                finding = await self._call_openrouter(**kwargs)
                if finding is not None:
                    return finding
            elif provider == "local_ensemble":
                # Pull agent1 tool context out of kwargs if mixin passed it through
                ctx = (exif_summary or {}).get("tools", {}) if exif_summary else {}
                return await self._ensemble.analyze(
                    file_path=file_path,
                    exif_summary=exif_summary,
                    is_screen_capture_like=is_screen_capture_like,
                    agent1_tool_context=ctx,
                )
        # absolute last resort
        return await self._gemini._local_forensic_fallback(
            file_path, exif_summary, is_screen_capture_like=is_screen_capture_like
        )

    # The 3 narrower methods (identify_file_content, analyze_manipulation_evidence,
    # analyze_objects_and_scene, analyze_metadata_visual_consistency)
    # delegate identically — they all funnel through deep_forensic_analysis on fallback,
    # while still trying Gemini's narrow prompt first. Implementation is symmetric:

    async def identify_file_content(self, file_path: str, agent_context: str = "") -> GeminiVisionFinding:
        if self._gemini._enabled:
            f = await self._gemini.identify_file_content(file_path, agent_context)
            if not f.error and f.model_used != "local_opencv_fallback":
                return f
        return await self.deep_forensic_analysis(file_path=file_path, exif_summary=None)

    # (same pattern for analyze_manipulation_evidence, analyze_objects_and_scene,
    #  analyze_metadata_visual_consistency — each ~6 lines)

    # ── Groq Vision provider ────────────────────────────────────────────

    async def _call_groq_vision(self, **kwargs) -> GeminiVisionFinding | None:
        key = self.config.groq_vision_api_key or self.config.llm_api_key
        if not key or is_placeholder_secret(key):
            return None
        if self._groq_vision_cb.state == "OPEN":
            return None
        allowed, _ = await ProviderQuotaGuard.check_and_record(
            "groq_vision", self.config.groq_vision_model
        )
        if not allowed:
            return None
        try:
            text = await self._post_openai_vision(
                base_url="https://api.groq.com/openai/v1/chat/completions",
                api_key=key,
                model=self.config.groq_vision_model,
                file_path=kwargs["file_path"],
                prompt=self._build_prompt(kwargs),
                timeout=self.config.groq_vision_timeout,
            )
            finding = self._parse_json_response(
                text, model_used=f"groq/{self.config.groq_vision_model}",
                analysis_type="deep_forensic_analysis",
            )
            self._groq_vision_cb.record_success()
            return finding
        except Exception as exc:
            self._groq_vision_cb.record_failure()
            logger.warning("Groq Vision failed", error=str(exc))
            return None

    # ── OpenRouter provider ─────────────────────────────────────────────

    async def _call_openrouter(self, **kwargs) -> GeminiVisionFinding | None:
        key = self.config.openrouter_api_key
        if not key or is_placeholder_secret(key) or not self.config.openrouter_enabled:
            return None
        if self._openrouter_cb.state == "OPEN":
            return None
        models = [m.strip() for m in self.config.openrouter_vision_models.split(",") if m.strip()]
        for model in models:
            allowed, _ = await ProviderQuotaGuard.check_and_record("openrouter", model)
            if not allowed:
                continue
            try:
                text = await self._post_openai_vision(
                    base_url="https://openrouter.ai/api/v1/chat/completions",
                    api_key=key,
                    model=model,
                    file_path=kwargs["file_path"],
                    prompt=self._build_prompt(kwargs),
                    timeout=self.config.openrouter_timeout,
                    extra_headers={
                        "HTTP-Referer": self.config.openrouter_referer or "https://forensic-council.local",
                        "X-Title": "Forensic Council",
                    },
                )
                finding = self._parse_json_response(
                    text, model_used=f"openrouter/{model}",
                    analysis_type="deep_forensic_analysis",
                )
                self._openrouter_cb.record_success()
                return finding
            except Exception as exc:
                logger.warning(f"OpenRouter {model} failed: {exc}")
                self._openrouter_cb.record_failure()
        return None

    # ── shared HTTP helper for OpenAI-compatible chat/completions vision ─

    async def _post_openai_vision(
        self, *, base_url: str, api_key: str, model: str, file_path: str,
        prompt: str, timeout: float, extra_headers: dict | None = None,
    ) -> str:
        mime, _ = mimetypes.guess_type(file_path)
        mime = mime or "image/jpeg"
        with open(file_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)
        payload = {
            "model": model,
            "temperature": 0.1,
            "max_tokens": 2048,
            "response_format": {"type": "json_object"},
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": prompt},
                ],
            }],
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(base_url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"].get("content", "")

    # ── reuse Gemini's prompt template + JSON parser ────────────────────

    def _build_prompt(self, kwargs: dict) -> str:
        # Reuse the prompt construction inside GeminiVisionClient.deep_forensic_analysis
        # by exporting it as a static method. Add a small refactor:
        from core.gemini_client import _build_deep_forensic_prompt  # see Phase 2.2 below
        return _build_deep_forensic_prompt(
            exif_summary=kwargs.get("exif_summary"),
            persona=kwargs.get("persona"),
            is_screen_capture_like=kwargs.get("is_screen_capture_like", False),
        )

    def _parse_json_response(self, raw: str, model_used: str, analysis_type: str) -> GeminiVisionFinding:
        # Reuse GeminiVisionClient._parse_response, but stamp model_used
        # (small refactor — make _parse_response classmethod or pull body out).
        finding = self._gemini._parse_response(raw, analysis_type, 0.0)
        finding.model_used = model_used
        return finding
3.2 Small refactor inside apps/api/core/gemini_client.py
Extract the prompt-construction block (the giant prompt = (_SAFETY_PREAMBLE + persona_preamble + ...) inside deep_forensic_analysis, lines ~673-756) into a module-level function so VisionRouter can reuse it:

def _build_deep_forensic_prompt(
    exif_summary: dict | None,
    persona: str | None,
    is_screen_capture_like: bool,
) -> str:
    # …existing body verbatim…
    return prompt
And replace the inline construction inside deep_forensic_analysis with:

prompt = _build_deep_forensic_prompt(exif_summary, persona, is_screen_capture_like)
This avoids prompt duplication.

4. Phase 3 — Text/synthesis cascade hygiene
4.1 apps/api/core/llm_client.py changes (3 surgical edits)
Edit A — Remove the 30 s emergency sleep. Replace lines ~780-814 of _generate_synthesis_inner:

# OLD:
#     logger.warning("All synthesis candidates exhausted. Initiating forced Gemini synthesis fallback in 30 seconds...")
#     await asyncio.sleep(30.0)
#     ...

# NEW:
if last_exc:
    logger.error(f"All synthesis candidates failed: {last_exc}")
return ""
(The arbiter narrative layer's _template_all will handle the empty-string return — that's already wired.)

Edit B — Symmetric cross-provider for synthesis. Replace the cross-provider append block (lines ~672-680) with:

# Cross-provider fallback chain — append other providers if their key is set.
# Today this was Groq → Gemini only. Add the symmetric Gemini → Groq path and
# Cerebras as a last LLM-tier fallback before templates.
if self.provider == "groq" and self.gemini_api_key and not is_placeholder_secret(self.gemini_api_key):
    candidate = f"gemini/{self.gemini_model}"
    if candidate not in candidates:
        candidates.append(candidate)
if self.provider == "gemini" and self.api_key and not is_placeholder_secret(self.api_key):
    # If we are running gemini-primary, append the configured groq fallback model
    candidate = f"groq/{getattr(self.config, 'llm_fallback_models', '').split(',')[0].strip()}"
    if candidate and candidate != "groq/" and candidate not in candidates:
        candidates.append(candidate)
# Cerebras text-tier last resort
cb_key = getattr(self.config, "cerebras_api_key", None)
if cb_key and not is_placeholder_secret(cb_key):
    cb_model = getattr(self.config, "cerebras_model", "llama-3.3-70b")
    candidates.append(f"cerebras/{cb_model}")
Edit C — Handle cerebras provider in the per-candidate branch. Inside the for model_spec in candidates: loop, add an elif target_provider == "cerebras": block (Cerebras uses the OpenAI-compatible endpoint at https://api.cerebras.ai/v1/chat/completions):

elif target_provider == "cerebras":
    url = "https://api.cerebras.ai/v1/chat/completions"
    req_headers = {
        "Authorization": f"Bearer {cb_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": target_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_content},
        ],
        "temperature": 0.2,
        "max_tokens": tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    async with LLMClient._global_semaphore:
        resp = await client.post(url, headers=req_headers, json=payload, timeout=req_timeout)
And one extra parsing branch right after the if target_provider == "groq": return ... block:

elif target_provider == "cerebras":
    return resp.json()["choices"][0]["message"].get("content", "").strip()
4.2 apps/api/agents/arbiter_narrative.py — parallel template+LLM
Inside deliberate_narratives (the section starting at line ~1495 await _step("Generating cross-modal arbiter synthesis.")), wrap with asyncio.wait so the template is built immediately and used if the LLM exceeds 12 s:

# Build template synthesis up-front so we have a usable result even if LLM stalls.
def _build_template():
    return self._template_all(
        overall_verdict, overall_confidence, overall_error_rate,
        manipulation_probability, applicable_agent_count, all_findings,
        cross_modal_confirmed_count, len(contested_findings),
        analysis_coverage_note, active_agent_results,
        incomplete_count=len(incomplete_findings),
        per_agent_metrics=per_agent_metrics,
    )
template_future = asyncio.to_thread(_build_template)

# Existing LLM call wrapped with shorter ceiling (12 s)
async def _llm():
    try:
        return await asyncio.wait_for(
            self._llm_arbiter_synthesis(...),  # existing args
            timeout=12.0,
        )
    except Exception as _e:
        logger.warning("Arbiter LLM synthesis failed", error=str(_e))
        return None

done, _pending = await asyncio.wait(
    {asyncio.create_task(_llm()), template_future},
    return_when=asyncio.FIRST_COMPLETED,
    timeout=12.5,
)
llm_result = None
template_result = None
for task in done:
    val = task.result()
    if val is None:
        continue
    if isinstance(val, tuple) and len(val) == 6:
        template_result = val  # _template_all returns 6-tuple
    else:
        llm_result = val
# If LLM didn't return in time, await the template (it's cheap)
if not llm_result and not template_result:
    template_result = await template_future
The downstream code remains the same — llm_result populates v_sent / kf_list / r_note / p_anal / exec_sum / unc_stmt if present, otherwise template_result populates them.

5. Phase 4 — Configuration + observability
5.1 apps/api/core/config.py additions
Insert after the existing Gemini settings block (around line 700):

# ─── Vision provider chain (cascade order) ──────────────────────────────
vision_provider_chain: str = Field(
    default="gemini,groq_vision,openrouter,local_ensemble",
    description="Comma-separated cascade. Disable a step by removing it.",
)
text_provider_chain: str = Field(
    default="groq,gemini,cerebras,template",
    description="Comma-separated text-LLM cascade for synthesis.",
)

# ─── Groq Vision (Llama-3.2/4 vision via OpenAI-compatible endpoint) ────
groq_vision_api_key: str | None = Field(
    default=None,
    description="Groq API key for vision models. Defaults to LLM_API_KEY if unset.",
)
groq_vision_model: str = Field(
    default="meta-llama/llama-4-scout-17b-16e-instruct",
    description="Groq vision model id. Free-tier alternative: llama-3.2-90b-vision-preview.",
)
groq_vision_timeout: float = Field(default=30.0)
groq_vision_rpm_limit: int = Field(default=15)
groq_vision_rpd_limit: int = Field(default=14400)

# ─── OpenRouter (free vision models, opt-in) ────────────────────────────
openrouter_enabled: bool = Field(default=False)
openrouter_api_key: str | None = Field(default=None)
openrouter_referer: str | None = Field(default=None)
openrouter_vision_models: str = Field(
    default=("meta-llama/llama-3.2-11b-vision-instruct:free,"
             "qwen/qwen2.5-vl-7b-instruct:free,"
             "google/gemma-3-12b-it:free"),
)
openrouter_timeout: float = Field(default=45.0)
openrouter_rpm_limit: int = Field(default=20)
openrouter_rpd_limit: int = Field(default=200)

# ─── Cerebras (text only, free tier) ────────────────────────────────────
cerebras_api_key: str | None = Field(default=None)
cerebras_model: str = Field(default="llama-3.3-70b")
cerebras_rpm_limit: int = Field(default=30)
cerebras_rpd_limit: int = Field(default=14400)
5.2 .env.example additions (append below the existing Gemini block ~line 195)
# ─── Vision cascade (after Gemini exhausts) ───────────────────────────
VISION_PROVIDER_CHAIN=gemini,groq_vision,openrouter,local_ensemble
TEXT_PROVIDER_CHAIN=groq,gemini,cerebras,template

# Groq Vision (free tier; reuses LLM_API_KEY by default)
# Get key at: https://console.groq.com/keys
GROQ_VISION_API_KEY=
GROQ_VISION_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
GROQ_VISION_RPM_LIMIT=15
GROQ_VISION_RPD_LIMIT=14400

# OpenRouter free vision models — opt-in
# Get key at: https://openrouter.ai/keys
OPENROUTER_ENABLED=false
OPENROUTER_API_KEY=
OPENROUTER_REFERER=https://forensic-council.local
OPENROUTER_VISION_MODELS=meta-llama/llama-3.2-11b-vision-instruct:free,qwen/qwen2.5-vl-7b-instruct:free,google/gemma-3-12b-it:free
OPENROUTER_RPM_LIMIT=20
OPENROUTER_RPD_LIMIT=200

# Cerebras text-only last-resort LLM
# Get key at: https://cloud.cerebras.ai/
CEREBRAS_API_KEY=
CEREBRAS_MODEL=llama-3.3-70b
5.3 apps/api/api/main.py — wire quota guards (insert near line 349)
ProviderQuotaGuard.configure(
    "groq_vision",
    rpm_limit=settings.groq_vision_rpm_limit,
    rpd_limit=settings.groq_vision_rpd_limit,
)
ProviderQuotaGuard.configure(
    "openrouter",
    rpm_limit=settings.openrouter_rpm_limit,
    rpd_limit=settings.openrouter_rpd_limit,
)
ProviderQuotaGuard.configure(
    "cerebras",
    rpm_limit=settings.cerebras_rpm_limit,
    rpd_limit=settings.cerebras_rpd_limit,
)
And register the new router (near where other route routers are included):

from api.routes.health_providers import router as health_providers_router
app.include_router(health_providers_router, prefix="/api/v1")
5.4 apps/api/api/routes/health_providers.py (NEW)
"""Live provider-cascade status endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from core.config import Settings, get_settings
from core.llm_client import is_placeholder_secret
from core.provider_quota_guard import ProviderQuotaGuard

router = APIRouter(tags=["health"])


def _status_for(name: str, key: str | None, model: str) -> dict:
    rpm, rpd = ProviderQuotaGuard.get_current_counts(name, model)
    cfg = ProviderQuotaGuard.get_config(name)
    return {
        "provider": name,
        "model": model,
        "key_configured": bool(key) and not is_placeholder_secret(key),
        "rpm_used": rpm,
        "rpm_limit": cfg.rpm_limit if cfg else None,
        "rpd_used": rpd,
        "rpd_limit": cfg.rpd_limit if cfg else None,
    }


@router.get("/health/providers")
async def providers(settings: Settings = Depends(get_settings)):
    return {
        "vision_chain": settings.vision_provider_chain.split(","),
        "text_chain":   settings.text_provider_chain.split(","),
        "providers": [
            _status_for("gemini",       settings.gemini_api_key,        settings.gemini_model),
            _status_for("groq",         settings.llm_api_key,           settings.llm_model),
            _status_for("groq_vision",  settings.groq_vision_api_key or settings.llm_api_key,
                                                                       settings.groq_vision_model),
            _status_for("openrouter",   settings.openrouter_api_key,
                                                                       settings.openrouter_vision_models.split(",")[0]),
            _status_for("cerebras",     settings.cerebras_api_key,      settings.cerebras_model),
        ],
        "gemini_policy_ok": settings.gemini_api_key_policy_ok,
    }
5.5 apps/api/agents/mixins/synthesis.py — one-line swap
- from core.gemini_client import GeminiVisionClient
+ from core.vision_router import VisionRouter as GeminiVisionClient
That's the entire integration. Existing call sites and tests work unchanged.

6. Phase 5 — Tests
6.1 apps/api/tests/integration/test_provider_cascade.py (NEW)
"""Cascade scenarios A/B/C/D."""
import os
import pytest
from unittest.mock import patch, AsyncMock

from core.config import get_settings
from core.vision_router import VisionRouter


@pytest.fixture
def fake_image(tmp_path):
    from PIL import Image
    p = tmp_path / "x.jpg"
    Image.new("RGB", (256, 256), (128, 128, 128)).save(p, "JPEG")
    return str(p)


@pytest.mark.asyncio
async def test_scenario_A_gemini_and_groq(fake_image, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaTEST")
    monkeypatch.setenv("GEMINI_API_KEY_POLICY_OK", "true")
    monkeypatch.setenv("LLM_API_KEY", "gsk_TEST")
    s = get_settings()
    router = VisionRouter(s)
    with patch.object(router._gemini, "deep_forensic_analysis",
                      new=AsyncMock(return_value=_fake_finding("gemini-2.5-flash"))):
        out = await router.deep_forensic_analysis(file_path=fake_image)
    assert out.model_used.startswith("gemini")


@pytest.mark.asyncio
async def test_scenario_C_no_gemini_falls_to_local_ensemble(fake_image, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "gsk_TEST")
    # Disable groq_vision + openrouter so we land on local_ensemble
    monkeypatch.setenv("VISION_PROVIDER_CHAIN", "gemini,local_ensemble")
    s = get_settings()
    out = await VisionRouter(s).deep_forensic_analysis(file_path=fake_image)
    assert out.model_used == "local_ensemble_v2"
    assert 0.40 <= out.confidence <= 0.70
    assert out.court_defensible is False


@pytest.mark.asyncio
async def test_scenario_D_no_provider_still_produces_finding(fake_image, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("VISION_PROVIDER_CHAIN", "gemini,local_ensemble")
    s = get_settings()
    out = await VisionRouter(s).deep_forensic_analysis(file_path=fake_image)
    assert out is not None
    assert out.content_description  # non-empty


def _fake_finding(model):
    from core.gemini_client import GeminiVisionFinding
    return GeminiVisionFinding(
        analysis_type="deep_forensic_analysis", model_used=model,
        content_description="ok", confidence=0.8, court_defensible=True,
    )
6.2 Extend apps/api/scripts/verify_llm_keys.py
Add probe blocks (mirrors existing Groq/Gemini probes):

# Groq Vision (OpenAI-compat)
if settings.groq_vision_api_key or settings.llm_api_key:
    key = settings.groq_vision_api_key or settings.llm_api_key
    probe_results["groq_vision"] = await _probe_openai_compat(
        "https://api.groq.com/openai/v1/models",
        key, label="groq_vision",
    )

# OpenRouter
if settings.openrouter_api_key:
    probe_results["openrouter"] = await _probe_openai_compat(
        "https://openrouter.ai/api/v1/models",
        settings.openrouter_api_key, label="openrouter",
    )

# Cerebras
if settings.cerebras_api_key:
    probe_results["cerebras"] = await _probe_openai_compat(
        "https://api.cerebras.ai/v1/models",
        settings.cerebras_api_key, label="cerebras",
    )
7. Ordered execution plan (so a coder/agent can execute step-by-step)
Config first — apply Section 5.1 (config.py) + 5.2 (.env.example). Run uv run python -c "from core.config import get_settings; print(get_settings().vision_provider_chain)" to validate.
Refactor Gemini prompt — extract _build_deep_forensic_prompt (Section 3.2).
Create vision_fallback_ensemble.py (Section 2.1). Add tools/image_tools.detr_detect_objects thin wrapper if it doesn't exist (search first: rg "def detr_detect" apps/api/tools).
Create vision_router.py (Section 3.1).
Swap mixin import (Section 5.5).
Wire main.py startup (Section 5.3) + create health_providers.py (Section 5.4).
Edit llm_client.py — three edits in Section 4.1.
Edit arbiter_narrative.py — parallel template+LLM (Section 4.2).
Extend verify_llm_keys.py (Section 6.2).
Write integration tests (Section 6.1). Run with cd apps/api && uv run pytest tests/integration/test_provider_cascade.py -v.
Smoke test end-to-end — run a single investigation with each scenario by toggling env keys, hit GET /api/v1/health/providers and verify the cascade state matches expectation.
Update docs — docs/MODEL_REGISTRY.md and docs/ARCHITECTURE.md cascade diagram (one paragraph + the chain block from Section 0).
8. Provider sign-up URLs (operator copy/paste)
Provider	Free-tier sign-up	Notes
Groq (text + vision)	https://console.groq.com/keys	Single key for both LLM_API_KEY and GROQ_VISION_API_KEY
Google Gemini	https://aistudio.google.com/apikey	Don't forget GEMINI_API_KEY_POLICY_OK=true
OpenRouter	https://openrouter.ai/keys	Free models suffix :free; daily limit ~200 req/key
Cerebras	https://cloud.cerebras.ai/	Text only, very fast
9. What I'm NOT changing (and why)
Verdict math (arbiter._compute_verdict) — already deterministic and good.
Cross-modal fusion / cross-agent comparison — orthogonal to provider availability.
Signing / chain of custody — out of scope.
Initial pass classical tools — out of scope; they don't depend on LLMs.
Heavy local models (LLaVA, Pixtral local) — explicitly excluded per your "no GPU intensive models locally" constraint.
10. What I need from you before I start coding
Confirm scope: implement all of Phases 1-5, or stage it (e.g. Phases 1+2 first, then 3-5 in a second pass)?
API keys — please share, or confirm I should leave each blank in .env.example so the operator fills them:
Groq key (works for both text + vision)
Gemini key (+ acknowledge policy flag)
OpenRouter key (optional)
Cerebras key (optional)
OpenRouter on by default? — current proposal: OPENROUTER_ENABLED=false (opt-in, since it phones home with a referer). Confirm or flip.
Cerebras on by default? — same question.
Groq Vision model id — meta-llama/llama-4-scout-17b-16e-instruct (newer, multimodal) vs llama-3.2-90b-vision-preview (older, stable). Want me to verify both are still on Groq's free tier in 2026 with a web_search before locking the default?
Once you sign off on this plan, I'll execute the 12 steps above in order, run the integration tests, and report back.
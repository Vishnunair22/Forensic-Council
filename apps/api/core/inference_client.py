"""
Inference Client Abstraction
============================

Centralized management for heavy ML model inference (YOLO, SigLIP, AASIST).
Prevents resource fragmentation by managing model singletons and ensuring
thread-safe/async-safe inference.

Design: Fix 2 (Audit Modernization)
"""

import asyncio
import os
from typing import Any, Optional

from core.config import get_settings
from core.structured_logging import get_logger

logger = get_logger(__name__)

class InferenceClient:
    """
    Unified client for ML model inference.

    Provides a centralized point for model loading and execution,
    preventing vRAM fragmentation during multi-agent concurrent runs.
    """

    _instance: Optional["InferenceClient"] = None
    # Lock is created lazily inside the running event loop to avoid
    # DeprecationWarning/RuntimeError in Python 3.10+ when asyncio.Lock()
    # is instantiated at class-body scope before any event loop is running.
    _lock: asyncio.Lock | None = None

    def __init__(self):
        self._models: dict[str, Any] = {}
        self._load_locks: dict[str, asyncio.Lock] = {
            "yolo": asyncio.Lock(),
            "siglip": asyncio.Lock(),
            "aasist": asyncio.Lock(),
            "trufor": asyncio.Lock(),
            "busternet": asyncio.Lock(),
            "mantra": asyncio.Lock(),
            "f3net": asyncio.Lock(),
        }
        self.settings = get_settings()

    @classmethod
    async def get_instance(cls) -> "InferenceClient":
        """Get the singleton instance."""
        if cls._instance is None:
            # Lazy lock creation: must happen inside a running event loop so
            # asyncio.Lock() is bound to the correct loop (Python 3.10+).
            if cls._lock is None:
                cls._lock = asyncio.Lock()
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = InferenceClient()
        return cls._instance

    # ── YOLO (Object Detection) ───────────────────────────────────────────

    async def get_yolo_model(self):
        """Get or load YOLO11 model."""
        async with self._load_locks["yolo"]:
            if "yolo" not in self._models:
                from ultralytics import YOLO
                yolo_cache = self.settings.yolo_model_dir
                os.makedirs(yolo_cache, exist_ok=True)

                # Configure Ultralytics settings
                from ultralytics import settings as yolo_settings
                if self.settings.offline_mode:
                    os.environ["ULTRALYTICS_OFFLINE"] = "True"
                    os.environ["HF_HUB_OFFLINE"] = "1"

                valid_keys = set(yolo_settings.keys()) if hasattr(yolo_settings, "keys") else set(dict(yolo_settings).keys())
                safe_updates = {k: v for k, v in {"weights_dir": yolo_cache, "datasets_dir": yolo_cache}.items() if k in valid_keys}
                if safe_updates:
                    yolo_settings.update(safe_updates)

                model_name = getattr(self.settings, "yolo_model_name", "yolo11m.pt")
                model_path = os.path.join(yolo_cache, model_name)

                if not os.path.exists(model_path):
                    fallback_path = os.path.join(yolo_cache, "yolo11n.pt")
                    if os.path.exists(fallback_path):
                        logger.warning(
                            "Configured YOLO model missing; using cached fallback",
                            configured=model_path,
                            fallback=fallback_path,
                        )
                        model_path = fallback_path

                logger.info(f"Loading YOLO model from {model_path}...")
                self._models["yolo"] = YOLO(model_path)

            return self._models["yolo"]

    # ── SigLIP 2 (Vision-Language) ───────────────────────────────────────

    async def get_siglip_analyzer(self):
        """Get or load SigLIP 2 analyzer."""
        async with self._load_locks["siglip"]:
            if "siglip" not in self._models:
                from tools.clip_utils import get_clip_analyzer
                logger.info("Initializing SigLIP analyzer...")
                self._models["siglip"] = get_clip_analyzer()
            return self._models["siglip"]

    # ── AASIST/SpeechBrain (Audio Anti-Spoofing) ──────────────────────────

    async def get_aasist_classifier(self):
        """Get or load AASIST anti-spoofing classifier."""
        async with self._load_locks["aasist"]:
            if "aasist" not in self._models:
                try:
                    from speechbrain.inference.classifiers import EncoderClassifier
                    logger.info(f"Loading AASIST model {self.settings.aasist_model_name}...")

                    if self.settings.offline_mode:
                        os.environ["HF_HUB_OFFLINE"] = "1"
                        os.environ["TRANSFORMERS_OFFLINE"] = "1"

                    classifier = EncoderClassifier.from_hparams(
                        source=self.settings.aasist_model_name,
                        run_opts={"device": "cpu"},
                    )
                    self._models["aasist"] = classifier
                except Exception as e:
                    logger.error(f"Failed to load AASIST: {e}")
                    return None
            return self._models["aasist"]

    # ── Unified Predict Interface ──────────────────────────────────────────

    async def predict_yolo(self, image_path: str, **kwargs):
        """Run YOLO inference."""
        model = await self.get_yolo_model()
        # Run in thread pool as YOLO inference is CPU/GPU intensive and blocking
        return await asyncio.to_thread(model, image_path, **kwargs)

    async def predict_siglip(self, image_path: str, categories: list = None, check_concerns: bool = False):
        """Run SigLIP inference."""
        analyzer = await self.get_siglip_analyzer()
        # analyzer.analyze_image is synchronous
        return await asyncio.to_thread(analyzer.analyze_image, image_path, categories, check_concerns)

    async def get_neural_fingerprint(self, image_path: str):
        """[SOTA] Generate a robust neural embedding fingerprint using SigLIP 2."""
        analyzer = await self.get_siglip_analyzer()
        # Reuses the embedding layer of SigLIP for perceptual hashing
        return await asyncio.to_thread(analyzer.generate_fingerprint, image_path)

    async def predict_aasist(self, signal):
        """Run AASIST inference on audio signal."""
        classifier = await self.get_aasist_classifier()
        if classifier is None:
            return None
        # classifier.classify_batch is usually sync in SB
        return await asyncio.to_thread(classifier.classify_batch, signal)

    # ── Phase 2 Neural Forensics ──────────────────────────────────────────

    async def predict_trufor(self, image_path: str):
        """[SOTA] TruFor Vision Transformer analysis."""
        # Placeholder for actual TruFor loader integration
        return await self._run_phase2_model("trufor", image_path)

    async def predict_busternet(self, image_path: str):
        """[SOTA] BusterNet dual-branch copy-move detection."""
        return await self._run_phase2_model("busternet", image_path)

    async def predict_mantra(self, image_path: str):
        """[SOTA] ManTra-Net anomaly tracing."""
        return await self._run_phase2_model("mantra", image_path)

    async def predict_f3net(self, image_path: str):
        """[SOTA] F3-Net frequency analysis."""
        return await self._run_phase2_model("f3net", image_path)

    async def _run_phase2_model(self, model_id: str, image_path: str):
        """Generic runner for Phase 2 neural tools via ml_subprocess."""
        from core.ml_subprocess import run_ml_tool
        # Note: These are heavy operations run as separate processes
        # to ensure memory isolation while sharing VRAM if configured.
        script_map = {
            "trufor": "trufor_analyzer.py",
            "busternet": "busternet_v2.py",
            "mantra": "mantra_net_tracer.py",
            "f3net": "f3net_freq.py"
        }
        return await run_ml_tool(script_map[model_id], image_path, timeout=30.0)

async def get_inference_client() -> InferenceClient:
    """Helper to get the inference client singleton."""
    return await InferenceClient.get_instance()

"""
Worker startup diagnostics — fail-loud self-test + numba/librosa pre-warm.
========================================================================

Catches the *silent-degradation* class of reliability bugs: e.g. when
NUMBA_DISABLE_JIT=1 breaks every librosa audio tool while they quietly return
0.0 (which reads as "authentic"), or a model that won't load. We exercise the
real code paths once at startup, log LOUDLY on failure, and record a status that
the /health endpoint can surface — so degradation is visible, never silent.

Also pre-warms the librosa numba JIT (compiles the hot functions on a tiny
synthetic buffer) so the FIRST real audio analysis isn't slow / doesn't risk a
gate timeout. Compiled artifacts persist in NUMBA_CACHE_DIR (a volume).

Never raises — diagnostics must not crash the worker. NOTE: the project's
StructuredLogger does NOT accept printf-style args; always use f-strings.
"""

from __future__ import annotations

import os

from core.structured_logging import get_logger

logger = get_logger(__name__)

# Module-level status, surfaced by the health endpoint.
_STATUS: dict[str, str] = {}


def get_startup_status() -> dict[str, str]:
    return dict(_STATUS)


def run_startup_diagnostics() -> dict[str, str]:
    """Run all startup self-tests + pre-warm. Safe to call once at worker boot."""
    _config_trap_warnings()
    _prewarm_and_test_librosa()
    _test_audio_model()
    prewarm_florence()
    ok = [k for k, v in _STATUS.items() if v == "OK"]
    bad = {k: v for k, v in _STATUS.items() if v not in ("OK",) and not v.startswith("SKIPPED")}
    if bad:
        logger.error(f"Startup diagnostics: DEGRADED subsystems detected — {bad} (ok: {ok})")
    else:
        logger.info(f"Startup diagnostics: all subsystems OK — {ok}")
    return get_startup_status()


def _truthy_env(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in ("1", "true", "yes", "on")


def _config_trap_warnings() -> None:
    """Catch dangerous config combinations before they silently degrade analysis."""
    try:
        from core.config import get_settings

        s = get_settings()
        audio_on = bool(getattr(s, "enable_audio_models", False))
        if _truthy_env("NUMBA_DISABLE_JIT") and audio_on:
            _STATUS["config_numba_jit"] = "TRAP: NUMBA_DISABLE_JIT=1 with audio enabled"
            logger.error(
                "CONFIG TRAP: NUMBA_DISABLE_JIT=1 while ENABLE_AUDIO_MODELS=true — this "
                "breaks ALL librosa audio tools (they silently return 0.0, i.e. false "
                "'authentic'). Set NUMBA_DISABLE_JIT=0 and recreate the worker."
            )
        else:
            _STATUS["config_numba_jit"] = "OK"
    except Exception as exc:
        logger.warning(f"Config trap check failed (non-fatal): {exc!r}")


def prewarm_florence() -> None:
    """Load the Florence-2 VLM captioner at boot so the on-device visual-context
    description is a rich natural-language read (not a bare category) — without
    paying a cold model load inside the ensemble's concurrent tool budget, where
    it silently timed out and was dropped. Best-effort: never blocks boot."""
    try:
        from tools.florence_analyzer import get_florence_analyzer

        if get_florence_analyzer().ensure_loaded():
            _STATUS["florence2_vlm"] = "OK"
            logger.info("Startup: Florence-2 VLM pre-warmed (on-device captioning live).")
        else:
            _STATUS["florence2_vlm"] = "UNAVAILABLE"
            logger.warning(
                "Startup: Florence-2 VLM unavailable — on-device descriptions fall back "
                "to categorical identification."
            )
    except Exception as exc:
        _STATUS["florence2_vlm"] = f"ERROR: {exc!r}"
        logger.warning(f"Startup: Florence-2 pre-warm failed (non-fatal): {exc!r}")


def _prewarm_and_test_librosa() -> None:
    """Exercise + JIT-compile the hot librosa paths the audio agent depends on."""
    try:
        import librosa
        import numpy as np

        buf = np.sin(2 * np.pi * 220 * np.arange(16000, dtype=np.float32) / 16000).astype("float32")
        librosa.feature.rms(y=buf)
        librosa.feature.mfcc(y=buf, sr=16000, n_mfcc=13)
        librosa.feature.spectral_centroid(y=buf, sr=16000)
        librosa.pyin(buf, fmin=80, fmax=400, sr=16000)
        _STATUS["librosa"] = "OK"
        logger.info("Startup: librosa/numba pre-warm + self-test OK (audio tools live).")
    except Exception as exc:
        _STATUS["librosa"] = f"DEGRADED: {type(exc).__name__}"
        logger.error(
            "Startup: librosa/numba SELF-TEST FAILED — audio prosody/MFCC/spectral tools "
            f"will SILENTLY DEGRADE to 0.0 (false 'authentic'). Check NUMBA_DISABLE_JIT. {exc!r}"
        )


def _test_audio_model() -> None:
    """Confirm the configured audio deepfake model loads (only when audio enabled)."""
    try:
        from core.config import get_settings

        s = get_settings()
        if not getattr(s, "enable_audio_models", False):
            _STATUS["audio_model"] = "SKIPPED (audio disabled)"
            return
        from transformers import AutoModelForAudioClassification

        model_name = getattr(s, "voice_clone_model_name", None) or getattr(s, "aasist_model_name", "")
        AutoModelForAudioClassification.from_pretrained(model_name, local_files_only=s.offline_mode)
        _STATUS["audio_model"] = "OK"
        logger.info(f"Startup: audio deepfake model loaded ({model_name}).")
    except Exception as exc:
        _STATUS["audio_model"] = f"DEGRADED: {type(exc).__name__}"
        logger.error(
            "Startup: audio deepfake model FAILED to load — voice-clone detection degrades "
            f"to handcrafted features. {exc!r}"
        )

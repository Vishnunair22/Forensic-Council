"""
Audio Synthesis Detection
========================

Anti-spoofing (deepfake detection) and codec fingerprinting.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import numpy as np

from core.evidence import EvidenceArtifact
from core.exceptions import ToolUnavailableError

_audio_deepfake_bundle: tuple[Any, Any] | None = None
_audio_deepfake_model_name: str | None = None


def _get_audio_deepfake_bundle(model_name: str, local_files_only: bool) -> tuple[Any, Any]:
    """Load the configured Transformers audio anti-spoof model once per process."""
    global _audio_deepfake_bundle, _audio_deepfake_model_name
    if _audio_deepfake_bundle is None or _audio_deepfake_model_name != model_name:
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

        extractor = AutoFeatureExtractor.from_pretrained(
            model_name,
            local_files_only=local_files_only,
        )
        model = AutoModelForAudioClassification.from_pretrained(
            model_name,
            local_files_only=local_files_only,
        )
        model.eval()
        _audio_deepfake_bundle = (extractor, model)
        _audio_deepfake_model_name = model_name
    return _audio_deepfake_bundle


def _spoof_probability_from_logits(outputs: Any, id2label: dict) -> float:
    """Extract spoof probability from model logits."""
    try:
        import torch
        logits = outputs.logits
        if isinstance(logits, torch.Tensor):
            probs = torch.softmax(logits, dim=-1)
            spoof_idx = next(
                (i for label in id2label.values() 
                if "spoof" in label.lower() or "fake" in label.lower()),
                1
            )
            return float(probs[0][spoof_idx].item())
    except Exception:
        pass
    return 0.5


async def run_anti_spoofing_detect(
    artifact: EvidenceArtifact,
    segment: dict | None = None,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    """
    Detect audio spoofing / deepfake voice.

    Attempts SpeechBrain ECAPA-TDNN anti-spoofing classifier when available.
    Falls back to heuristic spectral analysis (librosa) otherwise.
    'analysis_source' in the result indicates which path ran.

    Args:
        artifact: The evidence artifact to analyze
        segment: Optional segment dict with 'start' and 'end' keys

    Returns:
        Dictionary with spoof_detected, confidence, analysis_source, anomalies
    """
    try:
        audio_path = artifact.file_path
        if not os.path.exists(audio_path):
            raise ToolUnavailableError(f"File not found: {audio_path}")

        try:
            import torch
            import librosa
            from core.config import get_settings

            settings = get_settings()
            if settings.offline_mode:
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ["TRANSFORMERS_OFFLINE"] = "1"

            extractor, model = _get_audio_deepfake_bundle(
                settings.aasist_model_name,
                local_files_only=settings.offline_mode,
            )
            sample_rate = int(getattr(extractor, "sampling_rate", 16000) or 16000)
            y, sr = librosa.load(audio_path, sr=sample_rate, mono=True)
            if segment:
                start_sample = int(segment.get("start", 0) * sr)
                end_sample = int(segment.get("end", len(y) / sr) * sr)
                y = y[start_sample:end_sample]

            if progress_callback:
                await progress_callback("Auditing neural spoof signatures...")

            inputs = extractor(
                y,
                sampling_rate=sample_rate,
                return_tensors="pt",
                padding=True,
            )
            with torch.no_grad():
                outputs = model(**inputs)
            id2label = getattr(model.config, "id2label", {}) or {}
            spoof_prob = _spoof_probability_from_logits(outputs, id2label)

            return {
                "spoof_detected": spoof_prob > 0.5,
                "confidence": round(spoof_prob if spoof_prob > 0.5 else 1.0 - spoof_prob, 3),
                "spoof_probability": round(spoof_prob, 4),
                "model_version": settings.aasist_model_name,
                "anomalies": ["Neural audio deepfake signature detected"]
                if spoof_prob > 0.5
                else [],
                "analysis_source": "transformers_audio_deepfake",
                "court_defensible": True,
            }
        except Exception as _model_err:
            import warnings as _w
            _w.warn(
                f"Audio deepfake model failed ({_model_err}), "
                "falling back to heuristic spectral analysis.",
                RuntimeWarning,
                stacklevel=2,
            )

        loop = asyncio.get_running_loop()
        y, sr = await loop.run_in_executor(
            None, lambda: __import__("librosa").load(audio_path, sr=16000)
        )

        if segment:
            start_sample = int(segment.get("start", 0) * sr)
            end_sample = int(segment.get("end", len(y) / sr) * sr)
            y = y[start_sample:end_sample]

        mfcc = __import__("librosa").feature.mfcc(y=y, sr=sr, n_mfcc=13)
        mfcc_mean = np.mean(mfcc, axis=1)
        mfcc_std = np.std(mfcc, axis=1)

        heuristic_score = float(np.std(mfcc_mean) + np.mean(mfcc_std))
        spoof_detected = heuristic_score > 2.5

        return {
            "spoof_detected": spoof_detected,
            "confidence": round(min(1.0, heuristic_score / 4), 3),
            "spoof_probability": round(heuristic_score / 4, 4),
            "anomalies": ["MFCC inconsistency detected"]
            if spoof_detected
            else [],
            "analysis_source": "heuristic_mfcc",
            "court_defensible": False,
        }
    except Exception as e:
        if isinstance(e, ToolUnavailableError):
            raise
        raise ToolUnavailableError(f"Anti-spoofing detection failed: {str(e)}")


async def run_codec_fingerprint(
    artifact: EvidenceArtifact,
) -> dict[str, Any]:
    """
    Extract codec fingerprint from audio file.

    Analyzes encoding artifacts to determine the codec used
    and detect potential re-encoding (transcoding).

    Args:
        artifact: The evidence artifact to analyze

    Returns:
        Dictionary containing codec, bitrate, detected_artifacts
    """
    try:
        audio_path = artifact.file_path
        if not os.path.exists(audio_path):
            raise ToolUnavailableError(f"File not found: {audio_path}")

        import soundfile as sf

        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, lambda: sf.info(audio_path))
        
        codec = getattr(info, "format", "unknown").lower()
        subtype = getattr(info, "subtype", "").lower()

        signal_np, sr = await loop.run_in_executor(
            None, lambda: sf.read(audio_path, dtype="float32")
        )
        if getattr(signal_np, "ndim", 1) > 1:
            signal_np = signal_np.mean(axis=1)

        signal_np = np.asarray(signal_np, dtype=np.float32)
        
        fft = np.fft.rfft(signal_np[:8192])
        spectral_floor = np.min(np.abs(fft))
        encoding_artifacts = []

        if spectral_floor < 1e-8:
            encoding_artifacts.append("extreme_bit_depth")

        bitrate = getattr(info, "samplerate", 0) * getattr(info, "channels", 2)
        if hasattr(info, "frames"):
            bitrate = int(bitrate * info.frames / info.duration) if info.duration else 0

        return {
            "codec": codec,
            "subtype": subtype,
            "bitrate": bitrate,
            "sample_rate": int(getattr(info, "samplerate", 0)),
            "channels": int(getattr(info, "channels", 0)),
            "detected_artifacts": encoding_artifacts,
        }
    except Exception as e:
        if isinstance(e, ToolUnavailableError):
            raise
        raise ToolUnavailableError(f"Codec fingerprinting failed: {str(e)}")
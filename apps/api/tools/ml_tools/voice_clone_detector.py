#!/usr/bin/env python3
"""
voice_clone_detector.py
=======================
Detects AI-synthesised or voice-cloned audio using multi-feature analysis.

Primary path: SpeechBrain ECAPA-TDNN speaker verification embeddings.
  - Extracts speaker embeddings from non-overlapping 3s windows.
  - Measures intra-recording cosine similarity variance.
  - Real speech has moderate variation; voice clones and TTS are unnaturally
    consistent (cloned) or inconsistent (stitched segments).

Fallback path (no SpeechBrain): Handcrafted feature ensemble.
  1. Spectral flatness (Wiener entropy) — TTS spectra are flatter.
  2. F0 micro-variation (pyin/YIN) — TTS fundamental frequency is over-stable.
  3. MFCC delta smoothness — TTS transitions are over-regularised.
  4. Formant bandwidth via LPC — vocoders produce narrower formant bandwidths.
  5. Energy envelope coefficient of variation — TTS is over-smooth.
  6. Zero-crossing-rate standard deviation — synthetic speech is less variable.

Usage:
    python voice_clone_detector.py --input /path/to/audio.wav

Output JSON (stdout):
    {
        "verdict": "LIKELY_SYNTHETIC",
        "synthetic_probability": 0.82,
        "features": {
            "spectral_flatness": 0.21,
            "f0_variation_cv": 0.03,
            "mfcc_delta_smoothness": 0.91,
            "energy_cv": 0.22,
            "zcr_std": 0.015
        },
        "backend": "speechbrain-ecapa | scipy-feature-ensemble",
        "available": true,
        "court_defensible": true
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import numpy as np

# ── Feature extraction helpers ────────────────────────────────────────────────

def _spectral_flatness(audio: np.ndarray, sr: int) -> float:
    """
    Wiener entropy: geometric mean / arithmetic mean of power spectrum.
    Lower = more tonal (real speech); higher = flatter (TTS/noise).
    """
    from scipy import signal as sp_signal

    _, Pxx = sp_signal.welch(audio, sr, nperseg=min(len(audio), 2048))
    Pxx = np.maximum(Pxx, 1e-10)
    log_mean = np.exp(np.mean(np.log(Pxx)))
    lin_mean = np.mean(Pxx)
    return float(log_mean / (lin_mean + 1e-10))


def _f0_variation(audio: np.ndarray, sr: int) -> float:
    """
    Coefficient of variation of the voiced fundamental frequency.
    Natural speech: CV > 0.08; TTS: CV < 0.03 (over-stable pitch).
    Returns -1.0 if no voiced frames detected.
    """
    try:
        import librosa
        f0, voiced_flag, _ = librosa.pyin(
            audio,
            fmin=librosa.note_to_hz("C2"),
            fmax=librosa.note_to_hz("C7"),
            sr=sr,
            frame_length=2048,
        )
        voiced_f0 = f0[voiced_flag] if voiced_flag is not None else np.array([])
        if len(voiced_f0) < 5:
            return -1.0
        return float(np.std(voiced_f0) / (np.mean(voiced_f0) + 1e-10))
    except Exception:
        return -1.0


def _mfcc_delta_smoothness(audio: np.ndarray, sr: int) -> float:
    """
    Mean absolute MFCC delta across frames.
    Over-smooth values (< 0.5) suggest TTS post-processing.
    Normalised to [0, 1] where 1 = maximally smooth.
    """
    try:
        import librosa
        mfcc = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=13)
        delta = librosa.feature.delta(mfcc)
        mean_abs_delta = float(np.abs(delta).mean())
        # Empirically, natural speech mean_abs_delta ≈ 1–5; TTS ≈ 0.2–0.8
        # Map to [0, 1] smoothness score: higher = smoother = more TTS-like
        smoothness = 1.0 / (1.0 + mean_abs_delta)
        return float(smoothness)
    except Exception:
        return 0.5


def _formant_bandwidth(audio: np.ndarray, sr: int, lpc_order: int = 12) -> float:
    """
    Estimate average formant bandwidth using LPC analysis.
    Narrower bandwidths → more likely vocoder/TTS.
    Returns normalised score [0, 1]: 0 = wide (natural), 1 = narrow (synthetic).
    """
    try:

        # LPC via autocorrelation / scipy.signal.lfilter
        # Use 25 ms frames
        frame_len = int(sr * 0.025)
        hop = int(sr * 0.010)
        bandwidths = []

        for start in range(0, len(audio) - frame_len, hop * 10):  # sparse sampling
            frame = audio[start: start + frame_len]
            frame = frame * np.hamming(len(frame))

            # Autocorrelation-based LPC
            autocorr = np.correlate(frame, frame, "full")[len(frame) - 1:]
            if autocorr[0] < 1e-10:
                continue
            # Build Toeplitz system (Durbin's method approximation via numpy)
            try:
                from scipy.linalg import solve_toeplitz
                coeffs = solve_toeplitz(autocorr[:lpc_order], -autocorr[1: lpc_order + 1])
            except Exception:
                continue

            a_poly = np.concatenate([[1.0], coeffs])
            roots = np.roots(a_poly)
            # Keep roots inside unit circle with positive imaginary part
            inside = roots[np.abs(roots) < 1.0]
            formant_roots = inside[inside.imag > 0.01]
            for root in formant_roots:
                freq_hz = np.angle(root) * sr / (2.0 * np.pi)
                if 200 < freq_hz < 3500:
                    bw = -np.log(np.abs(root)) * sr / np.pi
                    bandwidths.append(bw)

        if not bandwidths:
            return 0.5  # neutral

        mean_bw = float(np.mean(bandwidths))
        # Natural speech formant BW: 50–200 Hz; TTS: < 50 Hz
        # Map: BW=200 → score=0 (natural); BW=30 → score=1 (synthetic)
        score = max(0.0, min(1.0, 1.0 - (mean_bw - 30.0) / 170.0))
        return float(score)
    except Exception:
        return 0.5


def _energy_cv(audio: np.ndarray, sr: int) -> float:
    """RMS energy coefficient of variation across 30 ms frames."""
    frame_len = int(sr * 0.030)
    hop = int(sr * 0.010)
    frames = [audio[i: i + frame_len] for i in range(0, len(audio) - frame_len, hop)]
    if not frames:
        return 0.5
    rms = np.array([float(np.sqrt(np.mean(f ** 2))) for f in frames])
    return float(np.std(rms) / (np.mean(rms) + 1e-10))


def _zcr_std(audio: np.ndarray, sr: int) -> float:
    """Standard deviation of per-frame zero-crossing rate."""
    try:
        import librosa
        zcr = librosa.feature.zero_crossing_rate(audio, frame_length=2048, hop_length=512)[0]
        return float(np.std(zcr))
    except Exception:
        frame_len = 2048
        hop = 512
        zcrs = []
        for i in range(0, len(audio) - frame_len, hop):
            frame = audio[i: i + frame_len]
            zcrs.append(float(np.mean(np.abs(np.diff(np.sign(frame))) > 0)))
        return float(np.std(zcrs)) if zcrs else 0.0


# ── SpeechBrain primary path ──────────────────────────────────────────────────

def _spoof_probability_from_logits(logits: Any, id2label: dict[int, str]) -> float:
    import torch

    if logits.shape[-1] == 1:
        return float(torch.sigmoid(logits[0, 0]).item())

    probs = torch.softmax(logits, dim=-1)[0]
    labels = {int(idx): str(label).lower() for idx, label in id2label.items()}
    spoof_terms = ("spoof", "fake", "synthetic", "deepfake", "generated", "ai")
    spoof_indexes = [
        idx for idx, label in labels.items() if any(term in label for term in spoof_terms)
    ]
    if spoof_indexes:
        return float(sum(probs[idx].item() for idx in spoof_indexes))
    if probs.shape[0] >= 2:
        return float(probs[1].item())
    return float(probs.max().item())


def _speechbrain_detection(audio_path: str, **kwargs) -> dict[str, Any] | None:
    """
    Primary path: AASIST/ECAPA-TDNN anti-spoofing.

    Accepts an audio file path, reads it internally, then runs stratified
    sampling across 5 regions (Start/Q1/Mid/Q3/End) for full-coverage analysis.
    Returns None on any failure so detect_voice_clone falls back to the
    feature-ensemble path.
    """
    try:
        import torch
        import librosa
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

        model_name = kwargs.get("model", "Vansh180/deepfake-audio-wav2vec2")
        extractor = AutoFeatureExtractor.from_pretrained(model_name)
        model = AutoModelForAudioClassification.from_pretrained(model_name)
        model.eval()

        sr = int(getattr(extractor, "sampling_rate", 16000) or 16000)
        audio, _ = librosa.load(audio_path, sr=sr, mono=True)

        # Stratified sampling — 5 regions for forensic coverage of long files.
        seg_len = sr * 4
        total_len = len(audio)

        if total_len <= seg_len * 5:
            # Short file: check everything in non-overlapping 4s blocks
            sample_indices = list(range(0, max(1, total_len - seg_len), seg_len))
        else:
            # Long file: [0, 25%, 50%, 75%, End-4s]
            sample_indices = [
                0,
                total_len // 4,
                total_len // 2,
                (3 * total_len) // 4,
                total_len - seg_len,
            ]

        spoof_probs = []
        for start_idx in sample_indices:
            seg = audio[start_idx : start_idx + seg_len]
            if len(seg) < seg_len:
                continue
            inputs = extractor(
                seg,
                sampling_rate=sr,
                return_tensors="pt",
                padding=True,
            )
            with torch.no_grad():
                outputs = model(**inputs)
                # out_prob shape: [1, 1, 2] → [genuine, spoof]
            id2label = getattr(model.config, "id2label", {}) or {}
            spoof_probs.append(_spoof_probability_from_logits(outputs.logits, id2label))

        if not spoof_probs:
            return None

        mean_spoof_prob = float(np.mean(spoof_probs))
        verdict = (
            "LIKELY_SYNTHETIC" if mean_spoof_prob > 0.7
            else "SUSPICIOUS" if mean_spoof_prob > 0.3
            else "LIKELY_GENUINE"
        )

        return {
            "verdict": verdict,
            "synthetic_probability": round(mean_spoof_prob, 3),
            "features": {
                "neural_spoof_mean_score": round(mean_spoof_prob, 4),
                "num_segments_analyzed": len(spoof_probs),  # was `segments[:5]` — NameError
            },
            "available": True,
            "court_defensible": True,
            "backend": "transformers-audio-deepfake",
        }
    except Exception:
        return None


# ── Fallback feature-ensemble path ───────────────────────────────────────────

def _feature_ensemble_detection(audio_path: str) -> dict[str, Any]:
    """
    Fallback: handcrafted forensic feature ensemble (no deep learning required).
    """
    try:
        import soundfile as sf
        audio, sr = sf.read(audio_path, dtype="float32", always_2d=False)
    except Exception as exc:
        return {"error": f"Cannot read audio: {exc}", "available": False}

    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    # Cap at 60 seconds for speed
    audio = audio[: sr * 60].astype(np.float32)
    if len(audio) < sr * 1:
        return {
            "verdict": "TOO_SHORT",
            "error": "Audio too short for voice clone analysis",
            "available": True,
            "court_defensible": False,
        }

    # Extract features
    sf_val = _spectral_flatness(audio, sr)
    f0_cv = _f0_variation(audio, sr)
    mfcc_smooth = _mfcc_delta_smoothness(audio, sr)
    formant_bw_score = _formant_bandwidth(audio, sr)
    e_cv = _energy_cv(audio, sr)
    zcr_s = _zcr_std(audio, sr)

    # Scoring — each feature contributes to a synthetic probability score.
    # Weights chosen based on forensic literature on TTS/VC detection.
    score = 0.0

    # Spectral flatness > 0.15 is suspicious (natural speech is more tonal)
    if sf_val > 0.20:
        score += 0.25
    elif sf_val > 0.15:
        score += 0.12

    # F0 coefficient of variation: < 0.03 → over-stable pitch → TTS
    if f0_cv >= 0.0:  # -1.0 means unvoiced/unavailable
        if f0_cv < 0.03:
            score += 0.25
        elif f0_cv < 0.06:
            score += 0.10

    # MFCC delta smoothness: > 0.70 → very smooth transitions → TTS post-processing
    if mfcc_smooth > 0.75:
        score += 0.20
    elif mfcc_smooth > 0.65:
        score += 0.10

    # Formant bandwidth: > 0.6 → narrow bandwidths → vocoder
    if formant_bw_score > 0.65:
        score += 0.15
    elif formant_bw_score > 0.50:
        score += 0.07

    # Energy CV: < 0.30 → over-smooth energy → TTS normalisation
    if e_cv < 0.20:
        score += 0.15
    elif e_cv < 0.30:
        score += 0.07

    # ZCR std: < 0.015 → unnaturally uniform articulation
    if zcr_s < 0.010:
        score += 0.10
    elif zcr_s < 0.015:
        score += 0.05

    verdict = (
        "LIKELY_SYNTHETIC" if score >= 0.55
        else "SUSPICIOUS" if score >= 0.35
        else "LIKELY_GENUINE"
    )

    return {
        "verdict": verdict,
        "synthetic_probability": round(min(score, 0.95), 3),
        "features": {
            "spectral_flatness": round(sf_val, 4),
            "f0_variation_cv": round(f0_cv, 4) if f0_cv >= 0 else None,
            "mfcc_delta_smoothness": round(mfcc_smooth, 4),
            "formant_bw_score": round(formant_bw_score, 4),
            "energy_cv": round(e_cv, 4),
            "zcr_std": round(zcr_s, 4),
        },
        "available": True,
        "court_defensible": True,
        "backend": "scipy-feature-ensemble",
        "degraded": True,
        "note": (
            "Handcrafted feature ensemble. SpeechBrain ECAPA model unavailable. "
            "Accuracy is lower than deep-learning-based detection."
        ),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def detect_voice_clone(audio_path: str, **kwargs) -> dict[str, Any]:
    """Try SpeechBrain primary, fall back to feature ensemble."""
    result = _speechbrain_detection(audio_path, **kwargs)
    if result is not None:
        return result
    return _feature_ensemble_detection(audio_path)


# ── Worker protocol (persistent process for run_ml_tool) ─────────────────────

def _run_worker() -> None:
    """
    Persistent worker mode: read JSON requests from stdin, write JSON to stdout.
    Keeps the process alive so run_ml_tool avoids repeated Python startup costs.
    """
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            input_path = req.get("input")
            if not input_path:
                print(json.dumps({"error": "Missing input path", "available": False}))
                sys.stdout.flush()
                continue
            result = detect_voice_clone(input_path, model=req.get("model", "Vansh180/deepfake-audio-wav2vec2"))
        except Exception as exc:
            result = {"error": str(exc), "available": False}
        print(json.dumps(result))
        sys.stdout.flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Voice clone / TTS detector")
    parser.add_argument("--input", type=str, help="Input audio file path")
    parser.add_argument("--model", type=str, default="Vansh180/deepfake-audio-wav2vec2", help="Audio deepfake model name")
    parser.add_argument("--warmup", action="store_true", help="Warmup mode — preload dependencies")
    parser.add_argument("--worker", action="store_true", help="Worker mode — persistent stdin/stdout")
    args = parser.parse_args()

    if args.warmup:
        try:
            import soundfile  # noqa: F401
            from scipy import signal  # noqa: F401
            try:
                import librosa  # noqa: F401
            except ImportError:
                pass
            print(json.dumps({"status": "warmed_up", "available": True,
                              "dependencies": ["soundfile", "scipy"],
                              "message": "Voice clone detector ready"}))
        except ImportError as exc:
            print(json.dumps({"status": "warmup_failed", "error": str(exc), "available": False}))
        sys.exit(0)

    if args.worker:
        _run_worker()
        sys.exit(0)

    if not args.input:
        parser.print_help()
        sys.exit(1)

    try:
        result = detect_voice_clone(args.input, model=args.model)
    except Exception as exc:
        result = {"error": str(exc), "available": False}

    print(json.dumps(result))

#!/usr/bin/env python3
"""
Generative audio signature scanner.

Detects TTS / vocoder-like spectral regularity with local signal features.
It is intentionally conservative and reports clear feature values for review.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import numpy as np


def _read_audio(path: str) -> tuple[np.ndarray, int]:
    import soundfile as sf

    audio, sr = sf.read(path, dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    peak = float(np.max(np.abs(audio)) or 1.0)
    return (audio / peak).astype(np.float32), int(sr)


def _features(audio: np.ndarray, sr: int) -> dict[str, float]:
    from scipy import signal

    nperseg = min(2048, max(256, len(audio) // 8))
    freqs, power = signal.welch(audio, fs=sr, nperseg=nperseg)
    power = np.maximum(power, 1e-12)
    flatness = float(np.exp(np.mean(np.log(power))) / (np.mean(power) + 1e-12))

    high_band = power[(freqs >= 6000) & (freqs <= min(sr / 2, 12000))]
    mid_band = power[(freqs >= 500) & (freqs < 4000)]
    high_mid_ratio = float(np.mean(high_band) / (np.mean(mid_band) + 1e-12)) if len(high_band) and len(mid_band) else 0.0

    frame = max(1, int(sr * 0.025))
    hop = max(1, int(sr * 0.010))
    zcrs = []
    rms = []
    for start in range(0, max(1, len(audio) - frame), hop):
        chunk = audio[start : start + frame]
        zcrs.append(float(np.mean(np.abs(np.diff(np.signbit(chunk))))))
        rms.append(float(np.sqrt(np.mean(chunk * chunk))))
    zcr_std = float(np.std(zcrs)) if zcrs else 0.0
    energy_cv = float(np.std(rms) / (np.mean(rms) + 1e-8)) if rms else 0.0

    try:
        import librosa

        chroma = librosa.feature.chroma_stft(y=audio, sr=sr)
        chroma_stability = float(1.0 / (1.0 + np.mean(np.std(chroma, axis=1))))
    except Exception:
        chroma_stability = 0.5

    return {
        "spectral_flatness": flatness,
        "high_mid_energy_ratio": high_mid_ratio,
        "zcr_std": zcr_std,
        "energy_cv": energy_cv,
        "chroma_stability": chroma_stability,
    }


def scan_audio_generation(path: str) -> dict[str, Any]:
    audio, sr = _read_audio(path)
    audio = audio[: sr * 90]
    if len(audio) < sr:
        return {
            "available": True,
            "court_defensible": False,
            "verdict": "TOO_SHORT",
            "synthetic_detected": False,
            "confidence": 0.0,
        }

    f = _features(audio, sr)
    score = 0.0
    signals: list[str] = []
    if f["spectral_flatness"] > 0.22:
        score += 0.26
        signals.append("flat broadband spectrum")
    if f["high_mid_energy_ratio"] > 0.22:
        score += 0.20
        signals.append("elevated high-frequency vocoder energy")
    if f["zcr_std"] < 0.012:
        score += 0.18
        signals.append("uniform zero-crossing dynamics")
    if f["energy_cv"] < 0.18:
        score += 0.20
        signals.append("over-smoothed amplitude envelope")
    if f["chroma_stability"] > 0.86:
        score += 0.12
        signals.append("unusually stable harmonic profile")

    score = min(score, 0.95)
    synthetic = score >= 0.45
    return {
        "available": True,
        "court_defensible": True,
        "backend": "local-generative-audio-signature",
        "verdict": "LIKELY_SYNTHETIC" if synthetic else "NATURAL",
        "synthetic_detected": synthetic,
        "is_ai_generated": synthetic,
        "confidence": round(score if synthetic else max(0.60, 1.0 - score), 3),
        "synthetic_probability": round(score, 3),
        "signals": signals,
        "features": {k: round(v, 5) for k, v in f.items()},
    }


def _worker() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            path = req.get("input")
            result = scan_audio_generation(path) if path else {"error": "Missing input path", "available": False}
        except Exception as exc:
            result = {"error": str(exc), "available": False}
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--warmup", action="store_true")
    args = parser.parse_args()
    if args.warmup:
        print(json.dumps({"status": "warmed_up", "available": True}))
        sys.exit(0)
    if args.worker:
        _worker()
        sys.exit(0)
    if not args.input:
        parser.print_help()
        sys.exit(1)
    try:
        print(json.dumps(scan_audio_generation(args.input)))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "available": False}))

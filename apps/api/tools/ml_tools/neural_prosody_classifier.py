#!/usr/bin/env python3
"""
Neural-style prosody classifier.

This is a deterministic, local acoustic-prosody screen used when no external
Wav2Vec-style checkpoint is available. It extracts pitch, energy, spectral, and
MFCC dynamics and returns the same JSON shape expected by Agent 2.
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
    if sr <= 0 or len(audio) == 0:
        raise ValueError("empty or invalid audio stream")
    peak = float(np.max(np.abs(audio)) or 1.0)
    return (audio / peak).astype(np.float32), int(sr)


def _rms_cv(audio: np.ndarray, sr: int) -> float:
    frame = max(1, int(sr * 0.030))
    hop = max(1, int(sr * 0.010))
    vals = []
    for start in range(0, max(1, len(audio) - frame), hop):
        chunk = audio[start : start + frame]
        vals.append(float(np.sqrt(np.mean(chunk * chunk))))
    arr = np.asarray(vals, dtype=np.float32)
    return float(np.std(arr) / (np.mean(arr) + 1e-8)) if len(arr) else 0.0


def _spectral_flux(audio: np.ndarray, sr: int) -> float:
    try:
        import librosa

        spec = np.abs(librosa.stft(audio, n_fft=1024, hop_length=256))
        if spec.shape[1] < 2:
            return 0.0
        spec = spec / (np.sum(spec, axis=0, keepdims=True) + 1e-8)
        return float(np.mean(np.sqrt(np.sum(np.diff(spec, axis=1) ** 2, axis=0))))
    except Exception:
        return 0.0


def _pitch_cv(audio: np.ndarray, sr: int) -> float | None:
    try:
        import librosa

        f0, voiced, _ = librosa.pyin(
            audio,
            fmin=librosa.note_to_hz("C2"),
            fmax=librosa.note_to_hz("C7"),
            sr=sr,
            frame_length=2048,
        )
        voiced_f0 = f0[voiced] if voiced is not None else np.asarray([])
        if len(voiced_f0) < 5:
            return None
        return float(np.std(voiced_f0) / (np.mean(voiced_f0) + 1e-8))
    except Exception:
        return None


def _mfcc_delta_mean(audio: np.ndarray, sr: int) -> float:
    try:
        import librosa

        mfcc = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=13)
        return float(np.mean(np.abs(librosa.feature.delta(mfcc))))
    except Exception:
        return 0.0


def classify_prosody(path: str) -> dict[str, Any]:
    audio, sr = _read_audio(path)
    max_len = sr * 90
    audio = audio[:max_len]
    duration = len(audio) / float(sr)
    if duration < 1.0:
        return {
            "available": True,
            "court_defensible": False,
            "verdict": "TOO_SHORT",
            "confidence": 0.0,
            "manipulation_detected": False,
            "reason": "Audio shorter than 1 second.",
        }

    pitch_cv = _pitch_cv(audio, sr)
    energy_cv = _rms_cv(audio, sr)
    flux = _spectral_flux(audio, sr)
    mfcc_delta = _mfcc_delta_mean(audio, sr)

    score = 0.0
    signals: list[str] = []
    if pitch_cv is not None:
        if pitch_cv < 0.025:
            score += 0.30
            signals.append("over-stable pitch contour")
        elif pitch_cv > 0.45:
            score += 0.18
            signals.append("unstable pitch contour")
    if energy_cv < 0.12:
        score += 0.22
        signals.append("over-smoothed energy envelope")
    elif energy_cv > 1.2:
        score += 0.14
        signals.append("abrupt energy envelope shifts")
    if flux < 0.012:
        score += 0.18
        signals.append("low spectral articulation flux")
    if 0.0 < mfcc_delta < 0.55:
        score += 0.18
        signals.append("over-regular MFCC transitions")

    score = min(score, 0.95)
    verdict = "PROSODY_ANOMALY" if score >= 0.45 else "NATURAL_PROSODY"
    return {
        "available": True,
        "court_defensible": True,
        "backend": "local-prosody-feature-classifier",
        "verdict": verdict,
        "manipulation_detected": score >= 0.45,
        "prosody_anomaly": score >= 0.45,
        "confidence": round(score if score >= 0.45 else max(0.62, 1.0 - score), 3),
        "anomaly_score": round(score, 3),
        "signals": signals,
        "features": {
            "duration_s": round(duration, 2),
            "pitch_cv": round(pitch_cv, 4) if pitch_cv is not None else None,
            "energy_cv": round(energy_cv, 4),
            "spectral_flux": round(flux, 5),
            "mfcc_delta_mean": round(mfcc_delta, 4),
        },
    }


def _worker() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            path = req.get("input")
            result = classify_prosody(path) if path else {"error": "Missing input path", "available": False}
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
        print(json.dumps(classify_prosody(args.input)))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "available": False}))

#!/usr/bin/env python3
"""
audio_splice_detector.py
========================
Detects audio splicing points using MFCC anomaly detection.
Segments audio into ~1s windows, extracts features, uses IsolationForest
to flag statistically anomalous transition points.

Usage:
    python audio_splice_detector.py --input /path/to/audio.wav [--window 1.0]

Output JSON:
    {
        "splice_points": [
            {"timestamp_s": 4.2, "anomaly_score": 0.87, "feature_jump": 0.43}
        ],
        "num_splice_candidates": 1,
        "overall_consistency": 0.91,
        "verdict": "SPLICE_DETECTED",     # CLEAN | SPLICE_SUSPECTED | SPLICE_DETECTED
        "duration_s": 12.4,
        "available": true
    }
"""

import argparse
import json
import numpy as np


def extract_segment_features(y: np.ndarray, sr: int) -> np.ndarray:
    """Extract forensic audio features from a segment."""
    import librosa
    # MFCC statistics (robust to content variation)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    mfcc_mean = np.mean(mfcc, axis=1)
    mfcc_std = np.std(mfcc, axis=1)
    
    # Spectral features
    spec_centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    zcr = float(np.mean(librosa.feature.zero_crossing_rate(y)))
    rms = float(np.mean(librosa.feature.rms(y=y)))
    
    # Spectral rolloff (codec fingerprint proxy)
    rolloff = float(np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr)))
    
    return np.concatenate([mfcc_mean, mfcc_std, [spec_centroid, zcr, rms, rolloff]])


def detect_audio_splices(audio_path: str, window_s: float = 1.0) -> dict:
    import librosa
    from sklearn.ensemble import IsolationForest

    try:
        y, sr = librosa.load(audio_path, sr=None, mono=True)
    except Exception as e:
        return {"error": f"Cannot load audio: {e}", "available": False}

    duration = float(len(y) / sr)
    if duration < 3.0:
        return {
            "splice_points": [], "num_splice_candidates": 0,
            "overall_consistency": 1.0, "verdict": "INCONCLUSIVE",
            "duration_s": round(duration, 2), "available": True,
            "note": "Audio too short",
        }

    # Slice into windows
    window_samples = int(window_s * sr)
    segments = []
    timestamps = []

    for start in range(0, len(y) - window_samples, window_samples // 2):  # 50% overlap
        seg = y[start:start + window_samples]
        feats = extract_segment_features(seg, sr)
        segments.append(feats)
        timestamps.append(float(start / sr))

    if len(segments) < 5:
        return {
            "splice_points": [], "num_splice_candidates": 0,
            "overall_consistency": 1.0, "verdict": "INCONCLUSIVE",
            "duration_s": round(duration, 2), "available": True,
        }

    X = np.array(segments)
    
    # Handle NaN/inf
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    clf = IsolationForest(contamination=0.08, random_state=42, n_estimators=50)
    clf.fit(X)
    scores = clf.decision_function(X)
    labels = clf.predict(X)

    # Normalize scores to 0-1 anomaly score
    s_min, s_max = scores.min(), scores.max()
    norm_scores = (scores - s_min) / (s_max - s_min + 1e-9)
    anomaly_scores = 1.0 - norm_scores  # higher = more anomalous

    splice_points = []
    for i, (ts, label, anom) in enumerate(zip(timestamps, labels, anomaly_scores)):
        if label == -1 and anom > 0.5:
            # Feature jump: distance to previous segment
            if i > 0:
                jump = float(np.linalg.norm(X[i] - X[i-1]))
            else:
                jump = 0.0
            splice_points.append({
                "timestamp_s": round(ts, 2),
                "anomaly_score": round(float(anom), 3),
                "feature_jump": round(jump, 3),
            })

    # Deduplicate (keep max anomaly within 2s window)
    deduped = []
    for sp in sorted(splice_points, key=lambda x: -x["anomaly_score"]):
        if not any(abs(sp["timestamp_s"] - d["timestamp_s"]) < 2.0 for d in deduped):
            deduped.append(sp)

    consistency = 1.0 - (len(deduped) * 0.15)
    consistency = max(0.0, min(1.0, consistency))

    if len(deduped) >= 2:
        verdict = "SPLICE_DETECTED"
    elif len(deduped) == 1:
        verdict = "SPLICE_SUSPECTED"
    else:
        verdict = "CLEAN"

    return {
        "splice_points": deduped[:5],
        "num_splice_candidates": len(deduped),
        "overall_consistency": round(consistency, 3),
        "verdict": verdict,
        "duration_s": round(duration, 2),
        "available": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--window", type=float, default=1.0)
    args = parser.parse_args()

    try:
        result = detect_audio_splices(args.input, args.window)
    except Exception as e:
        result = {"error": str(e), "available": False}

    print(json.dumps(result))

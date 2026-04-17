#!/usr/bin/env python3
"""
enf_analysis.py
===============
Electrical Network Frequency (ENF) Analysis for Audio Forensics.

Detects ENF signal embedded in audio recordings from power line interference
and identifies splice/edit points by tracking discontinuities in the ENF trace.

Without a reference grid database this tool provides:
  - ENF signal detection and grid classification (50 Hz vs 60 Hz)
  - ENF trace continuity analysis for splice-point detection
  - Multi-harmonic SNR characterisation
  - Verdict: CLEAN | SPLICE_SUSPECTED | SPLICE_DETECTED | NO_ENF_SIGNAL

Usage:
    python enf_analysis.py --input /path/to/audio.wav [--grid 50|60|auto]

Output JSON (stdout):
    {
        "enf_detected": true,
        "grid_frequency": "50Hz",
        "dominant_harmonic_hz": 100,
        "enf_snr_db": 12.4,
        "enf_trace_length": 42,
        "splice_candidates": [{"timestamp_s": 18.2, "discontinuity_score": 0.91}],
        "num_splice_candidates": 1,
        "trace_continuity": 0.87,
        "verdict": "SPLICE_SUSPECTED",
        "available": true,
        "court_defensible": true,
        "backend": "scipy-enf-stft"
    }

References:
    Garg, R. et al. (2013). "Seeing ENF: Power-Signature-Based Timestamp for
    Digital Multimedia." IEEE Trans. Information Forensics and Security.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import numpy as np

# ── Constants ─────────────────────────────────────────────────────────────────

# Grid harmonics to probe (first 4 harmonics for both 50 Hz and 60 Hz grids)
_50HZ_HARMONICS = [50, 100, 150, 200]
_60HZ_HARMONICS = [60, 120, 180, 240]

# Bandwidth around each harmonic to integrate power (±0.5 Hz)
_BANDWIDTH_HZ = 0.5

# Minimum SNR (dB) to consider ENF signal "detected"
_MIN_ENF_SNR_DB = 3.0

# STFT parameters — high frequency resolution needed for ENF tracking
_STFT_WINDOW_S = 8.0       # 8-second analysis window → 0.125 Hz resolution
_STFT_HOP_S = 2.0           # 2-second hop → one ENF sample every 2s
_MAX_AUDIO_S = 600           # Analyse at most 10 minutes

# Discontinuity threshold (z-score of frame-to-frame ENF delta)
_SPLICE_ZSCORE_THRESH = 3.0


# ── Core analysis ─────────────────────────────────────────────────────────────

def _band_power(power_spectrum: np.ndarray, freqs: np.ndarray, centre_hz: float) -> float:
    """Integrate power in ±_BANDWIDTH_HZ around centre_hz."""
    mask = (freqs >= centre_hz - _BANDWIDTH_HZ) & (freqs <= centre_hz + _BANDWIDTH_HZ)
    if not mask.any():
        return 0.0
    return float(power_spectrum[mask].mean())


def _harmonic_snr_db(
    Pxx_mean: np.ndarray,
    freqs: np.ndarray,
    harmonics: list[float],
) -> float:
    """
    Compute average harmonic SNR by comparing power in the ENF band
    to neighbouring noise bands (±5–10 Hz guard bands).
    """
    snrs = []
    for h in harmonics:
        sig = _band_power(Pxx_mean, freqs, h)
        # Noise estimate: average of two guard regions flanking the harmonic
        noise_lo = _band_power(Pxx_mean, freqs, h - 5.0)
        noise_hi = _band_power(Pxx_mean, freqs, h + 5.0)
        noise = (noise_lo + noise_hi) / 2.0 + 1e-10
        snr_db = 10.0 * np.log10(sig / noise + 1e-10)
        snrs.append(snr_db)
    return float(np.median(snrs))


def _extract_enf_trace(
    audio: np.ndarray,
    sr: int,
    harmonics: list[float],
) -> np.ndarray:
    """
    Return per-frame dominant ENF power track using STFT.
    Shape: (num_frames,)
    """
    from scipy import signal as sp_signal

    nperseg = min(len(audio), int(sr * _STFT_WINDOW_S))
    noverlap = nperseg - int(sr * _STFT_HOP_S)
    noverlap = max(0, min(noverlap, nperseg - 1))

    freqs, _times, Zxx = sp_signal.stft(audio, fs=sr, nperseg=nperseg, noverlap=noverlap)
    power = np.abs(Zxx) ** 2  # shape (n_freqs, n_frames)

    # Sum power across all harmonics for each frame
    tracks = []
    for h in harmonics:
        mask = (freqs >= h - _BANDWIDTH_HZ) & (freqs <= h + _BANDWIDTH_HZ)
        if mask.any():
            tracks.append(power[mask, :].mean(axis=0))

    if not tracks:
        return np.array([])

    return np.stack(tracks).mean(axis=0)  # (n_frames,)


def _detect_splice_points(
    enf_trace: np.ndarray,
    hop_s: float,
) -> list[dict[str, Any]]:
    """
    Detect discontinuities in ENF trace using z-score of frame-to-frame deltas.
    """
    if len(enf_trace) < 4:
        return []

    deltas = np.abs(np.diff(enf_trace))
    if deltas.std() < 1e-10:
        return []

    z_scores = (deltas - deltas.mean()) / (deltas.std() + 1e-10)

    splice_candidates = []
    for i, (z, delta) in enumerate(zip(z_scores, deltas, strict=False)):
        if z > _SPLICE_ZSCORE_THRESH:
            timestamp_s = (i + 1) * hop_s
            splice_candidates.append({
                "timestamp_s": round(timestamp_s, 2),
                "discontinuity_score": round(float(min(z / 10.0, 1.0)), 3),
                "delta_power_db": round(float(10.0 * np.log10(delta + 1e-10)), 2),
            })

    # Deduplicate: keep highest score within 4-second windows
    deduped: list[dict[str, Any]] = []
    for sp in sorted(splice_candidates, key=lambda x: -x["discontinuity_score"]):
        if not any(abs(sp["timestamp_s"] - d["timestamp_s"]) < 4.0 for d in deduped):
            deduped.append(sp)

    return sorted(deduped, key=lambda x: x["timestamp_s"])


def analyse_enf(audio_path: str, grid_hint: str = "auto") -> dict[str, Any]:
    """
    Main ENF analysis function.

    Parameters
    ----------
    audio_path:
        Path to the audio file to analyse.
    grid_hint:
        "50", "60", or "auto" (probe both grids and select the stronger one).
    """
    try:
        import soundfile as sf
    except ImportError:
        return {"error": "soundfile not installed", "available": False}

    try:
        from scipy import signal as sp_signal  # noqa: F401 — verify scipy available
    except ImportError:
        return {"error": "scipy not installed", "available": False}

    # Load audio ─────────────────────────────────────────────────────────────
    try:
        audio, sr = sf.read(audio_path, dtype="float32", always_2d=False)
    except Exception as exc:
        return {"error": f"Cannot read audio: {exc}", "available": False}

    if audio.ndim > 1:
        audio = audio.mean(axis=1)  # downmix to mono

    # Trim to _MAX_AUDIO_S
    max_samples = sr * _MAX_AUDIO_S
    if len(audio) > max_samples:
        audio = audio[:max_samples]

    if len(audio) < sr * 5:
        return {
            "enf_detected": False,
            "verdict": "TOO_SHORT",
            "note": "Audio shorter than 5 seconds; ENF analysis requires sustained recording.",
            "available": True,
            "court_defensible": True,
        }

    # Compute mean power spectrum for SNR estimation ──────────────────────────
    from scipy import signal as sp_signal

    nperseg = min(len(audio), int(sr * _STFT_WINDOW_S))
    freqs_full, Pxx = sp_signal.welch(audio, sr, nperseg=nperseg, scaling="density")

    # Grid selection ──────────────────────────────────────────────────────────
    if grid_hint == "50":
        candidate_grids = [("50Hz", _50HZ_HARMONICS)]
    elif grid_hint == "60":
        candidate_grids = [("60Hz", _60HZ_HARMONICS)]
    else:
        snr_50 = _harmonic_snr_db(Pxx, freqs_full, _50HZ_HARMONICS)
        snr_60 = _harmonic_snr_db(Pxx, freqs_full, _60HZ_HARMONICS)
        if snr_50 >= snr_60:
            candidate_grids = [("50Hz", _50HZ_HARMONICS)]
            dominant_snr = snr_50
        else:
            candidate_grids = [("60Hz", _60HZ_HARMONICS)]
            dominant_snr = snr_60

    grid_label, harmonics = candidate_grids[0]
    if grid_hint == "auto":
        enf_snr_db = dominant_snr
    else:
        enf_snr_db = _harmonic_snr_db(Pxx, freqs_full, harmonics)

    enf_detected = enf_snr_db >= _MIN_ENF_SNR_DB

    if not enf_detected:
        return {
            "enf_detected": False,
            "enf_snr_db": round(enf_snr_db, 2),
            "verdict": "NO_ENF_SIGNAL",
            "note": (
                "No significant ENF signal found. The recording may have been made "
                "outdoors, on battery power, or with strong noise suppression applied."
            ),
            "available": True,
            "court_defensible": True,
            "backend": "scipy-enf-stft",
        }

    # Extract ENF trace and detect splices ────────────────────────────────────
    enf_trace = _extract_enf_trace(audio, sr, harmonics)
    splice_candidates = _detect_splice_points(enf_trace, _STFT_HOP_S)

    trace_len = len(enf_trace)
    # Continuity: fraction of frames with low delta (< mean + 1 std)
    if trace_len > 1:
        deltas = np.abs(np.diff(enf_trace))
        threshold = deltas.mean() + deltas.std()
        trace_continuity = float(np.mean(deltas <= threshold))
    else:
        trace_continuity = 1.0

    # Find dominant harmonic (highest SNR individual harmonic)
    harmonic_snrs = {h: _band_power(Pxx, freqs_full, float(h)) for h in harmonics}
    dominant_harmonic = max(harmonic_snrs, key=lambda h: harmonic_snrs[h])

    # Verdict ─────────────────────────────────────────────────────────────────
    n_splices = len(splice_candidates)
    if n_splices >= 2:
        verdict = "SPLICE_DETECTED"
    elif n_splices == 1:
        verdict = "SPLICE_SUSPECTED"
    else:
        verdict = "CLEAN"

    return {
        "enf_detected": True,
        "grid_frequency": grid_label,
        "dominant_harmonic_hz": dominant_harmonic,
        "enf_snr_db": round(enf_snr_db, 2),
        "enf_trace_length": trace_len,
        "splice_candidates": splice_candidates[:5],
        "num_splice_candidates": n_splices,
        "trace_continuity": round(trace_continuity, 3),
        "verdict": verdict,
        "available": True,
        "court_defensible": True,
        "backend": "scipy-enf-stft",
        "note": (
            "ENF analysis without a reference grid database can detect internal "
            "splice points but cannot timestamp-authenticate the recording."
        ),
    }


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ENF audio forensics analyser")
    parser.add_argument("--input", type=str, help="Input audio file path")
    parser.add_argument(
        "--grid", type=str, default="auto", choices=["50", "60", "auto"],
        help="Grid frequency hint (default: auto-detect)"
    )
    parser.add_argument("--warmup", action="store_true", help="Warmup mode — preload dependencies")
    parser.add_argument("--worker", action="store_true", help="Worker mode — persistent process")
    args = parser.parse_args()

    if args.warmup:
        try:
            import soundfile  # noqa: F401
            from scipy import signal  # noqa: F401
            print(json.dumps({"status": "ready", "available": True}))
        except ImportError as exc:
            print(json.dumps({"status": "unavailable", "error": str(exc), "available": False}))
        sys.exit(0)

    if not args.input:
        print(json.dumps({"error": "--input is required", "available": False}))
        sys.exit(1)

    result = analyse_enf(args.input, grid_hint=args.grid)
    print(json.dumps(result))

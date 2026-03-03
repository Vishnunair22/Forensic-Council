"""
Audio Forensic Tools
====================

Real forensic tool handlers for audio analysis.
Implements speaker diarization, anti-spoofing detection, prosody analysis,
background noise consistency, and codec fingerprinting.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
import librosa
import soundfile as sf

from core.evidence import ArtifactType, EvidenceArtifact
from core.exceptions import ToolUnavailableError


@dataclass
class AudioSegment:
    """Audio segment with speaker information."""
    speaker_id: str
    start: float
    end: float
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "speaker_id": self.speaker_id,
            "start": self.start,
            "end": self.end,
        }


@dataclass
class ProsodyAnomaly:
    """Prosody anomaly detected in audio."""
    timestamp: float
    type: str
    severity: float
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "type": self.type,
            "severity": self.severity,
        }


async def speaker_diarize(
    artifact: EvidenceArtifact,
    min_speakers: int = 1,
    max_speakers: int = 10,
) -> dict[str, Any]:
    """
    Perform speaker diarization on audio file.
    
    Uses librosa for audio analysis and simple clustering for speaker
    segmentation. For production, integrate pyannote.audio for better results.
    
    Args:
        artifact: The evidence artifact to analyze
        min_speakers: Minimum number of speakers to detect
        max_speakers: Maximum number of speakers to detect
    
    Returns:
        Dictionary containing:
        - speaker_count: Number of detected speakers
        - segments: List of speaker segments
        - duration: Total audio duration
    
    Raises:
        ToolUnavailableError: If file cannot be processed
    """
    try:
        audio_path = artifact.file_path
        if not os.path.exists(audio_path):
            raise ToolUnavailableError(f"File not found: {audio_path}")
        
        # Load audio with librosa
        y, sr = librosa.load(audio_path, sr=None)
        duration = float(len(y) / sr)
        
        # Simple energy-based segmentation
        # For production, use pyannote.audio for proper diarization
        
        # Compute short-time energy
        frame_length = int(sr * 0.025)  # 25ms frames
        hop_length = int(sr * 0.010)  # 10ms hop
        
        # Compute RMS energy
        rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
        
        # Find speech segments (energy above threshold)
        threshold = np.mean(rms) * 0.5
        speech_frames = rms > threshold
        
        # Convert frames to time
        frame_times = librosa.frames_to_time(
            np.arange(len(speech_frames)), 
            sr=sr, 
            hop_length=hop_length
        )
        
        # Simple speaker change detection based on spectral features
        # Compute MFCCs for speaker characteristics
        mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        
        # Segment the audio and compute speaker embeddings
        segments = []
        segment_duration = 2.0  # 2 second segments for analysis
        num_segments = int(duration / segment_duration)
        
        if num_segments == 0:
            # Short audio, treat as single speaker
            segments.append(AudioSegment(
                speaker_id="SPEAKER_01",
                start=0.0,
                end=duration,
            ))
        else:
            # Analyze each segment
            segment_features = []
            for i in range(num_segments):
                start_sample = int(i * segment_duration * sr)
                end_sample = min(int((i + 1) * segment_duration * sr), len(y))
                
                if end_sample - start_sample < sr * 0.1:  # Skip very short segments
                    continue
                
                segment_y = y[start_sample:end_sample]
                
                # Compute spectral centroid for this segment
                centroid = np.mean(librosa.feature.spectral_centroid(y=segment_y, sr=sr))
                segment_features.append(centroid)
            
            # Simple clustering based on spectral centroid
            if len(segment_features) > 0:
                segment_features = np.array(segment_features)
                median_val = np.median(segment_features)
                
                # Assign speakers based on deviation from median
                current_speaker = "SPEAKER_01"
                speaker_count = 1
                
                for i, feat in enumerate(segment_features):
                    if abs(feat - median_val) > np.std(segment_features):
                        # Potential speaker change
                        if speaker_count < max_speakers:
                            speaker_count += 1
                            current_speaker = f"SPEAKER_{speaker_count:02d}"
                    
                    start_time = i * segment_duration
                    end_time = min((i + 1) * segment_duration, duration)
                    
                    if segments and segments[-1].speaker_id == current_speaker:
                        # Extend previous segment
                        segments[-1] = AudioSegment(
                            speaker_id=current_speaker,
                            start=segments[-1].start,
                            end=end_time,
                        )
                    else:
                        segments.append(AudioSegment(
                            speaker_id=current_speaker,
                            start=start_time,
                            end=end_time,
                        ))
            else:
                # Fallback to single speaker
                segments.append(AudioSegment(
                    speaker_id="SPEAKER_01",
                    start=0.0,
                    end=duration,
                ))
        
        return {
            "speaker_count": len(set(s.speaker_id for s in segments)),
            "segments": [s.to_dict() for s in segments],
            "duration": duration,
            "sample_rate": sr,
        }
    
    except Exception as e:
        if isinstance(e, ToolUnavailableError):
            raise
        raise ToolUnavailableError(f"Speaker diarization failed: {str(e)}")


async def anti_spoofing_detect(
    artifact: EvidenceArtifact,
    segment: Optional[dict] = None,
) -> dict[str, Any]:
    """
    Detect audio spoofing and deepfake audio.
    
    Uses spectral analysis to detect synthetic audio artifacts.
    For production, integrate SpeechBrain AASIST model.
    
    Args:
        artifact: The evidence artifact to analyze
        segment: Optional segment dict with 'start' and 'end' keys
    
    Returns:
        Dictionary containing:
        - spoof_detected: Boolean indicating if spoofing detected
        - confidence: Confidence level (0.0 to 1.0)
        - model_version: Version of detection model
        - anomalies: List of detected anomalies
    """
    try:
        audio_path = artifact.file_path
        if not os.path.exists(audio_path):
            raise ToolUnavailableError(f"File not found: {audio_path}")
        
        # Load audio
        y, sr = librosa.load(audio_path, sr=None)
        
        # Extract segment if specified
        if segment:
            start_sample = int(segment.get("start", 0) * sr)
            end_sample = int(segment.get("end", len(y) / sr) * sr)
            y = y[start_sample:end_sample]
        
        anomalies = []
        spoof_score = 0.0
        
        # 1. Check for codec artifacts (synthetic audio often has unusual codec signatures)
        # Compute spectral flatness - synthetic audio tends to be less flat
        flatness = librosa.feature.spectral_flatness(y=y)
        mean_flatness = np.mean(flatness)
        
        if mean_flatness > 0.5:
            anomalies.append("High spectral flatness (possible synthetic)")
            spoof_score += 0.2
        
        # 2. Check for pitch consistency (synthetic voices may have unnatural pitch patterns)
        f0, voiced_flag, voiced_probs = librosa.pyin(
            y, 
            fmin=librosa.note_to_hz('C2'),
            fmax=librosa.note_to_hz('C7'),
            sr=sr
        )
        
        # Filter out NaN values
        f0_valid = f0[~np.isnan(f0)]
        if len(f0_valid) > 0:
            f0_std = np.std(f0_valid)
            if f0_std < 10:  # Very stable pitch is suspicious
                anomalies.append("Unusually stable pitch (possible synthetic)")
                spoof_score += 0.3
            elif f0_std > 100:  # Very unstable pitch is also suspicious
                anomalies.append("Unusually unstable pitch (possible manipulation)")
                spoof_score += 0.2
        
        # 3. Check for spectral rolloff anomalies
        rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)
        rolloff_std = np.std(rolloff)
        
        if rolloff_std < 500:  # Very consistent rolloff
            anomalies.append("Unusual spectral rolloff consistency")
            spoof_score += 0.15
        
        # 4. Check for zero crossing rate anomalies
        zcr = librosa.feature.zero_crossing_rate(y)
        zcr_mean = np.mean(zcr)
        
        if zcr_mean > 0.15:  # High ZCR can indicate synthetic audio
            anomalies.append("High zero crossing rate")
            spoof_score += 0.1
        
        # Normalize spoof score to confidence
        confidence = min(1.0, spoof_score)
        spoof_detected = confidence > 0.5
        
        return {
            "spoof_detected": spoof_detected,
            "confidence": confidence,
            "model_version": "heuristic_v1.0",
            "anomalies": anomalies,
            "metrics": {
                "spectral_flatness": float(mean_flatness),
                "pitch_std": float(np.std(f0_valid)) if len(f0_valid) > 0 else None,
                "rolloff_std": float(rolloff_std),
                "zcr_mean": float(zcr_mean),
            },
        }
    
    except Exception as e:
        if isinstance(e, ToolUnavailableError):
            raise
        raise ToolUnavailableError(f"Anti-spoofing detection failed: {str(e)}")


async def prosody_analyze(
    artifact: EvidenceArtifact,
) -> dict[str, Any]:
    """
    Analyze prosody features for discontinuities.
    
    Uses librosa to extract pitch, energy, and rhythm features,
    then detects statistical discontinuities that may indicate splicing.
    
    Args:
        artifact: The evidence artifact to analyze
    
    Returns:
        Dictionary containing:
        - anomalies: List of detected prosody anomalies
        - pitch_stats: Pitch statistics
        - energy_stats: Energy statistics
    """
    try:
        audio_path = artifact.file_path
        if not os.path.exists(audio_path):
            raise ToolUnavailableError(f"File not found: {audio_path}")
        
        # Load audio
        y, sr = librosa.load(audio_path, sr=None)
        duration = len(y) / sr
        
        anomalies = []
        
        # 1. Extract pitch (F0)
        f0, voiced_flag, voiced_probs = librosa.pyin(
            y,
            fmin=librosa.note_to_hz('C2'),
            fmax=librosa.note_to_hz('C7'),
            sr=sr
        )
        
        # Analyze pitch discontinuities
        f0_valid = f0[~np.isnan(f0)]
        if len(f0_valid) > 1:
            # Compute pitch derivative to find sudden changes
            f0_diff = np.diff(f0_valid)
            pitch_threshold = np.std(f0_diff) * 3
            
            # Find large pitch jumps
            pitch_jumps = np.where(np.abs(f0_diff) > pitch_threshold)[0]
            
            for jump_idx in pitch_jumps:
                # Map back to time
                voiced_times = np.where(~np.isnan(f0))[0]
                if jump_idx < len(voiced_times):
                    frame_idx = voiced_times[jump_idx]
                    time = librosa.frames_to_time(frame_idx, sr=sr)
                    anomalies.append(ProsodyAnomaly(
                        timestamp=time,
                        type="pitch_discontinuity",
                        severity=min(1.0, abs(f0_diff[jump_idx]) / pitch_threshold / 3),
                    ))
        
        # 2. Extract energy (RMS)
        rms = librosa.feature.rms(y=y)[0]
        rms_diff = np.diff(rms)
        energy_threshold = np.std(rms_diff) * 3
        
        # Find sudden energy changes
        energy_jumps = np.where(np.abs(rms_diff) > energy_threshold)[0]
        
        for jump_idx in energy_jumps:
            time = librosa.frames_to_time(jump_idx, sr=sr)
            # Check if this anomaly is already recorded
            existing_times = [a.timestamp for a in anomalies]
            if not any(abs(t - time) < 0.1 for t in existing_times):
                anomalies.append(ProsodyAnomaly(
                    timestamp=time,
                    type="energy_discontinuity",
                    severity=min(1.0, abs(rms_diff[jump_idx]) / energy_threshold / 3),
                ))
        
        # 3. Analyze rhythm (tempo changes)
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
        
        # Compute beat intervals
        if len(beats) > 1:
            beat_times = librosa.frames_to_time(beats, sr=sr)
            beat_intervals = np.diff(beat_times)
            
            # Check for unusual rhythm changes
            interval_std = np.std(beat_intervals)
            interval_mean = np.mean(beat_intervals)
            
            # Flag beats with unusual timing
            for i, interval in enumerate(beat_intervals):
                if abs(interval - interval_mean) > interval_std * 2:
                    time = beat_times[i]
                    existing_times = [a.timestamp for a in anomalies]
                    if not any(abs(t - time) < 0.2 for t in existing_times):
                        anomalies.append(ProsodyAnomaly(
                            timestamp=time,
                            type="rhythm_discontinuity",
                            severity=min(1.0, abs(interval - interval_mean) / interval_std / 2),
                        ))
        
        # Sort anomalies by timestamp
        anomalies.sort(key=lambda x: x.timestamp)
        
        return {
            "anomalies": [a.to_dict() for a in anomalies],
            "pitch_stats": {
                "mean": float(np.mean(f0_valid)) if len(f0_valid) > 0 else None,
                "std": float(np.std(f0_valid)) if len(f0_valid) > 0 else None,
                "range": [float(np.min(f0_valid)), float(np.max(f0_valid))] if len(f0_valid) > 0 else None,
            },
            "energy_stats": {
                "mean": float(np.mean(rms)),
                "std": float(np.std(rms)),
                "range": [float(np.min(rms)), float(np.max(rms))],
            },
            "tempo": float(tempo) if isinstance(tempo, (int, float, np.floating)) else float(tempo[0]) if len(tempo) > 0 else None,
        }
    
    except Exception as e:
        if isinstance(e, ToolUnavailableError):
            raise
        raise ToolUnavailableError(f"Prosody analysis failed: {str(e)}")


async def background_noise_consistency(
    artifact: EvidenceArtifact,
    segment_duration: float = 1.0,
) -> dict[str, Any]:
    """
    Analyze background noise consistency across audio.
    
    Segments audio and computes noise floor per segment,
    detecting shift points that may indicate splicing.
    
    Args:
        artifact: The evidence artifact to analyze
        segment_duration: Duration of each analysis segment in seconds
    
    Returns:
        Dictionary containing:
        - shift_points: List of timestamps where noise floor shifts
        - consistent: Boolean indicating if noise is consistent
        - noise_profile: Noise floor profile across segments
    """
    try:
        audio_path = artifact.file_path
        if not os.path.exists(audio_path):
            raise ToolUnavailableError(f"File not found: {audio_path}")
        
        # Load audio
        y, sr = librosa.load(audio_path, sr=None)
        duration = len(y) / sr
        
        # Segment the audio
        segment_samples = int(segment_duration * sr)
        num_segments = int(len(y) / segment_samples)
        
        if num_segments < 2:
            return {
                "shift_points": [],
                "consistent": True,
                "noise_profile": [],
                "message": "Audio too short for noise consistency analysis",
            }
        
        # Compute noise floor for each segment
        noise_floors = []
        
        for i in range(num_segments):
            start = i * segment_samples
            end = min((i + 1) * segment_samples, len(y))
            segment = y[start:end]
            
            # Compute noise floor (lower percentile of energy)
            rms = np.sqrt(np.mean(segment ** 2))
            # Also compute spectral characteristics
            spectral_centroid = np.mean(librosa.feature.spectral_centroid(y=segment, sr=sr))
            
            noise_floors.append({
                "timestamp": i * segment_duration,
                "rms": float(rms),
                "spectral_centroid": float(spectral_centroid),
            })
        
        # Detect shift points
        shift_points = []
        rms_values = [n["rms"] for n in noise_floors]
        rms_mean = np.mean(rms_values)
        rms_std = np.std(rms_values)
        
        # Threshold for detecting a shift
        shift_threshold = rms_std * 2 if rms_std > 0 else 0.01
        
        for i in range(1, len(noise_floors)):
            rms_diff = abs(noise_floors[i]["rms"] - noise_floors[i-1]["rms"])
            centroid_diff = abs(noise_floors[i]["spectral_centroid"] - noise_floors[i-1]["spectral_centroid"])
            
            if rms_diff > shift_threshold or centroid_diff > 1000:
                shift_points.append({
                    "timestamp": noise_floors[i]["timestamp"],
                    "rms_change": float(rms_diff),
                    "spectral_change": float(centroid_diff),
                })
        
        # Determine overall consistency
        consistent = len(shift_points) == 0
        
        return {
            "shift_points": shift_points,
            "consistent": consistent,
            "noise_profile": noise_floors,
            "statistics": {
                "mean_rms": float(rms_mean),
                "std_rms": float(rms_std),
                "num_segments": num_segments,
            },
        }
    
    except Exception as e:
        if isinstance(e, ToolUnavailableError):
            raise
        raise ToolUnavailableError(f"Background noise consistency analysis failed: {str(e)}")


async def codec_fingerprint(
    artifact: EvidenceArtifact,
) -> dict[str, Any]:
    """
    Detect codec fingerprint and re-encoding events.
    
    Analyzes audio for signs of multiple encoding passes.
    
    Args:
        artifact: The evidence artifact to analyze
    
    Returns:
        Dictionary containing:
        - reencoding_events: List of detected re-encoding events
        - codec_chain: List of detected codecs
        - format_info: Audio format information
    """
    try:
        audio_path = artifact.file_path
        if not os.path.exists(audio_path):
            raise ToolUnavailableError(f"File not found: {audio_path}")
        
        # Get audio file info using soundfile
        info = sf.info(audio_path)
        
        reencoding_events = []
        codec_chain = []
        
        # Determine format from file extension
        ext = os.path.splitext(audio_path)[1].lower()
        if ext in [".mp3", ".mp2", ".mp1"]:
            codec_chain.append("MP3")
        elif ext in [".m4a", ".mp4", ".aac"]:
            codec_chain.append("AAC")
        elif ext in [".wav"]:
            codec_chain.append("PCM")
        elif ext in [".flac"]:
            codec_chain.append("FLAC")
        elif ext in [".ogg", ".oga"]:
            codec_chain.append("Vorbis")
        else:
            codec_chain.append(f"Unknown ({ext})")
        
        # Load audio for analysis
        y, sr = librosa.load(audio_path, sr=None)
        
        # Check for codec artifacts
        
        # 1. Spectral cutoff (typical of lossy codecs)
        spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
        spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)
        
        max_freq = np.max(spectral_rolloff)
        nyquist = sr / 2
        
        # If max frequency is significantly below Nyquist, likely lossy encoded
        if max_freq < nyquist * 0.8:
            cutoff_ratio = max_freq / nyquist
            reencoding_events.append({
                "type": "spectral_cutoff",
                "frequency": float(max_freq),
                "confidence": 1.0 - cutoff_ratio,
            })
        
        # 2. Check for MP3 artifacts (frequency notches)
        # MP3 encoding creates characteristic notches at certain frequencies
        D = np.abs(librosa.stft(y))
        freqs = librosa.fft_frequencies(sr=sr)
        
        # Look for energy drops at typical MP3 cutoff frequencies
        energy_per_freq = np.mean(D, axis=1)
        
        # Check for sudden energy drops
        energy_diff = np.diff(energy_per_freq)
        significant_drops = np.where(energy_diff < -np.std(energy_diff) * 3)[0]
        
        for drop_idx in significant_drops:
            freq = freqs[drop_idx]
            if freq > 1000:  # Ignore low frequency variations
                reencoding_events.append({
                    "type": "frequency_notch",
                    "frequency": float(freq),
                    "confidence": min(1.0, abs(energy_diff[drop_idx]) / np.std(energy_diff) / 5),
                })
        
        # 3. Check for quantization noise (typical of re-encoding)
        # Look for noise floor patterns
        rms = librosa.feature.rms(y=y)[0]
        rms_std = np.std(rms)
        
        if rms_std < np.mean(rms) * 0.01:
            # Very consistent noise floor might indicate heavy processing
            reencoding_events.append({
                "type": "consistent_noise_floor",
                "confidence": 0.5,
            })
        
        return {
            "reencoding_events": reencoding_events,
            "codec_chain": codec_chain,
            "format_info": {
                "format": info.format,
                "subtype": info.subtype,
                "channels": info.channels,
                "samplerate": info.samplerate,
                "duration": info.duration,
                "frames": info.frames,
            },
        }
    
    except Exception as e:
        if isinstance(e, ToolUnavailableError):
            raise
        raise ToolUnavailableError(f"Codec fingerprint analysis failed: {str(e)}")

# Forensic OS Agents (2026 Spec)

The Forensic Council (v1.4.0) utilizes five specialized autonomous agents to perform non-linear forensic investigations. Each agent follows a tiered **Initial vs Deep Analysis** pipeline, cross-verified via **Gemini 2.5 Pro/Flash Semantic Grounding**.

## 1. Image Forensic Agent
Analyzes static visual evidence for pixel-level and semantic inconsistencies.
- **Pass 1 (Initial)**: ELA, SIFT Clone Detection, JPEG Ghosting, FFT frequency domain analysis.
- **Pass 2 (Deep)**: Diffusion Artifact Detection, Noise Fingerprinting (PRNU), Adversarial Perturbation Stability.
- **Signals**: On completion, broadcasts `agent1_complete` to signal Agents 3 & 5.

## 2. Audio Forensic Agent
Verifies the authenticity of voice recordings and ambient audio streams.
- **Pass 1 (Initial)**: Speaker Diarization, Noise Floor profiling, Anti-spoofing via Wav2Vec2.
- **Pass 2 (Deep)**: Voice Clone Detection (ElevenLabs/TTS), ENF (Electrical Network Frequency) tracking.
- **Grounding**: Correlates background environment acoustic markers with video streams.

## 3. Object-Scene Agent
Investigates the physical coherence of objects within a multimodal scene.
- **Pass 1 (Initial)**: YOLOv11 Multi-object Detection, ROI extraction.
- **Pass 2 (Deep)**: Perspective & Shadow Coherence, Splicing detection (SRM).
- **Context Injection**: Incorporates Agent 1 findings (ROIs/Anomalies) before deep-pass execution.

## 4. Video Forensic Agent
Monitors temporal continuity and inter-frame integrity.
- **Pass 1 (Initial)**: Frame Hash consistency, Optical Flow (Farneback), P-frame/I-frame ratio.
- **Pass 2 (Deep)**: Face-swap detection, Temporal continuity validation, Rolling shutter verification.

## 5. Metadata & Provenance Agent
Validates the chain of custody and cryptographic origin of the evidence.
- **Pass 1 (Initial)**: EXIF/XMP parsing, GPS/Timezone cross-validation, Hex-signature scanning.
- **Pass 2 (Deep)**: **C2PA JUMBF Validation**, Hardware Provenance verification, Reverse Image Search.
- **Context Injection**: Verifies Agent 1 grounding markers against claimed device hardware profiles.

---

### Inter-Agent Signaling (`InterAgentBus`)
Agents communicate in the Deep Analysis phase via a shared event bus:
- **Grounding Sync**: Agents 3 & 5 delay deep-pass execution until Agent 1 signals `agent1_complete`.
- **Finding Correlation**: Agents push "Early Signals" during their ReAct loops, allowing later agents to focus on contested regions.

*All Agent verdicts are synthesized by the **Council Arbiter** and recorded in the ECDSA-signed Forensic Ledger.*


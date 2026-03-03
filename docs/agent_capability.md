# Agent Capabilities: ML Subprocess Implementations

The Forensic Council agents have been updated to utilize a new subsystem of machine learning analysis tools. To ensure zero idle memory footprint, all ML code has been decoupled from the backend REST API server and runs as isolated Python CLI scripts (`asyncio.create_subprocess_exec`). Models are loaded into memory only during inference.

This document serves as an audit of the newly integrated capabilities.

## Overview of ML Tools

All ML tools are implemented in `backend/scripts/ml_tools/` and accessed via the `run_ml_tool` wrapper.

| Tool Script | Algorithm | Purpose | Calling Agents |
| :--- | :--- | :--- | :--- |
| `ela_anomaly_classifier.py` | `IsolationForest` | Classify Error Level Analysis (ELA) DCT block statistics to find manipulated regions. | Agent 1 |
| `splicing_detector.py` | `GaussianMixture` | Detect image splicing by analyzing inconsistencies in JPEG quantization tables. | Agent 1, Agent 3 |
| `noise_fingerprint.py` | `IsolationForest` | Detect camera sensor noise fingerprint (PRNU) inconsistencies using Wiener filters. | Agent 1, Agent 3 |
| `deepfake_frequency.py` | `OneClassSVM` | Identify GAN/deepfake artifacts by analyzing frequency-domain (2D-DFT) features. | Agent 1, Agent 4 |
| `audio_splice_detector.py` | `IsolationForest` | Detect audio splicing points by analyzing sudden shifts in MFCC features via `librosa`. | Agent 2 |
| `metadata_anomaly_scorer.py` | `IsolationForest` + Rules | Score EXIF metadata for tampering based on absent fields, timezone mismatches, and structural checks. | Agent 5 |

## Agent Integration Audit

### Agent 1 (Image Integrity)
**Focus:** Detect manipulation, splicing, compositing, and anti-forensics at the pixel level.
*   **Integrated Handlers:**
    *   `ela_anomaly_classify`: Calls `ela_anomaly_classifier.py`
    *   `splicing_detect`: Calls `splicing_detector.py`
    *   `noise_fingerprint`: Calls `noise_fingerprint.py`
    *   `deepfake_frequency_check`: Calls `deepfake_frequency.py`
*   **Task Decomposition Status:** Updated successfully. The agent's plan now explicitly includes these four ML execution steps.

### Agent 2 (Audio & Multimedia Forensics)
**Focus:** Detect audio deepfakes, splices, re-encoding events, and prosody anomalies.
*   **Integrated Handlers:**
    *   `audio_splice_detect`: Calls `audio_splice_detector.py`
*   **Task Decomposition Status:** Updated successfully. ML-based splice point detection on audio segments is now explicitly in the 11-step plan.

### Agent 3 (Object & Weapon Analysis)
**Focus:** Contextual validation, object detection, and lighting inconsistency checks.
*   **Integrated Handlers:**
    *   `image_splice_check`: Calls `splicing_detector.py`
    *   `noise_fingerprint`: Calls `noise_fingerprint.py`
*   **Task Decomposition Status:** Updated successfully. The agent now runs image splicing detection and noise fingerprint analysis on confirmed objects to verify spatial compositing logic.

### Agent 4 (Temporal Video Analysis)
**Focus:** Frame-level edit points, deepfake face swaps, and temporal inconsistencies.
*   **Integrated Handlers:**
    *   `deepfake_frequency_check`: Calls `deepfake_frequency.py` (applied to extracted frames).
*   **Task Decomposition Status:** Updated successfully. The agent now executes frequency-domain GAN artifact detection on extracted frames as part of its pipeline.

### Agent 5 (Metadata & Context Analysis)
**Focus:** EXIF metadata analysis, GPS-timestamp consistency, and provenance analysis.
*   **Integrated Handlers:**
    *   `metadata_anomaly_score`: Calls `metadata_anomaly_scorer.py`
*   **Task Decomposition Status:** Updated successfully. Explicit ML anomaly scoring has been added to the metadata verification chain.

## Tool Execution Wrapper (`ml_subprocess.py`)

A standardized wrapper was implemented across all 5 agents to handle the complexity of CLI execution:
*   **Timeout Management:** Hard cap set (e.g., 25.0 seconds) via `asyncio.wait_for` to prevent hanging subprocesses from stalling the ReAct loop.
*   **Safe Argument Passing:** Uses isolated arguments (`--input`, `--quality`, `--window`) without shell pipes.
*   **Graceful Parsing:** Extracts JSON data from stdout, disregarding potential stderr warnings from libraries (like CUDA/Tensorflow initialization messages), and gracefully falls back to error dictionaries if the payload is unparseable. 

This architecture successfully completes the implementation requirement of transferring heavy ML dependency loads to short-lived child processes.

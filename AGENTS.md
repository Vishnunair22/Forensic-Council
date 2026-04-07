# Forensic OS Agents (2026 Spec)

The Forensic Council (v1.3.0) utilizes five specialized autonomous agents to perform non-linear forensic investigations. Each agent follows a tiered **Initial vs Deep Analysis** pipeline, cross-verified via **Gemini 3.1 Semantic Grounding**.

## 1. Image Forensic Agent
Analyzes static visual evidence for pixel-level and semantic inconsistencies.
- **Pass 1 (Classical)**: Error Level Analysis (ELA), SIFT-based Clone Detection, JPEG Ghosting.
- **Pass 2 (20)26 Forensic)**: **Diffusion Artifact Detection** (Stable Diffusion/Midjourney hallmarks), AI-upscaling artifacts.
- **Semantic Grounding**: ROI-aware scene analysis via Gemini 3.1; cross-references ELA anomalies with physical light sources.

## 2. Audio Forensic Agent
Verifies the authenticity of voice recordings and ambient audio streams.
- **Pass 1 (Classical)**: Spectral Centroid analysis, Speaker Diarization, Noise Floor profiling.
- **Pass 2 (2026 Forensic)**: **Voice Synthesis Detection** (ElevenLabs/VALL-E detection), Phase-shift anomaly detection in vocoders.
- **Semantic Grounding**: Behavioral intent analysis; flags "impossible" speech patterns or synthetic cadence.

## 3. Object-Scene Agent
Investigates the physical coherence of objects within a multimodal scene.
- **Pass 1 (Classical)**: YOLOv11 Multi-object Detection, Bounding box overlap analysis.
- **Pass 2 (20)26 Forensic)**: **Perspective & Shadow Coherence**, Ray-traced shadow verification.
- **Semantic Grounding**: 3D geometric validation; flags objects that violate the physical perspective of the captured scene.

## 4. Video Forensic Agent
Monitors temporal continuity and inter-frame integrity.
- **Pass 1 (Classical)**: Frame Hash consistency, Optical Flow (Farneback), P-frame/I-frame ratio analysis.
- **Pass 2 (2026 Forensic)**: **Inter-frame Forgery Detection**, FaceSwap embedding discontinuity analysis (DeepFace).
- **Semantic Grounding**: Temporal flow verification; flags subtle motion vector spikes that contradict the global camera movement.

## 5. Metadata & Provenance Agent
Validates the chain of custody and cryptographic origin of the evidence.
- **Pass 1 (Classical)**: EXIF/XMP parsing, GPS/Timezone cross-validation, Hex-signature scanning.
- **Pass 2 (20)26 Forensic)**: **C2PA JUMBF Validation (2026)**, Hardware Provenance verification.
- **Semantic Grounding**: Device profile correlation; verifies if the file structure matches the claimed capturing hardware.

---
*All Agent verdicts are synthesized by the **Council Arbiter** and recorded in the ECDSA-signed Forensic Ledger.*

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
|------|----------|
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.

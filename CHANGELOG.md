# Changelog

All notable changes to the Forensic Council project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] - 2026-03-02
### Added
- **Multi-Agent Core Pipeline**: Sequential execution loop for 5 active agents (Image, Audio, Object, Video, Metadata).
- **Arbiter Synthesis Module**: Compiles cross-modal findings into cohesive verdicts.
- **Machine Learning Subsystem**: Deepfake detection, ELA, noise fingerprinting, and metadata parsing tools offloaded as secure subprocesses to avoid event-loop blocking.
- **WebSocket Streaming**: Live `THOUGHT` and `ACTION` blocks mirrored in real-time from backend to frontend UI.
- **Human-In-The-Loop (HITL)**: Webhook support to request mandatory operator decisions when agents contest each other.
- **Deterministic Cryptography**: Reports are signed deterministically with an ECDSA scheme based on `SIGNING_KEY` environment variables.

### Changed
- **Memory Management**: Redis models updated with 24-hour TTLs (`ex=86400`) to remedy memory leak issues during heavy load.
- **Container Architecture**: Optimized multi-stage Docker builds using `uv` to drastically reduce image sizes.
- **UI Aesthetics**: Adopted "cyber-analytic" framework complete with Tailwind v4, Framer Motion, and 3D visualization grids via `@react-three/fiber`.

### Fixed
- CORS blocking bugs resolved by standardizing `NEXT_PUBLIC_API_URL` during Next.js standalone build.
- Fixed AttributeErrors across backend ML handlers related to literal string property usage.

## [0.1.0] - Initial Alpha Prototype
### Added
- Initial setup of FastAPI backend and standalone React interface.
- Basic routing and placeholder endpoints for single-agent analysis logic.

# Forensic Council — Decisions, Patterns & Institutional Memory

Last updated: 2026-03-31 (post-audit hardening sprint)

---

## Architecture Decisions

### Why Two-Phase Pipeline
Fast initial results (15-20s) let users see something quickly without waiting for heavy ML models (2-5 min). Phase 2 is opt-in — the user controls depth. This also reduces Gemini API costs and GPU load for simple cases.

### Why Five Separate Agents Instead of One
Each agent has a different analysis domain requiring different ML models and tools. Running them in parallel and then cross-referencing findings (via arbiter) produces more reliable verdicts than a monolithic approach. Contradictions between agents are a meaningful forensic signal.

### Why ECDSA P-256 for Signing (Not RSA or Ed25519)
P-256 is the most widely accepted curve in legal/government contexts (NIST approved). Ed25519 is faster but less widely supported in courtroom evidence standards as of the project's design phase.

### Why Groq as Primary LLM (Not OpenAI)
Groq's hardware inference is significantly faster for the ReAct loop reasoning steps, which need low latency per iteration. Gemini is used specifically for vision tasks (deep pass) where Groq has no native vision support.

### Why Redis is Optional in Dev
Redis adds infrastructure complexity for local development. Working memory falls back to an in-memory dict when Redis is unavailable. In production, Redis is required (rate limiting, token blacklist, WebSocket pub/sub). Redis unavailability is now tracked as a degradation_flag.

### Why PostgreSQL for Chain of Custody (Not a blockchain)
Append-only PostgreSQL with cryptographic linking (prior_entry_ref) achieves the same tamper-evidence guarantees as a blockchain without the operational complexity. Chain integrity is now verified at report generation time via `verify_chain()`.

### Why Qdrant is Optional (Graceful Degradation)
Vector similarity search for historical finding correlation is a "nice to have" feature. Not having it doesn't break investigations — tracked as a degradation_flag when unavailable.

### Why 60-Minute JWT Expiry
Longer than typical web apps (15-30 min) because forensic investigations can take 2-5+ minutes per phase. Shorter than persistent tokens because evidence systems require tighter access controls.

### Calibration Honesty Policy (added 2026-03-31)
All confidence scores from default (unfitted) Platt parameters are marked `CalibrationStatus.UNCALIBRATED`. The `court_statement` field on all uncalibrated findings explicitly states "NOT court-admissible". This was added because the original code cited academic papers (Zampoglou 2020, Khodabakhsh 2018, NIST MFC 2019) for parameters that were actually hardcoded by a developer — a legal liability. To produce court-admissible scores, run a real calibration training script against a labelled forensic dataset and call `save_trained_model()`.

---

## Known Issues & Fixed Bugs (as of 2026-03-31 audit)

### FIXED: Silent Degradation Without Disclosure
Five subsystems (Gemini, LLM ReAct, Qdrant, Redis, Arbiter timeout) previously degraded silently. Now all degradation paths append to `report.degradation_flags` (list[str]). The frontend result page shows a prominent amber warning banner when non-empty. The flags are included in the cryptographic signature.

### FIXED: Arbiter Config Mutation Race Condition
`pipeline.py` used to set `self.arbiter.config.llm_api_key = None` when the arbiter timed out — a shared-config mutation that could disable LLM for concurrent investigations. Fixed: `deliberate()` now accepts `use_llm: bool = True` parameter. The timeout path calls `deliberate(..., use_llm=False)`.

### FIXED: Custody Chain Never Verified
`custody_logger.verify_chain()` existed but was never called. Now called in `pipeline.py` before `sign_report()`. A failed verification adds a CRITICAL degradation flag and is logged as an error.

### FIXED: Gemini Model String Wrong
Default was `gemini-3-pro-preview` (not a real model). Changed to `gemini-1.5-pro` in both `config.py` and `.env.example`.

### FIXED: Fictional Calibration Parameters
Removed false academic citations. Parameters are now documented as engineering defaults. `CalibrationStatus.UNCALIBRATED` is set on all default models. Court statements now explicitly say "NOT court-admissible".

### KNOWN ISSUE: Audio ML Is 2017-Level (Partially Fixed)
`audio_tools.py` now attempts pyannote.audio neural diarization and SpeechBrain ECAPA anti-spoofing if installed. Falls back to librosa with `analysis_source: "librosa_spectral_fallback"` and a DEGRADED caveat. Install pyannote.audio + speechbrain + torchaudio for full neural audio analysis. `HF_TOKEN` is required for pyannote.

### KNOWN ISSUE: Single Master Signing Key
All agent keys are derived from one `SIGNING_KEY` via HMAC-SHA256 (signing.py:132). If `SIGNING_KEY` leaks, all historical signatures become forgeable. Documented with a clear warning in `get_or_create()`. Mitigation: rotate `SIGNING_KEY` via secrets manager. Full per-agent independent key storage requires a DB schema change (not yet implemented).

### Image Preview in Upload Modal
Use native `<img>` for base64 data URLs — NOT Next.js `<Image>`. Next.js Image requires domain allowlist and does not support base64 data URLs.

---

## Patterns Used Across the Codebase

### Degradation Flag Pattern (added 2026-03-31)
When any subsystem falls back to reduced capability:
1. Append a human-readable string to `pipeline._degradation_flags`
2. After `deliberate()` returns, flags are extended to `report.degradation_flags`
3. Flags are included in the cryptographic signature (signed before `sign_report()`)
4. Frontend renders amber warning banner when non-empty

### Tool Registry Pattern
All agent tools are registered with `ToolRegistry`. Centralized error handling, custody logging, and 60s per-tool timeout (`asyncio.wait_for`). Always register new tools through the registry.

### ReAct Loop Pattern
THOUGHT → ACTION → OBSERVATION. LLM-driven when `LLM_API_KEY` + `llm_enable_react_reasoning=True`. Falls back to hardcoded task list. All steps logged to custody chain.

### Custody Logger Pattern
Every meaningful forensic step logged via `CustodyLogger`. ECDSA-signed, linked to prior entry. Now verified at report generation time. Non-negotiable for legal defensibility.

### Structured Logging
All logging uses `get_logger(__name__)` from `core/structured_logging.py`. JSON-structured output. No bare `print()` or `logging.getLogger()`.

### Async Everything
All backend I/O is async. No `time.sleep()`, no synchronous DB calls, no `requests` — use `asyncio.sleep()`, `asyncpg`, `httpx.AsyncClient`.

### CalibrationStatus Pattern
`CalibrationStatus.TRAINED` = fitted to real data → scores are evidentially meaningful.
`CalibrationStatus.UNCALIBRATED` = developer defaults → scores are indicative only, NOT court-admissible.
Always check `calibration_status` before citing a score in legal context.

---

## Production Checklist (Don't Deploy Without These)

1. `APP_ENV=production`
2. `SIGNING_KEY` = unique 32-char hex (not dev placeholder) — store in secrets manager
3. `POSTGRES_PASSWORD` = strong, not `forensic_pass`
4. `REDIS_PASSWORD` = strong
5. `BOOTSTRAP_ADMIN_PASSWORD` and `BOOTSTRAP_INVESTIGATOR_PASSWORD` set
6. `DOMAIN` set for Caddy auto-TLS
7. `LLM_API_KEY` set (Groq recommended)
8. `GEMINI_API_KEY` set — use `gemini-1.5-pro` model (NOT `gemini-3-pro-preview`)
9. `HF_TOKEN` set for pyannote.audio neural diarization (Agent 2)
10. Ports 80 and 443 open for Caddy
11. Verify `report.degradation_flags` is empty on first test investigation
12. Run `pytest tests/ --ignore=tests/connectivity -v` before go-live

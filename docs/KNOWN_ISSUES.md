# Known Issues

Active issues and limitations in the Forensic Council system.

## Tool Fallbacks

Several forensic tools use simplified fallback implementations when ML models are unavailable. Findings produced by fallbacks are marked with `"degraded": true` and `"fallback_reason"` in their metadata. The DegradationBanner in the frontend displays these flags.

Affected tools:
- ELA anomaly classifier (falls back to local heuristic)
- PRNU noise fingerprint (falls back to pixel-domain variance check)
- Speaker diarization (falls back to energy-based VAD)
- All audio tools with scipy-based inline fallbacks

## Compression Penalty

Social media and messaging app compression degrades pixel-level forensic signals (ELA, JPEG ghost, copy-move). The arbiter applies a compression penalty to affected tools when metadata indicates a known platform (WhatsApp, Instagram, Telegram). See `arbiter.py` `_FRAGILE_TOOLS` for the full list.

## Gemini API Rate Limits

The free Gemini API tier has rate limits that may cause 429 errors during concurrent deep analysis of multiple agents. The system uses an ordered fallback chain (`gemini-2.5-flash` â†’ `gemini-2.0-flash` â†’ `gemini-2.0-flash-lite`) and skips backoff on 404/429 to fail fast.

## Session State Volatility

Active investigation sessions are held in process memory. If the API server restarts, in-progress investigations are lost. Completed reports are persisted to PostgreSQL and survive restarts.


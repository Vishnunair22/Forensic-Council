# Phase: Production Hardening

## Current Context
We are refining the evidence pipeline to fix critical logic bugs and improve multimodal depth.

## Active Task
- **Phase 1 Structural Audit**: Completed — all fixes implemented, code verified.

## Todo
- [x] Fix `arbiter.py` dead code (diffusion penalty) — Already done (was dead constant `_MANIP_TOP_K`, removed)
- [x] Fix `agent2_audio.py` iteration ceiling — Covered by base_agent.py fix
- [x] Fix `agent4_video.py` iteration ceiling — Covered by base_agent.py fix
- [x] Add `try/except` guards to `agent3_object.py` Gemini calls — Fixed: wrapped in outer try/except
- [x] Implement `_generate_spectrogram` in `gemini_client.py` — Already done (fully implemented)
- [x] Migrate `sessionStorage` to `localStorage` — Fixed: all non-auth keys migrated to @/lib/storage
- [x] Update Typography to Title Case — Already done (verdict.ts provides display labels)

## Done
- [x] Create GSD Infrastructure (PROJECT.md, ROADMAP.md)
- [x] Audit for logic gaps (Complete)
- [x] Phase 1 Structural Audit (2026-04-15) — All fixes applied

## Blocked
- None


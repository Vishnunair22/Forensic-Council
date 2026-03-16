# Development Status

**Last updated:** 2026-03-16
**Current version:** v1.0.3
**Overall health:** 🟢 Production-ready
**Actively working on:** —
**Blocked on:** None

---

## Pipeline Health

```
Upload → [✅] → Evidence Store → [✅] → Agent Dispatch → [✅] → Council Arbiter → [✅] → Signing → [✅] → Report
```

| Stage | Status | Notes |
|-------|--------|-------|
| File Upload | ✅ | MIME + extension allowlists, 50MB limit, non-blocking async I/O |
| Evidence Store | ✅ | Immutable storage with SHA-256 integrity check |
| WebSocket Stream | ✅ | 12s connection timeout, CONNECTED/AGENT_UPDATE bootstrap, CancelledError re-raised |
| Agent Dispatch | ✅ | All 5 agents concurrent; file-type validation per agent; heartbeat every 0.2s |
| Initial Analysis | ✅ | Tools run → Groq synthesises findings → PIPELINE_PAUSED → Accept/Deep buttons |
| Deep Analysis | ✅ | Agent1 Gemini runs first → context injected into Agent3+Agent5 → fresh deep cards |
| Council Arbiter | ✅ | Skipped agents filtered; deduplication; 5-tier verdict; per-agent Groq narrative |
| Report Signing | ✅ | ECDSA P-256 + SHA-256, PostgreSQL custody log |
| Result Page | ✅ | Pre-computed verdict, per-agent analysis, initial/deep split, client-side dedup |

---

## v1.0.3 Complete Fix Log (2026-03-16)

### Critical Bug Fixes

| # | File | Issue | Fix |
|---|------|-------|-----|
| 1 | `evidence/page.tsx` | `useRef` lazy-init bug — `.current` was a function not a string, causing 422 on every POST | Replaced `useRef<string>(() => {...})` with `useRef<string>(_initInvestigatorId())` |
| 2 | `useSimulation.ts` | `clearCompletedAgents` didn't clear `agentUpdates` — stale initial-phase text persisted in deep phase | Added `setAgentUpdates({})` to `clearCompletedAgents` |
| 3 | `react_loop.py` | `update_state()` called without `agent_id` — iteration tracking wrote to wrong Redis key (`""`) | Added `agent_id=self.agent_id` to all 3 `update_state` calls |
| 4 | `investigation.py` | Deep pass `run_agent_deep_pass` used all agents including skipped ones | Added `_agent_was_active()` filter; skipped agents excluded from deep queue |
| 5 | `base_agent.py` | `run_deep_investigation()` returned combined initial+deep findings — duplicated initial cards in deep phase | Changed to return only deep findings; `self._findings` still holds combined for arbiter |

### Feature Additions

| # | What | Where |
|---|------|-------|
| 1 | 5-tier verdict: CERTAIN / LIKELY / UNCERTAIN / INCONCLUSIVE / MANIPULATION DETECTED | `arbiter.py` |
| 2 | Per-agent Groq narrative comparing initial vs deep findings | `arbiter.py → _generate_agent_narrative()` |
| 3 | `AgentMetrics` model with error_rate + confidence_score per agent | `arbiter.py`, `schemas.py` |
| 4 | Phase-aware Groq synthesis: deep-pass prompt includes initial findings for comparison | `base_agent.py → _synthesize_findings_with_llm(phase=...)` |
| 5 | Agent1 Gemini result injected into Agent3 + Agent5 after deep pass | `investigation.py → run_agent_deep_pass()` |
| 6 | Agent5 `_shared_agent1_context` + `inject_agent1_context()` classmethod | `agent5_metadata.py` |
| 7 | `envelope_open` / `envelope_close` / `scan` Web Audio API sounds | `useSound.ts` |
| 8 | `MicroscopeScanner`, `EnvelopeCTA`, `GlassCard` UI components | `app/page.tsx` |
| 9 | Syne + JetBrains Mono fonts replacing Poppins | `layout.tsx`, `globals.css` |
| 10 | `GlobalFooter` academic disclaimer on all pages (landing, evidence, result, error) | `components/ui/GlobalFooter.tsx` |
| 11 | `PageTransition` + `StaggerIn`/`StaggerChild` smooth page transitions | `components/ui/PageTransition.tsx` |
| 12 | `cursor: pointer` on all buttons/interactive elements; `btn` utility classes | `globals.css` |
| 13 | Glass card agent cards with skeleton loading, shimmer bar, ping badge | `AgentProgressDisplay.tsx` |
| 14 | `per_agent_analysis`, `per_agent_metrics`, `overall_verdict` propagated to result page | Full stack: arbiter → schemas → sessions → api.ts → result page |
| 15 | AgentSection: Groq narrative primary, initial/deep split, client-side dedup, collapsed raw | `result/page.tsx` |

### Audit Fixes (Sessions 1–2)

| # | File | Fix |
|---|------|-----|
| B3 | `metrics.py` | `_KEY_DURATION_SUM` suffix aligned |
| B4 | `sessions.py` | WebSocket loop re-raises `CancelledError` |
| B5 | `pipeline.py` | `_setup_infrastructure` uses `get_redis_client()` singleton |
| B9 | `logging.py` | `get_logger` uses dict cache instead of `@lru_cache` |
| B10 | `redis_client.py` | `set()` returns `result is True` |
| B11 | `retry.py` | `CircuitBreaker.state` property is pure (side effects extracted) |
| D3 | `sessions.py` | `get_agent_brief` queries live working memory |
| D4 | `sessions.py` | `get_session_checkpoints` queries `hitl_checkpoints` table |
| D6 | `evidence/page.tsx` | `investigatorId` generated once on mount |
| D7 | `useSimulation.ts` | Dead `_phaseGen` stale-detection code removed |
| D10 | `pyproject.toml` | `numpy>=1.26,<2.0` upper bound added |
| D13–D15 | `test_auth.py`, `test_security.py`, `test_api_routes.py` | Correct import names and patch targets |
| D16 | `types/index.ts` | `AgentResult.metadata` field added |
| E1–E6 | Various | Temp file cleanup, done-callback, `gather(return_exceptions=True)`, DB wait_for, 503 on DB error, per-call retry flag |

---

## Known Limitations

| Area | Limitation |
|------|-----------|
| Agent execution | Sequential within each phase (not parallel) to maintain stable WebSocket streaming |
| LLM inference | No fallback if Groq/Gemini API is unavailable during analysis |
| Video analysis | Frame extraction is CPU-intensive; files >200 MB may timeout on slow machines |
| Deep analysis timing | Agent1 Gemini runs sequentially before Agent3/Agent5 to enable context sharing (~30–90s) |

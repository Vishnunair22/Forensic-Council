Forensic Council — 3-Phase Audit & Redesign Plan
Repo: github.com/Vishnunair22/Forensic-Council (branch main, v1.4.0)
Stack: Next.js 15 + React 19 + Tailwind v4 + Framer Motion 12 (web) / FastAPI + Python 3.12 (api) / Redis, Postgres, Qdrant, Caddy.

PHASE 1 — FRONTEND AUDIT & REDESIGN (Glassmorphic Blue)
Files audited (web)
apps/web/next.config.ts, middleware.ts, tsconfig.json, package.json
src/app/layout.tsx, app/page.tsx, app/globals.css, app/evidence/page.tsx, app/result/page.tsx, app/error.tsx, app/*/layout.tsx, app/*/error.tsx, app/session-expired/page.tsx, app/not-found.tsx, app/global-error.tsx
All src/components/ui/* (GlassPanel, GlobalNavbar, GlobalFooter, LandingBackground, HeroAuthActions, HowWorksSection, AgentsSection, ForensicProgressOverlay, ForensicErrorModal, ForensicResetOverlay, AgentFindingCard, AgentIcon, AnimatedNumber, Badge, BrandLogo, DarkBackgroundAnimation, LoadingOverlay, MicroscopeBackground, PageTransition, QueryProvider, RouteExperience, Toaster, dialog)
All src/components/evidence/* (FileUploadSection, UploadModal, UploadSuccessModal, AnalysisProgressOverlay, AgentProgressDisplay, AgentStatusCard, HITLCheckpointModal, QuotaMeter, ErrorDisplay, ForensicTimeline)
All src/components/result/* (ResultLayout, ResultHeader, ResultStateView, IntelligenceBrief, AgentAnalysisTab, AgentFindingSubComponents, ArcGauge, DeepModelTelemetry, DegradationBanner, EvidenceThumbnail, HistoryPanel, MetricsPanel, ReportFooter, ActionDock, TribunalMatrix, TimelineTab)
Hooks: useSound, useSoundscape, useInvestigation, useResult, useForensicData, useForensicSfx, useReducedMotion, useSessionStorage, useSimulation, useTimer, use-mobile, use-toast
Libs: design-tokens, api.ts, api/client, backendTargets, constants, schemas, storage, tool-icons, tool-progress, utils, verdict
🔴 P0 BLOCKERS — Undefined CSS utilities (silent visual breakage)
Tailwind v4 uses @theme{} to register tokens. Only a subset is defined in globals.css. The codebase references MANY classes that resolve to no styles or render text invisible.

Missing in @theme or @layer:

text-danger, bg-danger, border-danger → no --color-danger token defined. Used in: AgentFindingCard.tsx:53,305, AgentStatusCard.tsx:48,188,250, ForensicErrorModal.tsx (≥8 refs), FileUploadSection.tsx:261,263, HistoryPanel.tsx:36,152, ForensicProgressOverlay.tsx:125. Result: red alert states currently render as transparent/default text.
text-warning, bg-warning, border-warning → no --color-warning token. Used in AgentFindingCard.tsx:54, HistoryPanel.tsx:35.
text-success, bg-success → --color-success token IS defined; Tailwind v4 will auto-generate, OK.
horizon-card — referenced in ≥10 files (ForensicErrorModal, UploadModal, UploadSuccessModal, HistoryPanel, HeroAuthActions, AgentsSection indirectly…) — not defined anywhere.
premium-glass, premium-card, bg-grid-small, border-border-subtle, bg-surface-1/2/3 are referenced; only bg-surface-1/2/3 are defined.
btn-pill-secondary — referenced in evidence/page.tsx:161 — not defined.
custom-scrollbar — referenced in AgentStatusCard.tsx:273 — not defined.
.skeleton — referenced in ResultLayout.tsx:222,231,… — not defined (skeleton renders as a plain empty div).
text-glow-cyan, text-hero-gradient are defined but unused in final layouts.
FIX (add to globals.css @theme + base layer):

@theme {
  /* Blue-centric palette (replaces cyan/mint) */
  --color-primary: #3B82F6;          /* sky-500 */
  --color-primary-rgb: 59, 130, 246;
  --color-primary-soft: #93C5FD;      /* sky-300 */
  --color-accent: #60A5FA;            /* sky-400 */
  --color-accent-rgb: 96, 165, 250;

  --color-success: #34D399;
  --color-success-rgb: 52, 211, 153;
  --color-success-light: #A7F3D0;

  --color-warning: #F59E0B;
  --color-warning-rgb: 245, 158, 11;

  --color-danger:  #F43F5E;
  --color-danger-rgb: 244, 63, 94;

  /* Surfaces */
  --color-background: #05070D;        /* deep navy-black */
  --color-foreground: #F1F5F9;
  --color-surface-1: #070A12;
  --color-surface-2: #0C111E;
  --color-surface-3: #111830;

  /* Borders (shared) */
  --color-border-subtle: rgba(148,163,184,0.08);

  /* Glass tokens */
  --glass-bg: rgba(59,130,246,0.05);
  --glass-border: rgba(147,197,253,0.18);
  --glass-highlight: rgba(255,255,255,0.06);
  --glass-blur: 20px;

  --radius-xl: 18px;
  --radius-2xl: 28px;
  --radius-full: 9999px;
}

@layer utilities {
  .bg-surface-1 { background-color: var(--color-surface-1); }
  .bg-surface-2 { background-color: var(--color-surface-2); }
  .bg-surface-3 { background-color: var(--color-surface-3); }
  .border-border-subtle { border-color: var(--color-border-subtle); }

  .bg-grid-small {
    background-image:
      linear-gradient(to right, rgba(147,197,253,0.05) 1px, transparent 1px),
      linear-gradient(to bottom, rgba(147,197,253,0.05) 1px, transparent 1px);
    background-size: 20px 20px;
  }

  .custom-scrollbar::-webkit-scrollbar { width: 6px; }
  .custom-scrollbar::-webkit-scrollbar-thumb {
    background: rgba(147,197,253,0.2); border-radius: 999px;
  }
  .custom-scrollbar { scrollbar-width: thin; scrollbar-color: rgba(147,197,253,0.2) transparent; }

  .skeleton {
    background: linear-gradient(90deg,
      rgba(147,197,253,0.04) 0%,
      rgba(147,197,253,0.10) 50%,
      rgba(147,197,253,0.04) 100%);
    background-size: 200% 100%;
    animation: skeleton-shimmer 1.6s infinite linear;
  }
  @keyframes skeleton-shimmer {
    0% { background-position: 200% 0; } 100% { background-position: -200% 0; }
  }
}

/* Unified glass primitives */
.glass-panel,
.horizon-card,
.premium-glass,
.premium-card {
  position: relative;
  background: var(--glass-bg);
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(140%);
  backdrop-filter: blur(var(--glass-blur)) saturate(140%);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-2xl);
  box-shadow:
    inset 0 1px 0 var(--glass-highlight),
    inset 0 0 0 1px rgba(59,130,246,0.04),
    0 24px 60px -20px rgba(0,0,0,0.75),
    0 0 0 1px rgba(59,130,246,0.06);
  transition: transform .45s cubic-bezier(.22,1,.36,1),
              border-color .35s ease, box-shadow .35s ease;
}
.glass-panel::before,
.horizon-card::before {
  content:""; position:absolute; inset:0; border-radius:inherit; pointer-events:none;
  background:
    radial-gradient(120% 80% at 0% 0%, rgba(147,197,253,0.08), transparent 60%),
    radial-gradient(80% 120% at 100% 100%, rgba(59,130,246,0.06), transparent 60%);
  mix-blend-mode: screen;
}
.glass-panel:hover,
.horizon-card:hover {
  border-color: rgba(147,197,253,0.28);
  box-shadow:
    inset 0 1px 0 var(--glass-highlight),
    0 30px 80px -20px rgba(0,0,0,.85),
    0 0 40px rgba(59,130,246,0.12);
  transform: translateY(-2px);
}

/* Blue-centric buttons (replaces btn-horizon-primary / outline) */
.btn-primary, .btn-horizon-primary {
  --ring: rgba(59,130,246,.35);
  display:inline-flex; align-items:center; justify-content:center; gap:.55rem;
  padding: .95rem 2.2rem; border-radius: 999px;
  font: 700 .78rem/1 var(--font-heading);
  letter-spacing:.12em; text-transform:uppercase;
  color: #04070F !important;
  background: linear-gradient(135deg, #93C5FD 0%, #3B82F6 60%, #2563EB 100%);
  border: 1px solid rgba(147,197,253,.7);
  box-shadow: 0 10px 30px -8px rgba(59,130,246,.6),
              inset 0 1px 0 rgba(255,255,255,.35);
  transition: transform .25s, box-shadow .25s, filter .25s;
}
.btn-primary:hover { transform: translateY(-1px); filter:brightness(1.08); box-shadow: 0 14px 40px -10px rgba(59,130,246,.75); }

.btn-outline, .btn-horizon-outline, .btn-pill-secondary {
  display:inline-flex; align-items:center; justify-content:center; gap:.55rem;
  padding:.9rem 2rem; border-radius: 999px;
  font: 600 .78rem/1 var(--font-heading); letter-spacing:.12em; text-transform:uppercase;
  color: rgba(226,232,240,.9);
  background: rgba(147,197,253,.05);
  border: 1px solid rgba(147,197,253,.18);
  -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px);
  transition: background .25s, border-color .25s, color .25s, box-shadow .25s;
}
.btn-outline:hover { background: rgba(147,197,253,.1); border-color: rgba(147,197,253,.35); color:#fff; box-shadow: 0 0 24px rgba(59,130,246,.18); }

.glass-button {
  background: rgba(147,197,253,0.06);
  border: 1px solid rgba(147,197,253,0.18);
  -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px);
  color:#fff; padding:.75rem 1.4rem; border-radius: 999px;
  font-weight:600; transition: background .3s, border-color .3s, box-shadow .3s;
}
.glass-button:hover { background: rgba(147,197,253,.12); border-color: rgba(147,197,253,.4); box-shadow:0 0 22px rgba(59,130,246,.22); }

:focus-visible { outline:2px solid var(--color-primary); outline-offset:2px; }
🔴 P0 — Duplicate / wrong footers
app/page.tsx renders its own <footer> (lines 78–82) AND layout.tsx renders GlobalFooter — footer appears twice on landing.
Fix: delete the inline <footer> in page.tsx.
🔴 P0 — LandingBackground invisible
globals.css sets body { background-color: var(--color-background) } AND .bg-mesh-container { position:fixed; z-index:-1 }. A z-index of -1 goes behind the body's paint layer in some browsers → orbs never appear.
Fix:

html, body { background-color: transparent; }
:root { background-color: var(--color-background); }
.bg-mesh-container { z-index: 0; }
main { position: relative; z-index: 10; }
🔴 P0 — ForensicErrorModal close button is non-functional
ForensicErrorModal.tsx:51 — <Dialog.Root open={isVisible} onOpenChange={() => {}}> — onOpenChange is a no-op. The Dialog.Close button at line 144 and ESC key cannot dismiss the modal; only onHome/onRetry work. Also Dialog.Close without an explicit handler relies on Radix's internal open-state change which we've suppressed.
Fix:

<Dialog.Root open={isVisible} onOpenChange={(open) => { if (!open) onHome?.(); }}>
or pass an explicit onClose prop and wire the Close button's onClick.

🟠 P1 — Font wiring inconsistencies (layout.tsx + globals.css)
layout.tsx creates Plus_Jakarta_Sans and assigns --font-outfit (misnamed variable).
globals.css --font-heading: 'Plus Jakarta Sans' hardcodes the name instead of var(--font-outfit) → heading font relies on Google Fonts network fallback even though Next inlined the font.
--font-mono: 'JetBrains Mono' same problem (should be var(--font-mono-jb)).
--font-geist-mono loaded but never referenced.
Fix (layout.tsx):

const plusJakarta = Plus_Jakarta_Sans({ subsets:["latin"], variable:"--font-heading-family", display:"swap" });
const jetbrainsMono = JetBrains_Mono({ subsets:["latin"], variable:"--font-mono-family", display:"swap" });
// drop Geist_Mono — unused
Fix (globals.css @theme):

--font-sans: var(--font-geist), system-ui, sans-serif;
--font-heading: var(--font-heading-family), var(--font-geist), sans-serif;
--font-mono: var(--font-mono-family), ui-monospace, monospace;
🟠 P1 — Mixed palette fights the "blue" requirement
btn-horizon-primary currently uses var(--color-success-light) (mint green). The entire Evidence / Result flow (FileUploadSection, AgentProgressDisplay, AgentStatusCard, ResultLayout tabs, "Active_Nodes" HUD) all highlight with mint green. User explicitly asked for blue clickable elements.
Fix: Replace every var(--color-success-light) used in CTA/HUD/progress contexts with var(--color-primary) / var(--color-primary-soft). Keep --color-success only for authentic-verdict semantics on the Result page. Audit:

FileUploadSection.tsx lines 93–98, 145, 211, 228, 240 → --color-primary-soft
AgentProgressDisplay.tsx lines 223–224, 241–243 → --color-primary
AgentStatusCard.tsx lines 48, 65–69, 163, 177, 187, 212–213, 227, 292 → --color-primary
ResultLayout.tsx line 88 active tab pill → --color-primary
🟠 P1 — Accessibility gaps
UploadModal.tsx close button (line 72) has no aria-label. Add aria-label="Close upload dialog".
AnalysisProgressOverlay.tsx has no role="dialog" aria-live="polite" or aria-busy. Add role="status" aria-live="polite" plus a visually-hidden screen-reader description.
ForensicProgressOverlay.tsx: decorative floating log has no role="log" aria-live="polite" — screen-reader users miss progress updates.
Dropzone in FileUploadSection.tsx has role="button" + keyboard handler; add aria-describedby pointing to the supported-types hint.
HistoryPanel.tsx: uses window.confirm (line 29) — not WCAG compliant with custom UI theming. Replace with a Radix dialog confirmation.
GlobalFooter.tsx uses only text-white/10 and text-white/20 on #05070D background — contrast ratio ~1.4:1; fails WCAG AA even for decorative text (and they contain real copyright). Bump to text-white/45 or rgba(241,245,249,0.5).
Result tab nav (ResultLayout.tsx:76–96) uses a role="tablist" but keyboard arrow-key navigation between tabs is not implemented. Add onKeyDown handler (ArrowLeft/ArrowRight to cycle activeTab).
🟠 P1 — Agent live-progress iconography (user requirement: "proper svg icons for live progress text during evidence analysis for all agents")
Currently AgentStatusCard.tsx:155 uses ProgressIcon from tool-progress.ts — need to verify coverage per agent. Known gap: agents only get generic Scan / Activity / Microscope / Cpu / ShieldAlert in AGENT_GRAPHICS (lines 64–70) — same mint color for all, no discrimination between image/audio/object/video/metadata.

Fix — give each agent a distinct SVG + blue hue:

import { ScanEye, Waveform, Boxes, Film, Database } from "lucide-react";
const AGENT_GRAPHICS: Record<string, { icon: LucideIcon; hue: string }> = {
  Agent1: { icon: ScanEye,   hue: "#60A5FA" }, // image — sky-400
  Agent2: { icon: Waveform,  hue: "#38BDF8" }, // audio — sky-500
  Agent3: { icon: Boxes,     hue: "#818CF8" }, // object — indigo-400
  Agent4: { icon: Film,      hue: "#22D3EE" }, // video — cyan-400
  Agent5: { icon: Database,  hue: "#93C5FD" }, // metadata — sky-300
};
And for live per-tool progress, extend lib/tool-progress.ts (getLiveProgressDescriptor) to return a consistent SVG for every tool_name — currently many tools fall back to a generic icon because the registry is partial (verified via lib/tool-icons.ts).

🟡 P2 — Sound / transitions / misc frontend
useSound.ts:456 shadows outer masterGain variable with inner const masterGain = ctx.createGain() inside the hum branch — works due to block scope but confusing; rename to humGain.
useSoundscape.ts:17–21 — if prefers-reduced-motion, the early return skips setting volume. Move setMasterVolume(DEFAULT_VOLUME) before the reduced-motion check.
useSound.ts:58–67 adds a pointerdown listener at module import time. In SSR this is guarded by typeof window !== "undefined", but during HMR the listener can be re-registered; guard with if (!(window as any).__fcAudioBound){ (window as any).__fcAudioBound = true; … }.
Sound coverage missing on decision buttons: AgentProgressDisplay "Accept Verdict" / "Deep Analysis" / "View Report" buttons do not call playSound("click"). Wire them via onAcceptAnalysis/onRunDeepAnalysis wrappers in useInvestigation.
PageTransition.tsx:23 — key={typeof children === 'string' ? children : undefined} — the exit animation never triggers on route change because key is undefined. Pass pathname as the key from the page:
// in evidence/page.tsx and result/page.tsx
<PageTransition key={pathname}>…</PageTransition>
AgentProgressDisplay.tsx:141–155 hardcodes a 10 s timer to hide unsupported agents — tie to the "initial" phase completion event (or pipelineStatus === 'dispatched') instead of a timer.
ForensicProgressOverlay.tsx:115–122 uses fmtDiagnosticTime() inside render — each re-render produces a new timestamp, causing React to re-key log entries incorrectly. Capture the timestamp once when pushing to log state.
next.config.ts:162 X-XSS-Protection:"0" is declared twice (/api/:path* and /(.*)) — dedupe, keep only in global block.
middleware.ts CSP uses style-src 'unsafe-inline' which voids the nonce you build; instead emit style-src 'self' 'nonce-${nonce}' and add the nonce prop to <style> tags Next generates (Next 15 supports experimental.cssChunking + nonce). If not feasible, document the exception.
middleware.ts sets CSP on the response but skips /api/*; however next.config.ts already sets X-Frame-Options: DENY etc. for /api/*. Confirm no duplication — currently global X-Content-Type-Options is defined by both next.config.ts global block AND there's no issue since middleware config excludes /api. Fine, but document.
evidence/page.tsx uses setAutoStartBlocking, setShowLoadingOverlay, sessionOnlyStorage directly in a button handler — OK but should factor into a single resetLoading() helper on the hook to centralize state.
result/page.tsx is a bare one-liner — fine.
HistoryPanel.tsx relies on forensic_history session storage; when a session is deleted via removeItem, there is no confirmation and no data-testid. Add data-testid="history-remove-${sessionId}" and replace window.confirm as noted.
AgentFindingCard.tsx:153 conditional uses !open && flagCfg.bg combined with open && "bg-surface-3" but when bg-surface-3 isn't registered (before fix) the panel is transparent. Covered by the CSS fix above.
UploadSuccessModal.tsx never has a close X button — the user can only proceed via "Reselect File" or "Begin Analysis". Add an explicit close path (ESC/X) for UX parity.
FileUploadSection.tsx:44–53 computeHash silently returns null on failure — consider logging the error in non-prod.
ResultLayout.tsx skeleton still references skeleton class (fixed by CSS addition above) and also unused sticky top-[60px] — there is no 60px header anymore (nav is fixed at top-24); align or remove.
✅ Frontend redesign — Glass Blue design system
Design tokens (CSS vars above). Typography: Space Grotesk for hero (fresh, unexpected, fits the "blue futurist" brief; replace Plus Jakarta Sans), Geist for body, JetBrains Mono for HUD/telemetry. Rationale: user wants something slick/modern, Plus Jakarta is over-used.

Component treatment per screen:

Screen	Component	Redesign directive
Landing	Hero	Drop accent-cyan headline gradient; use linear-gradient(135deg,#F8FAFC 0%, #93C5FD 100%) on headline. Replace mint "Begin Analysis" with the new btn-primary (blue gradient).
Landing	GlassPanel sections	Apply updated .glass-panel (inner highlight + blue radial sheen). Increase padding to p-12 lg:p-16.
Landing	Orbs	Recolor mesh-orb-1 → rgba(59,130,246,0.12), mesh-orb-2 → rgba(147,197,253,0.10).
Upload Modal	UploadModal.tsx	Replace horizon-card interior bg-[#020617] with bg-[var(--color-surface-2)]/80; dashed border → border-[rgba(147,197,253,0.25)]; dragging state uses .glass-panel with shadow-[0_0_40px_rgba(59,130,246,0.25)].
Upload Success	UploadSuccessModal.tsx	Same shell. CheckCircle icon bg → rgba(59,130,246,0.12) with blue glow. "Begin Analysis" → .btn-primary. HUD corners → border-sky-400/40.
Analysis Progress Overlay	AnalysisProgressOverlay.tsx + ForensicProgressOverlay.tsx	Spinner/Aperture node in primary blue. Log categories: info→primary, success→--color-success, error→--color-danger, system→white/50.
Agent Progress (evidence)	AgentProgressDisplay.tsx, AgentStatusCard.tsx	Header card + each agent card use .glass-panel. Progress bar → linear-gradient(90deg,#60A5FA,#3B82F6). Each agent has a distinct blue-shifted icon (table above). Decision dock uses new .btn-primary + .btn-outline.
Arbiter Overlay	ForensicProgressOverlay.tsx (reused)	Add a new central "prism" SVG (three radiating blue rays) that pulses while arbiter deliberates. Use rgba(59,130,246,0.08) underglow.
Result Page	ResultLayout.tsx, ResultHeader, ArcGauge, MetricsPanel	ArcGauge stroke → blue gradient; Authentic/Likely-Manipulated pills retain semantic green/red but sit on glass surfaces. Tab nav pill (active) → .btn-primary.
History	HistoryPanel.tsx	Each card is a .glass-panel with hover-lift; verdict pill keeps semantic colors but uses reduced opacity over glass (bg-danger/10 etc. — now that --color-danger is defined this works).
Decision buttons	AgentProgressDisplay.tsx bottom dock	Uses .glass-panel p-2 rounded-full + inner row of .btn-outline / .btn-primary.
Motion standards (apply globally):

Page enter: opacity 0→1, y 12→0, duration 0.45s, cubic-bezier(.22,1,.36,1)
Card enter: stagger 80ms
Hover: translateY(-2px) + shadow bloom
Reduced-motion respected via existing @media (prefers-reduced-motion) rule
Phase 1 Verification
cd apps/web && npm run lint && npm run type-check — must pass with zero errors.
npm run dev then visit /, /evidence, /result?session_id=dummy, /session-expired, /not-found, trigger error boundary via a bad fetch. Each screen must show:
Coherent blue glass shell end-to-end (no transparent red text, no unstyled skeleton).
Decision / primary buttons in blue gradient.
All 5 agents with distinct SVG icons + blue progress bars.
Arbiter overlay showing prism + live log.
History list cards visible with verdict chips.
Axe check: npm test -- --testPathPattern=accessibility → zero serious violations.
Playwright: npx playwright test tests/e2e/browser_journey.spec.ts must still pass (selectors rely on data-testid — untouched by redesign).
Manual: toggle prefers-reduced-motion: reduce — animations collapse, layout intact.
PHASE 2 — BACKEND AUDIT
Files audited (apps/api)
api/main.py (app bootstrap, CORS, CSP), api/schemas.py, api/constants.py, all api/routes/*
core/* (auth, config, persistence/*, llm_client, gemini_client, rate_limiting, circuit_breaker, audit_logger, custody_logger, signing, scoring, synthesis, verdicts, react_loop, inter_agent_bus, mime_registry, etc.)
agents/* (agent1–agent5, arbiter, arbiter_narrative, arbiter_verdict, base_agent, mixins/*, reflection, tool_handlers)
orchestration/* (pipeline, pipeline_enrichment, pipeline_phases, pipeline_registry, investigation_queue, investigation_runner, session_manager, signal_bus, agent_factory)
tools/* (image_tools, audio_tools, video_tools, metadata_tools, mediainfo_tools, ocr_tools, clip_utils, model_cache, ml_tools/*)
worker.py, scripts/*, probes/*
🔴 P0 — Duplicate security-header surface
api/main.py lines ~440+ build CSP/security headers AND apps/web/next.config.ts + apps/web/src/middleware.ts both emit headers. When Caddy proxies /api/* the browser sees the FastAPI headers; when Next SSR emits pages it sees Next headers. Risk: two conflicting CSPs on the same document if the backend ever serves HTML.
Fix: confirm api/main.py does not add CSP to non-API responses; remove any Content-Security-Policy middleware on api/main.py (FastAPI is JSON-only). If you want a safety net, limit to api_router mount and use headers that don't overlap Next's.

🟠 P1 — CORS & cookies
api/routes/auth.py + api/main.py must:

Set allow_credentials=True only if frontend sends cookies (it does for HttpOnly session). Verify settings.cors_allowed_origins uses explicit origins (never *) when credentials are enabled — wildcard + credentials is rejected by browsers.
Ensure cookies set SameSite=Lax; Secure; HttpOnly; Path=/. In dev over http://localhost, Secure breaks — gate with settings.app_env == "production".
🟠 P1 — Rate-limiter fail-open
api/routes/_rate_limiting.py + core/rate_limiting.py: existing test (tests/security/test_rate_limiter_failopen.py) suggests fail-open is intentional on Redis outage. Ensure:

On Redis error, emit structured_logging.warning AND bump a Prometheus counter (metrics.rate_limiter_fail_open_total).
Never fail-open on auth endpoints; return 503 instead.
🟠 P1 — Evidence / signing
core/signing.py + core/signing.py (ECDSA) — verify HSM-style key rotation path. Confirm keys are loaded from storage/keys/ (gitignored) AND the generate_production_keys.sh script writes them with mode 0600.
core/custody_logger.py must append-only; check it uses fsync before returning so a crash does not lose custody entries.
core/persistence/evidence_store.py + postgres_client.py: ensure SHA-256 is computed server-side (not trusted from client). Search for request.headers.get("x-sha") or ... patterns — if client hash is trusted, that is a P0 tampering vector.
🟠 P1 — LLM / Gemini client
core/gemini_client.py + core/llm_client.py: confirm circuit breaker (core/circuit_breaker.py) wraps ALL external calls. Any direct httpx.post(...) bypassing the breaker is a reliability bug.
Verify GEMINI_FALLBACK_MODELS cascade is applied on 429/503 only, not on 400 (bad payload) or 401 (auth).
Timeouts: must cap each call to <= 30s to avoid pipeline stalls.
🟡 P2 — Agents & pipeline
agents/base_agent.py uses mixins (context, investigation, memory, reflection, synthesis); confirm MRO — Python multiple-inheritance pitfalls. Add super().__init__(*a, **kw) in every mixin and a single test that constructs every agent via agent_factory to catch MRO errors.
agents/agent4_video.py — heavy ML; enforce a hard timeout via asyncio.wait_for to match the frontend expectation ("Deep analysis complete").
orchestration/pipeline_phases.py: ensure deep phase respects hitl_checkpoint decision — a reject must not proceed.
orchestration/signal_bus.py + core/inter_agent_bus.py: two buses with overlapping purpose — document who owns what (cross-agent context vs pipeline signalling). Consolidate if possible.
🟡 P2 — Routes / schemas
api/routes/investigation.py start endpoint must enforce MIME via core/mime_registry.py BEFORE writing bytes to storage/evidence/. Write the file only after validation; otherwise disk fills on junk uploads.
api/routes/sse.py: SSE events should include a retry hint (retry: 2000\n\n) and use heartbeats every 15s to keep Caddy from idling the connection.
api/schemas.py — any datetime field must serialize with UTC ISO-8601 Z suffix for JS compatibility (dt.isoformat().replace('+00:00','Z')). Check pydantic json_encoders.
🟡 P2 — Tests / quality
tests/contracts/test_api_contracts.py exists — ensure every route has a contract test. Generate a coverage diff: any route without a contract is a gap.
tests/security/test_auth_security.py — confirm tests for session cookie flags (Secure, HttpOnly, SameSite), CSRF one-per-session (test_csrf_one_per_session.py exists ✅).
pyproject.toml: ensure ruff + pyright run in CI (they do per npm run lint:api / type-check:api).
Phase 2 Verification
cd apps/api && uv run ruff check . && uv run pyright core/ agents/ api/ tools/ orchestration/ — zero errors.
uv run pytest tests/ -v must pass ≥ 95% (baseline exists).
./infra/validate_production_readiness.sh passes.
Smoke-test: upload → initial → HITL → deep → arbiter → signed report JSON, all with chain-of-custody lines appended for every significant event (tail storage/custody.log).
Abuse tests: curl an unsigned forged session token → 401; send Origin: evil.com → CORS rejects; flood /api/v1/auth/login → rate-limited with 429.
PHASE 3 — EVERYTHING ELSE AUDIT
Files audited
.env.example (12 KB — extensive), .gitignore, .dockerignore, .editorconfig, .gitattributes, .pre-commit-config.yaml
.github/workflows/ci.yml
infra/ (docker-compose.yml, docker-compose.dev.yml, docker-compose.prod.yml, docker-compose.test.yml, Caddyfile, generate_production_keys.sh, validate_production_readiness.sh, prometheus.yml, DOCKER_BUILD.md)
docs/* (ARCHITECTURE, API, CHANGELOG, SCHEMAS, DEPLOYMENT_MIGRATION, RUNBOOK, TESTING, SECURITY, STATE, KNOWN_ISSUES, MONITORING, MAINTENANCE, DEBUGGING, CODE_STYLE, CONTRIBUTING, MODEL_*.md, ADRs)
e2e_test.py, package.json, apps/web/Dockerfile, apps/api/Dockerfile, apps/api/scripts/*, apps/api/probes/*, apps/web/playwright.config.ts, apps/web/jest.config.ts
Findings
.env.example leakage risk. It is 12 KB — likely contains real-looking defaults. Audit every line: no real keys, no real passwords; all values must be placeholders like change-me or generate-via-script. Add a pre-commit hook to grep for patterns like sk-, AIza, -----BEGIN.
apps/web/tsc_errors.txt is committed — 🔴 delete this artifact and add apps/web/tsc_errors.txt to .gitignore.
apps/api/baseline_results.txt — same concern. Tests artifacts do not belong in the repo.
.github/workflows/ci.yml — verify:
Runs npm run lint && npm run test && npm run type-check on PRs.
Pins action versions (actions/checkout@v4, not @main).
Uses uv sync for Python and caches the .venv.
Fails if pyright/ruff/ESLint warnings > 0 (eslint --max-warnings 0 already set in apps/web/package.json).
Docker / infra:
docker-compose.yml — confirm each service has healthcheck: (postgres, redis, qdrant, api, web). Without health checks, depends_on: condition: service_healthy is a no-op.
Caddyfile should set encode zstd gzip, tls {issuer}, and forward X-Real-IP / X-Forwarded-* headers so FastAPI rate-limiter sees real client IP.
docker-compose.prod.yml must override to add restart: unless-stopped, secret mounts, and CPU/memory limits.
prometheus.yml — verify it scrapes /metrics on both api and web (if any). Add Grafana dashboards JSON into infra/ for completeness.
generate_production_keys.sh should chmod 600 the generated files and fail if openssl is missing.
apps/web/Dockerfile — since next.config.ts sets output:"standalone", the Dockerfile should COPY .next/standalone + .next/static + public into a minimal node:20-alpine runtime. Confirm multistage build; reject node_modules in final image.
apps/api/Dockerfile — CPU-only torch (ADR-004) — ensure base image is python:3.12-slim + explicit pip install torch --index-url https://download.pytorch.org/whl/cpu. Confirm .dockerignore excludes storage/, tests/fixtures/, __pycache__/, .venv/, *.pyc.
e2e_test.py lives in repo root but also apps/web/tests/e2e/* exists. Two e2e mechanisms → consolidate under apps/web/tests/e2e or apps/api/tests/integration. Delete the root one OR document its purpose in README.
models.lock.json at apps/api/ — verify it's the Hugging Face model pinning manifest (per docs/MODEL_PINNING.md). Confirm CI fails if models.lock.json changes without a matching entry in docs/CHANGELOG.md.
docs/KNOWN_ISSUES.md — living doc. Ensure every P0/P1 raised in this audit is appended.
.pre-commit-config.yaml — should include ruff, ruff-format, eslint, prettier, detect-secrets, trailing-whitespace. Add detect-secrets if not present.
.editorconfig — OK.
playwright.config.ts — verify CI uses a retry of 2 and workers: process.env.CI ? 2 : undefined.
README.md currently links many docs; verify each anchor exists (broken-link scan: docs/STATE.md, docs/DEVELOPMENT_SETUP.md, etc. — all present ✓).
scripts/hash_password.py — ensure it uses the same hashing algorithm (argon2 / bcrypt) as core/auth.py; add a test that round-trips a generated hash.
apps/api/probes/validate_ml_tools.py — ensure it runs during Docker HEALTHCHECK to detect missing model files early.
Phase 3 Verification
git ls-files | grep -E "tsc_errors|baseline_results" → empty.
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml config → no warnings, all healthchecks present.
./infra/validate_production_readiness.sh → PASS.
gh workflow run ci.yml (or push to a branch) → all jobs green.
pre-commit run --all-files → clean.
Deploy a test container, open browser → no mixed CSP errors in console, only blue glass UI visible, all routes load, history persists across sessions, arbiter signs a report.
Implementation Order (recommended)
Phase 1 — CSS tokens & glass primitives (unblocks all visual rendering). 1 file: globals.css.
Phase 1 — layout.tsx font vars + page.tsx footer removal + LandingBackground z-index. 2 files.
Phase 1 — Color swap to blue across FileUploadSection, AgentProgressDisplay, AgentStatusCard, ResultLayout, HeroAuthActions. ~6 files, mechanical replacement.
Phase 1 — Agent icon differentiation in AgentStatusCard + tool-progress.ts.
Phase 1 — Modal a11y (ForensicErrorModal.onOpenChange, UploadModal aria, HistoryPanel confirm).
Phase 1 — Motion fixes (PageTransition key, ForensicProgressOverlay timestamp bug).
Phase 2 — Security header dedup, evidence MIME validation order, Gemini circuit-breaker coverage.
Phase 2 — Auth cookie flags & CORS credential audit.
Phase 3 — Remove tsc_errors.txt + baseline_results.txt, add .gitignore entries, add detect-secrets pre-commit.
Phase 3 — Docker healthchecks + Caddy headers.
Summary
Root cause of most visible UI breakage: Tailwind v4's @theme registry is missing --color-danger, --color-warning, and ~10 utility classes (horizon-card, premium-glass, skeleton, custom-scrollbar, btn-pill-secondary, bg-grid-small, border-border-subtle) are referenced but never defined. Fixing globals.css unblocks the entire redesign.
Biggest functional bug: ForensicErrorModal cannot be dismissed by the user (no-op onOpenChange).
Biggest UX mismatch: primary CTA uses mint-green (--color-success-light) on every screen; the user wants blue. Centralizing this in .btn-primary makes the change a one-file override.
Biggest backend concern: possible duplicate CSP/security-header surface between FastAPI, Next middleware, and next.config.ts — must deduplicate.
Biggest infra concern: committed test artifacts (tsc_errors.txt, baseline_results.txt) and absence of healthchecks in docker-compose.
Apply Phase 1 first for an immediate end-to-end slick blue glass UI, then Phase 2 for backend correctness, then Phase 3 for hygiene. Each phase has explicit verification steps you can run locally.
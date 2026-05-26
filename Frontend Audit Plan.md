I have a comprehensive picture of the codebase. The frontend is a Next.js 15 / React 19 / Tailwind v4 monorepo app (apps/web) with a well-documented design system, deep WebSocket/SSE streaming, multi-phase pipeline state, and forensic report rendering. Below is the full forensic audit, written here in chat as you requested.

Forensic Frontend Audit — Forensic Council (apps/web)
Audit basis: pure static analysis of the uploaded archive. No runtime execution. Where evidence is insufficient, I state so explicitly.

Frontend stack confirmed (from package.json, next.config.ts, globals.css, source tree):

Next.js 15.5 (App Router, Turbopack, standalone output)
React 19.2
Tailwind v4 (@tailwindcss/postcss), CSS-variable theme via @theme
Framer Motion 12, Radix Dialog, Lucide
TanStack Query 5
Strict ESLint (next/typescript, max-warnings 0), jest-axe, Playwright (3 browsers), CSP middleware
Documented design system: FRONTEND_DESIGN_SYSTEM.md (Precision Frosted Glass)
1. Executive Summary
Overall maturity
This is an unusually mature, engineering-disciplined frontend — well above typical SaaS quality. The codebase shows:

A real design language (fc-surface-*, fc-text-*, fc-btn-*, agent tokens) with documented rules.
Strong test posture (Jest + jest-axe + Playwright across Chromium/WebKit/Firefox).
A11y primitives baked in (skip link, reduced-motion globally, focus rings, aria-live, focus trap hook, axe in CI).
A real CSP via middleware.ts and security headers in next.config.ts.
Boundary-aware hooks (useInvestigation ↔ useSimulation ↔ useResult) with explicit docstrings.
But it is not yet "frontend-locked". There is meaningful design-system drift, an overstretched orchestration layer (~1075-line useInvestigation.ts, ~1192-line useSimulation.ts), an implicit state machine spread across ~12 sessionStorage flags, and a visual identity collision between the documented thesis ("court-grade, not a hacker terminal") and execution (font-mono + uppercase + > prompts + scan lasers + segmented LED bars dominate the report screen).

Scores (1–10)
Dimension	Score	Notes
Frontend quality	7.5	High craft, but god-hooks and storage state machine drag it down.
UI/UX polish	7.0	Excellent micro-attention; identity drift toward "hacker terminal" undermines the stated "court-grade" thesis.
Maintainability	6.0	The two orchestration hooks are too large; storage keys form an undocumented protocol.
Accessibility	8.0	Best-in-class baseline; some specific gaps (export dropdown, tablist semantics, animated aria-live).
Production readiness	7.0	Hardened, but reconnection/handoff race surface is wide; needs lock plan execution before freeze.
Biggest risks
Two god-hooks carrying the entire investigation lifecycle (auth, upload, WS, SSE fallback, HITL, arbiter polling, reconnect, token refresh, BFCache, beforeunload, phase, persistence). Hard to test, hard to evolve, easy to regress.
Implicit state machine through ~12 sessionStorage flags (FC_SHOW_LOADING, FC_HANDOFF_FIRED, AUTO_START, FC_REPORT_READY, FC_ARBITER_TRANSITIONING, FC_RESUME_REQUESTED, FC_NO_RECONNECT, FC_OPEN_UPLOAD_ONCE, FC_PENDING_FILE_META, FC_LOADING_TEXT, FC_LOADING_DISPATCHED, IS_DEEP). Storage is being used as cross-component IPC.
Module-level mutable singleton (__pendingFileStore) holds a File, an auth promise, and an auth error outside React. Memory leaks and stale-reference hazards.
window event bus (fc:reset-home, fc:open-upload, fc:session-expired, fc_storage_update, fc_storage_quota_exceeded) replaces a context. Hides dependencies and makes flows hard to follow.
Design-system drift in production code paths: the docs forbid text-white/X, inline backdrop-blur-*, neon glows, scale-on-hover, animate-pulse outside status dots, and durations > 200ms — yet all of these appear in the most user-facing components (VerdictSection, ResultLayout, HomeClient, AgentProgressDisplay, error.tsx, session-expired, HowWorksSection).
Biggest UX weaknesses
Identity collision: thesis says "not a hacker terminal" but the report screen uses > Decrypting forensic ledger, scan lasers, segmented LED bars, uppercase mono everywhere, "Node: Alpha-7 Intake", "ENC: AES-256", "Node_Id", "0xFC_WS_LOST". This is the cosplay of forensic seriousness, not its language.
Two competing visual languages on the same page: glassmorphism + tactical HUD compete for attention in VerdictSection and ResultStateView.
Loading orchestration is over-engineered and visible: 800ms min, 1500ms min, 5000ms safety, 30000ms stall — multiple overlapping overlays (GlobalLoadingOverlay, LoadingOverlay, ForensicProgressOverlay, ArbiterDeliberationOverlay, body ::before bridge). Users perceive lag, not polish.
Artificial delays: setTimeout(600ms) before file selection navigates; 1500ms arbiter min display; reduce/remove unless you have user research backing them.
No empty/skeleton parity: EvidenceUploadClient empty state ("No Evidence Queued") is generic and disconnected from the brand.
Biggest architectural problems
The two orchestration hooks should be a single XState machine (or useReducer + clear states). The current code reinvents states across React state, refs, and storage.
No domain layer: API client, schemas, WebSocket message shapes, and React state are coupled.
No component-level documentation of design rules beyond FRONTEND_DESIGN_SYSTEM.md. ESLint guards mentioned in the doc are not actually present in eslint.config.mjs (verified — the file has none of the no-restricted-syntax rules the doc claims are "enforced mechanically"). This is the single biggest finding: the documented CI gate is a paper tiger.
Biggest polish opportunities (top 3)
Strip the hacker-terminal vocabulary from the result/verdict surface. Replace mono uppercase + > prompts with calm court-grade typography. Keep mono for hashes/IDs only.
Collapse the four loading overlays into one orchestrator with a single "phase" prop.
Enforce the design tokens in ESLint for real (the doc's "automated enforcement" rules are aspirational, not active).
2. Frontend Findings Catalog
Severity: Critical · High · Medium · Low

A. Design System Drift (Critical for "frontend lock")
ID	Sev	Area	Problem	Root cause	User impact	Tech impact	Fix	Complexity	Priority
DS-001	C	Tooling	FRONTEND_DESIGN_SYSTEM.md claims ESLint enforces banned classes (text-white/10..50, hover:scale-, backdrop-blur-*, micro text-[10/11/13px]). Real eslint.config.mjs has none of these no-restricted-syntax rules.	Doc-vs-code drift. Rules never landed.	None directly; indirect impact massive — design rules unenforced.	The promised CI gate is fictional. Tech debt grows silently.	Add the no-restricted-syntax rules listed in §2.1 of the design doc verbatim. Add a stylelint step for arbitrary spacings.	2h	P0
DS-002	H	Hero (HomeClient.tsx)	Decorative blurs bg-primary/10 blur-[140px] × 3 stacked on top of LandingBackground (which is already in layout.tsx). Violates "Rule of Two" backdrop-filter overlap and doubles the cost.	Background painted twice.	Slight motion judder on low-end devices; muddy gradients.	GPU compositing layers stacked.	Delete the <div className="absolute inset-0 ... -z-10"> block in HomeClient. Rely on LandingBackground.	1h	P1
DS-003	H	VerdictSection.tsx	(a) text-shadow: 0 0 20px rgba(...) — explicit "no neon glows" violation. (b) animate-[shimmer_3s_infinite] overlay on verdict icon — violates "no constant shimmering". (c) 60 sequential motion.div segmented bars (3 cells × 20). (d) font-mono uppercase tracking-widest for verdict label drifts to "hacker terminal" identity.	Visual maximalism in highest-traffic component.	First impression of the report is loud, not court-grade.	Reduces perceived trust; conflicts with brand thesis.	Remove text-shadow glow; drop shimmer; reduce segmented bar to a simple bar with tabular-nums % indicator; switch verdict label to text-hero-gradient font-heading (sans).	4h	P0
DS-004	H	ResultStateView.tsx	Uses bg-black/40, bg-black/50, backdrop-blur-md (inline), and a literal > prompt — all banned per design doc. Terminal aesthetic.	Pre-design-system relic.	"Terminal" identity collision.	Token drift.	Replace with fc-surface-quiet or fc-surface-solid; remove > prompt; remove inline backdrop-blur.	2h	P1
DS-005	H	ResultLayout.tsx	Tab nav uses bg-background/85 backdrop-blur-md (inline backdrop-blur — banned). Export dropdown uses raw border-white/[0.10] hover:bg-white/[0.05].	Bypassed fc-surface-elevated.	Slight inconsistency vs other nav.	Token drift.	Use fc-surface-elevated + standardized eyebrow/btn primitives.	2h	P1
DS-006	M	HowWorksSection.tsx	hover:scale-[1.01] and group-hover:scale-105 — both explicitly banned.	Drift.	Tactile feel inconsistent with rest of app.	Token drift.	Replace with hover:border-primary/40 only; remove scale.	30m	P1
DS-007	M	AgentProgressDisplay.tsx (Decision Gate)	bg-black/60 backdrop-blur-xl border border-primary/30 shadow-[0_0_40px_rgba(...)] — inline backdrop-blur and colored neon shadow — both banned. Plus animate-pulse on a w-5 h-5 icon (allowed only on w-1.5 status dots).	Custom surface instead of fc-surface-overlay/fc-surface-elevated.	Most critical CTA panel looks "off" from rest of UI.	Token drift on a high-impact element.	Replace whole panel chrome with fc-surface-elevated; remove neon shadow; remove animate-pulse on the Activity icon (or shrink to 6px dot).	2h	P0
DS-008	M	error.tsx (route error)	animate={{ opacity: [0.7, 1, 0.7] }} transition={{ duration: 3, repeat: Infinity }} — 3s breathing animation, banned (>200ms, constant motion).	Drift.	Distracting on error screens (worst moment for motion).	Token drift.	Replace with static state or single 160ms fade.	30m	P1
DS-009	M	SessionExpiredClient.tsx	Builds buttons with py-4 rounded-full bg-primary text-background instead of fc-btn-primary; uses fc-text-faint on text inside a glass panel (doc says minimum fc-text-muted inside glass — the "Glass Contrast Trap").	Drift.	Reduced contrast on glass; non-uniform button feel.	Direct contrast risk.	Use fc-btn-primary / fc-btn-secondary; switch fc-text-faint → fc-text-muted inside the panel.	30m	P1
DS-010	M	dialog.tsx (Radix Dialog)	Both DialogOverlay and DialogContent use z-50 rather than the documented --z-index-overlay: 60 (z-overlay) / --z-index-modal: 40 (z-modal). Tab nav uses z-modal (40) and DEV banner uses z-[60]. Z-index scale is inconsistent in practice.	Scale not threaded through Tailwind config.	Tooltips inside modals (per docs they should be fc-surface-solid) — works, but z-stacking is brittle.	Layout regressions on subsequent additions.	Add z-modal/z-overlay/z-tooltip/z-nav Tailwind classes mapping to the CSS variables; replace all z-50/z-[60]/z-[999] with tokens.	2h	P1
DS-011	L	EvidenceUploadClient.tsx error UI	<p className="text-danger ..."> — token text-danger not in design doc (fc-text-danger is).	Minor drift.	Cosmetic.	None.	Use fc-text-danger.	10m	P2
DS-012	L	globals.css	Duplicate keyframes (fc-shimmer and shimmer), legacy .custom-scrollbar alias.	Migration leftovers.	None.	Bundle bloat.	Remove unused.	30m	P2
DS-013	L	error.tsx vs global-error.tsx	Two error UIs with different micro-typography (e.g. "Forensic Council Encountered an Error" vs "System Interrupted" vs "Pipeline Interrupted").	Three teams of one.	Inconsistent brand voice.	Tone drift.	Adopt one copy spec (docs/COPY.md) and reuse a shared error frame.	2h	P2
B. Architecture / State
ID	Sev	Area	Problem	Root cause	User impact	Tech impact	Fix	Complexity	Priority
ARCH-001	C	useInvestigation.ts (1075 LOC)	Single hook owns auth, upload, thumbnail, session, WS, BFCache, beforeunload, popstate, arbiter wait, deep resume, navigation, overlay lifecycle, sounds, toast UX, and recovery. ~30 effects/refs interleaved.	Organic growth.	Bugs in any branch affect the whole flow.	Hard to test; impossible to reason about in isolation.	Decompose to: useAuthSession, useEvidenceHandoff, useInvestigationLifecycle (useReducer or XState), useArbiterTransition, useNavGuards.	5–8 days	P0
ARCH-002	C	useSimulation.ts (1192 LOC)	One callback connectWebSocket is 700+ lines with closures over a message queue, reconnect timer, dual fallback to SSE, and inline applyUpdate.	Same as above.	WS race conditions on phase changes.	Easy to mis-edit.	Split: socket.ts (transport), applyUpdate.ts (pure reducer), useSimulation.ts (orchestration). Move applyUpdate into a pure reducer over a typed SimulationState (helps tests too).	3–5 days	P0
ARCH-003	H	Storage-as-IPC	~12 sessionStorage flags + custom fc_storage_update events implement an undocumented state protocol across pages.	Cross-route handoff.	Race bugs (grace period logic in GlobalLoadingOverlay is evidence).	Hard to onboard; fragile.	Replace with a <InvestigationProvider> context that owns a typed state machine; storage persistence becomes a single subscriber. Document keys (/docs/STORAGE.md).	3–4 days	P0
ARCH-004	H	__pendingFileStore module singleton	Mutable File/promise/error stored on a module object. Survives across mounts. Risk of stale references and double-clear races (e.g. freshMountDoneRef guard).	Need to ferry a File from HomeClient to EvidenceUploadClient across router.push.	None visible.	Memory leak surface; lost-file UX on hard refresh already detected ("Please reselect").	Use IndexedDB-only persistence (savePendingEvidenceFile already exists). Drop the module singleton.	1 day	P1
ARCH-005	H	Window event bus	fc:reset-home, fc:open-upload, fc:session-expired, fc_storage_update, fc_storage_quota_exceeded.	Implicit cross-tree messaging.	None directly.	Side-effects invisible to React DevTools; hard to TypeScript.	Replace with a context dispatcher (typed events).	1–2 days	P1
ARCH-006	M	connectWebSocket deps []	Hard-coded empty deps with refs is intentional, but the explanatory comment is the only safeguard.	Performance vs correctness tradeoff.	Subtle stale-closure risk if refs change shape.	Hard to refactor safely.	Move applyUpdate to a pure reducer; the hook then only depends on the dispatch ref.	covered by ARCH-002	P1
ARCH-007	M	Dual phase sources of truth	activePhaseRef, phase state, storage[RESULT_PHASE], IS_DEEP, expectingPipelineCompleteRef, and report's is_deep_analysis.	Migration leftovers.	Phase desync possible on reconnect.	High cognitive load.	Single derived selector from one state machine.	covered by ARCH-003	P1
ARCH-008	M	useResult.ts mounted/hydration pattern	All storage state hydrated in a useEffect after setMounted(true). First paint shows arbiter loading even when report is ready. Then a second pass flips state.	Avoids SSR hydration mismatch.	Brief flash of progress overlay on result page.	Reasonable but suboptimal.	Use cookies() in a server component to ship mounted defaults; or read FC_REPORT_READY from cookie.	1 day	P2
ARCH-009	L	Magic timing numbers	EVIDENCE_MAX_DISPLAY_MS=5000, ARBITER_MIN_DISPLAY_MS=1500, MIN_DISPLAY_MS=800, SAFETY_TIMEOUT_MS=5000, STALL_MS=30000, setTimeout(600) in upload.	Local constants per file.	None.	Hard to tune.	Centralize in lib/timings.ts.	1h	P2
C. Components
ID	Sev	Area	Problem	Fix
CMP-001	H	AgentProgressDisplay.tsx (619 LOC)	Mixes two panels (Active / Skipped), the agent card grid, two decision gates, and lots of presentational logic.	Extract <DecisionGate> and <AgentGrid> to dedicated files; lift logic into useAgentStatus selector.
CMP-002	H	ResultLayout.tsx (700 LOC)	Holds ExportDropdown, buildKeyFindings (50+ LOC of business rules), cleanToolSummary, isLowValueFinding, severityRank, plus the tab shell, plus all section composition.	Move buildKeyFindings & helpers to lib/keyFindings.ts (pure, testable). Move ExportDropdown to its own file.
CMP-003	M	HITLCheckpointModal.tsx	Custom keyboard radiogroup implemented inline; logic is correct but not encapsulated.	Extract <RadioGrid> component (reusable for future protocol decisions).
CMP-004	M	RootErrorBoundary resets via window.location.href = "/" and window.location.reload()	Loses React state for users with active forms (e.g. HITL note in progress).	Try reset() first; only fall back to hard reload after N attempts.
CMP-005	M	GlobalNavbar.tsx	Dev-mode banner adds 28px and shifts nav top-7; assumed in DOM mockups elsewhere? Likely yes given pt-16 on <main>, but the 28px shift is not reflected on subsequent fixed elements (tab nav at top-16).	If directApiUrl, shift all top-16 fixed elements by 28px as well; or convert to a CSS var --nav-offset.
CMP-006	L	GlobalFooter	"Forensic Council is an academic project and can occasionally make mistakes." — fine on landing, awkward on result pages where users may treat output as definitive.	Hide on /result/* or rephrase as confidence disclaimer.
CMP-007	L	Dialog z-index	DialogContent max-w-lg overrides max-w-xl set on the HITL modal via classNames merge; verify cn() precedence works (it does in tailwind-merge — confirmed).	None.
D. Performance (statically inferred)
ID	Sev	Problem	Fix
PERF-001	M	VerdictSection.MetricCell creates 60 motion.divs with stagger; AnimatePresence + initial false logic correct but cost on first paint is meaningful on low-end CPUs.	Replace with a single <div> width-based bar.
PERF-002	M	3 large blur meshes in HomeClient (140–160px blur-[] ×3) stacked on top of LandingBackground (2 more). At ~5 GPU compositing layers — paint cost on mobile.	Reduce to 1 from LandingBackground only.
PERF-003	L	body[data-fc-loading="1"]::before uses backdrop-filter: blur(32px) full-screen. On hand-off this overlaps with <GlobalLoadingOverlay> which itself blurs. Two fullscreen blurs = double cost.	One owner only — let React component own it.
PERF-004	L	framer-motion imported broadly (good — already in optimizePackageImports). Verify motion components on critical path can be replaced with CSS transitions per design doc.	Audit and prefer fc-transition CSS for hover/exit states.
PERF-005	L	useResult re-creates activeAgentIds and keyFindings reasonably memoized, but ResultLayout defines variants inline per render (creates new objects per render).	Hoist variants out of the component, or use useMemo.
E. Styling / CSS
ID	Sev	Problem	Fix
CSS-001	M	Skipped/Active panels use border-white/4 (Tailwind v4 supports arbitrary alphas but 4% is borderline invisible — likely intended 0.04).	Confirm with stylelint; use border-border-subtle token.
CSS-002	M	Frequent text-white/55, text-white/60, text-white/70, text-white/68, text-white/85 etc. across many files. Doc bans these in favor of fc-text-*.	Codemod replace.
CSS-003	L	globals.css mixes the @theme block (Tailwind v4) with @layer base/@layer utilities. Some @layer utilities rules (e.g. scrollbar, .fc-text-*) would be more readable as @theme extensions or a tokens.css partial.	Split into tokens.css and components.css imports.
CSS-004	L	Inline style={{ background: "linear-gradient..." }} repeated (navbar accent gradient, glow gradients, etc.).	Token-ize.
F. Error handling / Resilience
ID	Sev	Problem	Fix
ERR-001	M	try/catch { /* ignore */ } and .catch(() => {}) appear in many places. Some are correct, some swallow real errors (e.g. inside connectWebSocket SSE fallback).	Tag swallowed errors with dbg.warn; surface to Sentry-style telemetry in prod.
ERR-002	M	Token refresh in useSimulation calls fetch(${API_BASE}/api/v1/auth/refresh) directly bypassing the client.ts retry/error pipeline.	Use the API client.
ERR-003	L	ExportDropdown warns on failure but offers no "open in new tab to debug" affordance.	Inline a small fallback link.
ERR-004	L	RootErrorBoundary clears two specific keys (fc_show_loading, fc_handoff_fired) in componentDidCatch but the storage system uses many more.	Either clear with storage.clearAllForensicKeys or none — pick one.
G. Code-quality / Type-safety
ID	Sev	Problem	Fix
TYPE-001	M	applyUpdate uses update.data as Record<string, unknown> then casts every field. Zod schemas exist (lib/schemas.ts) — not used here.	Parse incoming WS messages via Zod once; downstream is fully typed.
TYPE-002	L	(m as unknown as Record<string, unknown>).agent_verdict as string in ResultLayout.buildKeyFindings.	Add agent_verdict to the typed PerAgentMetrics DTO.
TYPE-003	L	console.log in dev WS handler is fine but verbose.	Wrap in dbg.log (already used elsewhere).
3. UI/UX Premium Polish Audit
What stops the app from feeling premium:

Identity collision (the #1 polish issue). The thesis is "court-grade, calm under pressure, not a hacker terminal." The reality on the result page is the opposite: monospace uppercase everything (OFFICIAL COUNCIL VERDICT · INITIAL, > Decrypting forensic ledger..., MANIPULATION RISK, TOOL ERROR RATE, AGENT SPREAD), a scan-line laser on the empty Diagnostic Logs state, segmented LED bars, Node: Alpha-7 Intake, ENC: AES-256. Tactical HUDs and frosted-glass court UIs are very different aesthetics; mixing them reads as "AI-generated landing page chic". Pick one. The doc already picked. Execute on it.

Verbose chrome around the verdict. The verdict is the product. It should be the most calm element on screen. Right now it has: animated icon shimmer, ambient watermark (opacity 0.03 of 384px icon), neon text-shadow on the % digit, a colored pulsing dot, "Signed deep-analysis report · 5 active agents · 92% aggregate confidence" small print, plus a 60-segment LED bar grid underneath. Reduce to: verdict label (large heading sans), one sentence under it, one row of three plain bars or simple text statistics.

Loading lattice. GlobalLoadingOverlay, LoadingOverlay, ForensicProgressOverlay, ArbiterDeliberationOverlay, data-fc-loading::before. Each owns a piece of the perceived load. Collapse to one <RouteTransitionOverlay phase="upload|connecting|analyzing|arbiter|loading-report">.

Empty states feel like 404s. EvidenceUploadClient empty state ("No Evidence Queued · Return to the home page to upload evidence") is generic. Premium tools restate the value proposition or auto-recover (e.g., re-open the upload modal here directly instead of routing back to /).

Two error UIs with different copy (error.tsx, global-error.tsx, plus RootErrorBoundary, plus ResultStateView.error, plus ForensicErrorModal). Five surfaces, four voices.

Artificial delays. setTimeout(600) between file select and dispatch reads as polish but feels laggy; the 1500ms arbiter min-display similarly. Premium products time their delays to user expectation, not to themselves.

Buttons drift. fc-btn-primary is great. But the session-expired page, the AgentProgressDisplay decision gate, and the ExportDropdown trigger all reinvent buttons. The verdict is a uniform button system that bleeds into every CTA. Today it has six button looks.

Spacing rhythm. Generally good (space-y-4, gap-4 md:gap-5 xl:gap-6). But the report page mixes space-y-0, space-y-4, space-y-6, pb-24 pt-20 sm:pt-12 and tab nav h-12 — small spacing decisions feel improvised. Pick a single vertical rhythm constant (8px or 12px).

Microcopy. "Session De-synchronized", "Ledger Desync", "Investigative payload session has either concluded, expired, or lacked appropriate validation signatures." Too theatrical. Real forensic UIs sound terse and human: "Your session expired. Please start a new analysis."

The export dropdown mixes PDF/DOCX/JSON without telling the user the difference; PDF can fall back to HTML silently. A premium pattern shows "PDF — recommended for printing", "JSON — raw data", and an info icon with a tooltip.

Prioritized premium polish roadmap
(1d) Strip mono uppercase from verdict, key findings, tab labels. Keep mono only for: hashes, IDs, file sizes, durations. (Already canonical per docs.)
(1d) Replace LED segmented bars with simple bars; remove neon glow on verdict %.
(1d) Collapse loading overlays into one.
(½d) Unify button system; codemod replace ad-hoc buttons.
(½d) Rewrite error / session-expired copy to plain English.
(1d) Replace empty EvidenceUploadClient state with an in-place "Upload new evidence" CTA that reopens the upload modal.
(½d) Make ExportDropdown self-explanatory with subtitles.
4. Accessibility Audit
Baseline is strong: skip link, focus rings (global :focus-visible), reduced-motion media query at the top of globals.css, aria-live regions, role="status" SR announcements, focus trap hook, axe in Jest, axe in Playwright, ESLint a11y plugin.

Findings
ID	Sev	Finding	Why it matters	Fix
A11Y-001	C	ExportDropdown is a custom listbox with aria-expanded on the trigger but no role="menu" / menuitems on the items, no aria-haspopup, no arrow-key navigation, and clicking outside closes but Escape does not.	Screen-reader users cannot perceive that PDF/DOCX/JSON are menu options. Keyboard users cannot escape.	Add role="menu", role="menuitem", aria-haspopup="menu", escape-to-close, and arrow-key cycling. (Consider Radix DropdownMenu.)
A11Y-002	C	aria-live="polite" regions update with animated content (e.g. pipelineMessage changes inside AgentProgressDisplay while motion overlays flash). Some screen readers will read every motion frame's text.	Verbose, noisy announcements.	Throttle SR-text updates: maintain a srMessage state separate from the visual pipelineMessage.
A11Y-003	H	HITLCheckpointModal radiogroup arrow-key handler calls setSelectedDecision even if focus is not on the radiogroup — the tabIndex={-1} on the wrapper attempts to handle this, but the focus management still depends on internal querySelector indexing.	Edge cases with focus restoration.	Use Radix RadioGroup.
A11Y-004	H	ResultLayout tab nav: tablist semantics are correct, but role="tabpanel" for history is rendered only when activeTab === "history". Per ARIA, both tabpanels should exist; the inactive one should be hidden. The analysis panel does use hidden. History panel does not exist when hidden — assistive tech cannot move backwards.	Tab navigation predictability.	Always render both <HistoryPanel> and analysis section; toggle visibility with hidden.
A11Y-005	H	EvidenceUploadClient "No Evidence Queued" route is reachable only after orphan navigation. No <h1> first focus / SR announcement.	SR users land on an unannounced page.	Add an aria-live="polite" announcement on mount, or use useEffect to focus <h1>.
A11Y-006	M	useFocusTrap excludes [aria-hidden="true"] but not elements inside [aria-hidden] ancestors. Off-screen siblings of an open modal can still get focus.	Focus trap may leak.	Walk ancestors when filtering focusables.
A11Y-007	M	data-testid="upload-dropzone" div is role="button" but contains an <input type="file"> that is also focusable in some browsers (tabIndex={-1} mitigates, but accept attribute may differ). When the user presses Enter on the dropzone, the input is clicked — fine — but Space also triggers it; native buttons handle Space natively, custom buttons should mirror.	Already handled (`if (e.key === "Enter"	
A11Y-008	M	progressbar inside UploadModal has aria-valuetext but no aria-valuenow/min/max and no determinate progress (it's animated).	Indeterminate progress should be announced once.	Use aria-busy="true" or live region "Encrypting…" message instead.
A11Y-009	M	Color-only conveyance: red/amber/emerald dots in KeyFindings, segmented LED bars in VerdictSection.	Contrast acceptable on background but color-blind users rely on labels alone.	Already labels exist (Anomalies Detected, Review Recommended). Confirm icons + text remain when color removed. Mostly OK.
A11Y-010	M	animate-pulse on the navbar session indicator w-1.5 h-1.5 rounded-full — allowed per design doc, but with prefers-reduced-motion: reduce the global rule clamps animation to 0.01ms. Visually OK.	None.	
A11Y-011	L	Text contrast: fc-text-muted at 62% on fc-surface interior — design doc says 68% minimum inside glass; current value 0.62 ≠ doc-claimed 0.68. Tiny but real.	Slight WCAG risk on glass interiors.	Bump --fc-text-muted to 0.68 (matches docs).
A11Y-012	L	<a href="#main-content"> skip link works, but <main> has tabIndex={-1} and style={{ outline: "none" }} — focus is set but invisible.	Skip-link users lose focus visibility.	Remove outline: none from <main>, rely on :focus-visible no-show for mouse users.
A11Y-013	L	useReducedMotion is called many times across components — fine; just ensure all entrance animations use the initial={prefersReducedMotion ? false : ...} guard. Some places do, some don't (e.g. VerdictSection MetricCell respects it; ResultStateView has an animate-pulse mask not gated).	Minor reduced-motion drift.	Audit.
A11Y-014	L	DEV banner role="alert" will announce on every page in dev mode.	Annoying.	role="status" instead.
Categorization:

Critical: A11Y-001, A11Y-002
Major: A11Y-003, A11Y-004, A11Y-005
Moderate: A11Y-006 – A11Y-010
Minor: A11Y-011 – A11Y-014
5. Refactor & Stabilization Plan
Phase 1 — Critical Stabilization (3–5 days)
DS-001: Land the documented ESLint no-restricted-syntax rules. Add a stylelint config that bans arbitrary text-[10|11|13|14|15px] and arbitrary text-white/[<55]. (1d)
DS-003 + DS-007: Repair the verdict/decision-gate aesthetic violations. (1d)
A11Y-001 + A11Y-002 + A11Y-004: Real menu semantics for ExportDropdown; throttle live SR; always-render tabpanels. (1d)
TYPE-001: Zod-parse WS messages once at the boundary. (1d)
ERR-001/002: Use the API client for token refresh; tag swallowed errors. (½d)
Risk: Low. Impact: High. Complexity: Low–Medium.

Phase 2 — Architecture Cleanup (8–12 days)
ARCH-001/002/003/007: Decompose useInvestigation and useSimulation. Introduce a single typed state machine (xstate or useReducer + pure reducer). Move storage flags into a single subscriber. (1–2 weeks)
ARCH-004/005: Drop __pendingFileStore singleton (IndexedDB only); drop window event bus in favor of context. (2d)
CMP-001/002: Split AgentProgressDisplay and ResultLayout. (2d)
Risk: Medium (touches the entire orchestration). Mitigation: Build the new state machine alongside, switch behind a feature flag, retire old hooks. Impact: Very high (every future bug pays this back).

Phase 3 — UI Consistency Normalization (2–3 days)
DS-002/004/005/006/008/009/010: Token-ize z-index, replace ad-hoc surfaces and buttons, normalize text-white/X → fc-text-*. (2d)
CSS-001/002/003/004. (1d)
Phase 4 — Accessibility Hardening (2 days)
A11Y-003/005/006/008/011: Remaining items. (1d)
A11Y-007/009/012/013/014. (½d)
Add axe-playwright runs to CI for the full critical-paths set (already a script exists). (½d)
Phase 5 — Performance Optimization (1–2 days)
PERF-001/002/003: Reduce blur layers; simplify VerdictSection bars; pick one fullscreen loading owner. (1d)
PERF-005: Hoist Framer variants out of render. (½d)
Phase 6 — Premium Polish Pass (3–4 days)
Polish roadmap §3. Aesthetic alignment with thesis. Microcopy rewrite. Empty/error state unification. (3–4d)
Phase 7 — Frontend Freeze Validation (1–2 days)
Tag a frontend-freeze candidate.
Run full Playwright matrix (already configured for chromium/webkit/firefox).
Run jest-axe across critical pages.
Visual regression sweep at: 320, 375, 768, 1024, 1440, 1920.
DOM snapshot diff vs baseline.
Total: ~18–28 engineering days for a clean freeze. ~5 days minimum for a "good enough" freeze (Phases 1, 3, 4, 7 only).

6. "Frontend Lock" Checklist
Use this as the gate before declaring frontend frozen.

Design system

 ESLint no-restricted-syntax rules from FRONTEND_DESIGN_SYSTEM.md §2.1 are present and pass with --max-warnings 0.
 No text-white/X opacities anywhere in src/.
 No inline backdrop-blur-* outside fc-surface-* definitions.
 No hover:scale-*, no scale springs.
 All animate-pulse confined to ≤6px status dots.
 No motion durations > 200ms in interactive components (excluding reveal sequences explicitly justified in code comments).
 All shadows are rgba(0,0,0,X); no colored neon glows.
 All z-indices come from CSS variables, no z-[999] / z-[60].
Consistency

 Single button system in use everywhere (fc-btn-primary|secondary|ghost|danger).
 Single surface system (fc-surface-*); zero ad-hoc glass.
 Single text scale (fc-text-*).
 One copy spec at docs/COPY.md powers error / empty / loading messages.
Architecture

 useInvestigation < 250 LOC; useSimulation < 300 LOC.
 No module-level mutable singletons hold React-relevant state.
 No window.addEventListener for cross-tree messages; use context.
 All storage keys documented at docs/STORAGE.md.
Accessibility

 Jest axe passes for every page route at zero violations.
 Playwright axe passes Chromium + WebKit + Firefox.
 All custom widgets (dropdowns, radio grids, tabs, dialogs) use Radix or ARIA-correct equivalents.
 Reduced-motion path verified manually for every animated component.
Resilience

 No silent catch {}; every swallow is tagged with dbg.warn or a TODO.
 Error boundaries cover route, root, and dynamic-import segments (already present — verify).
 Offline reconnect path tested by killing the WS for 10/30/60s.
Performance

 LCP < 2.5s on a throttled Slow 4G + mid-range mobile (verify with Lighthouse).
 No more than two stacked backdrop-filter layers on any route.
 Bundle size delta vs current baseline ≤ +5%.
Testing

 Storybook (or Playwright component test suite) covers all surface variants × state matrix.
 Visual regression suite locked at a baseline commit.
7. Hidden Risks & Future Debt
State-machine implosion. As soon as a third phase is added (e.g. "expert review queue", "appeal"), useInvestigation + useSimulation will not absorb it. Refactor (Phase 2) before any new pipeline phase.
Storage protocol drift. A new developer will add a 13th flag for the next handoff race. Every additional flag multiplies race surface area combinatorially. Without a documented machine, the system will fail in production under bfcache + slow networks.
Identity drift accelerates. Each new feature that touches the report screen will copy the existing terminal motif (it's the easy path). Without DS-001 (lint enforcement) the design system is a doc, not a guardrail.
PDF/DOCX export fallback silently downgrades. Today this is acceptable; users see a toast. Tomorrow when stakeholders run a courtroom demo and silently get JSON, trust evaporates. Add server-side health check; if unavailable, disable PDF in the dropdown rather than fallback.
framer-motion surface area. It's installed and used liberally. Some interactions are CSS-cheap. As CPU budget shrinks (mobile/low-end), framer everywhere will hurt. Plan a migration to pure CSS for hover/active.
Two error / loading models will diverge. ForensicErrorModal, ForensicProgressOverlay, GlobalLoadingOverlay, LoadingOverlay, ArbiterDeliberationOverlay, ResultStateView, RootErrorBoundary, error.tsx, global-error.tsx, not-found.tsx. Ten surfaces for "something went wrong" or "wait". Without consolidation, copy/style will drift every release.
Token refresh path bypasses the API client. As soon as backend changes CSRF/auth semantics, this codepath breaks silently in production. Centralize.
WS message types are not source-of-truth typed. Backend can change a field name and the UI will silently degrade (filtered out by the as casts).
Where I cannot confirm without runtime:

Whether prefers-reduced-motion: reduce is honored by every motion path (need DOM at runtime).
Whether the focus order on <main id="main-content" tabIndex={-1} style={{outline:"none"}}> is correct in all browsers.
Whether the WebSocket close-code reconnect logic actually backs off as designed under packet loss.
Whether the data-fc-loading body backstop double-blurs in practice (depends on actual stacking with the React overlays).
Bundle size after the standalone build — optimizePackageImports is configured but unmeasured.
Top 20 Highest-ROI Frontend Improvements
Ranked by (user impact × engineering impact) / effort:

#	Improvement	Why
1	Land the documented ESLint design-system rules (DS-001).	2-hour fix that converts the design doc from aspiration to enforcement. Single highest leverage move in this audit.
2	Strip terminal-HUD motifs from VerdictSection (DS-003).	The verdict is the product. It currently fights its own brand.
3	Replace ExportDropdown with Radix DropdownMenu (A11Y-001).	Critical screen-reader regression; fixes keyboard nav too.
4	Throttle aria-live updates (A11Y-002).	Stops SR users from drowning during analysis.
5	Consolidate loading surfaces into one <RouteTransitionOverlay>.	Eliminates the entire "loading loop" bug class noted in comments.
6	Zod-parse all WS message types at the boundary (TYPE-001).	Eliminates a whole bug class going forward.
7	Decompose useInvestigation and useSimulation (ARCH-001/002).	Highest engineering ROI; unlocks confident editing.
8	Replace __pendingFileStore singleton + window-event bus (ARCH-004/005).	Removes the entire "where does this state live?" class.
9	Codemod all text-white/X → fc-text-* (CSS-002).	One-time fix that locks in design system.
10	Bump --fc-text-muted to 0.68 to match the doc (A11Y-011).	Doc/code parity. Tiny edit. Real contrast bump on glass.
11	Centralize timing constants (lib/timings.ts) (ARCH-009).	Tunability without grep.
12	Remove duplicate decorative background in HomeClient (DS-002, PERF-002).	One commit, smoother first paint.
13	Unify the button system (DS-005, DS-007, DS-009).	Visual consistency across CTAs.
14	Rewrite error / session-expired copy in plain English.	Premium products sound human.
15	Disable PDF export when server can't generate (instead of silent fallback).	Trust safety.
16	Always render both tab panels with hidden (A11Y-004).	ARIA correctness.
17	Remove setTimeout(600) and ARBITER_MIN_DISPLAY_MS=1500 artificial delays unless user research backs them.	Perceived speed.
18	Reduce VerdictSection segmented bars to plain bars (PERF-001).	Lighter paint cost, cleaner identity.
19	Add a docs/STORAGE.md documenting every storage key + lifecycle.	Lock-in maintainability.
20	Add a docs/COPY.md and reuse a single error frame component.	Voice consistency across ten error/loading surfaces.
Closing note
This is a strong codebase being undermined by two forces: (a) the design system exists on paper but is not enforced in the linter; (b) two giant orchestration hooks plus a sessionStorage-as-IPC protocol are doing too much work. Both are addressable in a single 3–4 week effort using the phased plan above. Once Phase 1 (Critical Stabilization) ships, you can credibly market "court-grade" — today, the visuals say "tactical HUD" louder than the documentation does. Lock the visuals, simplify the orchestration, then declare freeze.
Forensic Council — End-to-End Functional Audit
STEP 1. Landing page loads
Path: apps/web/src/app/page.tsx + apps/web/src/app/layout.tsx + apps/web/src/components/ui/LandingBackground.tsx

✅ Working — no inline <footer> duplication, LandingBackground z-index correct, fonts wired to --font-heading-family.

⚠️ Bug 1.1 — Hydration jitter on hero. page.tsx is a client component but renders Framer Motion animate on mount before fonts swap; users see a flash. Low priority, ignore unless you observe it.

Verification checklist:

 / loads with no console error
 Hero gradient/blue palette visible
 CTA data-testid="cta-begin-analysis" is visible
STEP 2. Landing CTA → Upload modal
File: apps/web/src/components/ui/HeroAuthActions.tsx

🔴 Bug 2.1 — Modal stays open after auth/health failure. In handleStartAnalysis (lines 62–97), setShowUpload(false) is reached only on the success path (line 90). On health.ok === false or thrown error, the function returns early and the UploadSuccessModal remains mounted underneath the ForensicErrorModal. Two stacked modals, broken UX.

Fix — apps/web/src/components/ui/HeroAuthActions.tsx (replace the relevant branches):

const handleStartAnalysis = useCallback(async () => {
  if (!selectedFile) return;
  setIsAuthenticating(true);
  setAuthError(null);

  try {
    const health = await checkBackendHealth();
    if (!health.ok) {
      setShowUpload(false);                         // <-- ADD
      setSelectedFile(null);                        // <-- ADD
      setIsAuthenticating(false);
      setAuthError(health.warmingUp ? "Protocol Warming Up... (60s)" : health.message);
      return;
    }
    await autoLoginAsInvestigator();
    storage.setItem("forensic_auth_ok", "1");
  } catch (err) {
    setShowUpload(false);                           // <-- ADD
    setSelectedFile(null);                          // <-- ADD
    setIsAuthenticating(false);
    if (err instanceof ProtocolWarmingError) {
      setAuthError("Protocol Warming Up... (Retrying)");
    } else {
      setAuthError(err instanceof Error ? err.message : "Authentication failed");
    }
    return;
  }

  setShowUpload(false);
  __pendingFileStore.file = selectedFile;
  sessionOnlyStorage.setItem("forensic_auto_start", "true");
  sessionOnlyStorage.setItem("fc_show_loading", "true");
  setIsNavigating(true);
  router.push("/evidence", { scroll: true });
  setIsAuthenticating(false);
}, [router, selectedFile]);
🔴 Bug 2.2 — isNavigating never resets if user clicks the back button. Once setIsNavigating(true) fires (line 94), it stays true forever; if the user presses Back to land again, the spinner overlay reappears and never closes.

Fix — same file, after the existing useEffects, add:

useEffect(() => {
  // When the landing page re-mounts (e.g. via Back from /evidence), reset transient flags.
  setIsNavigating(false);
  setIsAuthenticating(false);
}, []);
⚠️ Bug 2.3 — UploadModal close on overlay click drops file. UploadModal.tsx:56 has onClick={onClose} on the backdrop. Drag-and-drop sometimes registers a stray click on the backdrop (post-drop) which closes the modal AFTER the file is selected, racing the onFileSelected handler.

Fix — apps/web/src/components/evidence/UploadModal.tsx:50 (root motion.div):

onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
// remove the existing onClick={onClose}
Verification checklist:

 Click CTA → UploadModal opens
 Stop the API → click CTA → file → Begin → modal closes, error modal shows
 Press Back from /evidence → CTA clickable again
STEP 3. File upload success modal
File: apps/web/src/components/evidence/UploadSuccessModal.tsx + HeroAuthActions.tsx

✅ Modal swap (Upload → Success) works via key="success-modal" with mode="wait".

⚠️ Bug 3.1 — No close X. The user must use Reselect or Begin Analysis. Add an explicit close path so ESC/X works (already filed in earlier audit P2-F9; still missing in this commit).

Fix — apps/web/src/components/evidence/UploadSuccessModal.tsx (add to the modal header):

import { X } from "lucide-react";
// inside the modal panel, top-right:
<button
  onClick={() => { onNewUpload(); }}
  aria-label="Close"
  data-testid="success-modal-close"
  className="absolute top-6 right-6 text-white/40 hover:text-primary"
>
  <X className="w-5 h-5" />
</button>
Also add ESC handler in the same file:

useEffect(() => {
  const onEsc = (e: KeyboardEvent) => { if (e.key === "Escape") onNewUpload(); };
  window.addEventListener("keydown", onEsc);
  return () => window.removeEventListener("keydown", onEsc);
}, [onNewUpload]);
Verification checklist:

 After file select, success modal shows with file name + size
 X / ESC closes back to UploadModal
 “Begin Analysis” triggers spinner then routes
STEP 4. Analysis progress overlay
File: apps/web/src/components/evidence/AnalysisProgressOverlay.tsx (rendered from both HeroAuthActions and EvidencePage)

🔴 Bug 4.1 — Overlay can hang forever if backend never sends agent updates. In useInvestigation.ts:542-551, the overlay is dismissed only when agentUpdates or completedAgents becomes non-empty. If WebSocket connects but no agent_update ever arrives (e.g. all agents skipped + race condition), overlay never lifts.

Fix — apps/web/src/hooks/useInvestigation.ts add a timeout safety:

useEffect(() => {
  if (!showLoadingOverlay || !analysisStreamReady) return;
  const safety = setTimeout(() => {
    setShowLoadingOverlay(false);
    sessionOnlyStorage.removeItem("fc_show_loading");
  }, 20_000); // give backend 20s after WS-ready before forcing dismissal
  return () => clearTimeout(safety);
}, [showLoadingOverlay, analysisStreamReady]);
🔴 Bug 4.2 — Unhandled await authReadyRef.current rejection leaves investigationInFlightRef = true and isUploading = true forever. useInvestigation.ts:238 — if authReadyRef.current rejects, the rejection bubbles past the try/catch around startInvestigation and the function never sees it.

Fix — apps/web/src/hooks/useInvestigation.ts:238 wrap the await:

try {
  await authReadyRef.current;
} catch (authErr) {
  setIsUploading(false);
  setShowLoadingOverlay(false);
  resetSimulation();
  investigationInFlightRef.current = false;
  toast.destructive({ title: "Authentication failed", description: authErr instanceof Error ? authErr.message : "Could not establish session." });
  return;
}
Verification checklist:

 Overlay shows immediately after CTA → routing
 Overlay dismisses within 1 s of first agent update
 Force backend offline mid-flow → overlay dismisses within 20 s with a toast
STEP 5. Evidence page loads all 5 agents
File: apps/web/src/components/evidence/AgentProgressDisplay.tsx + AgentStatusCard.tsx

✅ All 5 agent cards render via allValidAgents = AGENTS_DATA.filter((agent) => agent.id !== "Arbiter").

🔴 Bug 5.1 — “File-type validation” UI step is missing. Per your spec: each card should show a Validating → Skip / Run transition. Today, getAgentStatus() (line 172) immediately returns "unsupported" from MIME, with no validating intermediate state. The status type already includes "validating" and "checking" but they’re never used.

Fix — apps/web/src/components/evidence/AgentProgressDisplay.tsx add a brief validating window so users see the file-type check happen:

const [validatingAgents, setValidatingAgents] = useState<Set<string>>(
  () => new Set(allValidAgents.map(a => a.id))
);

useEffect(() => {
  // Hold every card in "validating" for 1.2 s after MIME is known, then release.
  if (!mimeType) return;
  const t = setTimeout(() => setValidatingAgents(new Set()), 1200);
  return () => clearTimeout(t);
}, [mimeType]);

const getAgentStatus = (agentId: string): AgentStatus => {
  if (validatingAgents.has(agentId)) return "validating";
  const isSupported = isAgentSupportedForMime(agentId, mimeType);
  if (!isSupported) return "unsupported";
  // ...rest unchanged
};
Then in AgentStatusCard.tsx render a “Validating file type…” pill when status === "validating" so the user sees the check.

🔴 Bug 5.2 — Skipped-card 10 s timer fires from grid mount, not from card reveal. AgentProgressDisplay.tsx:138-154 starts the timer immediately on mimeType change, before the user has even seen the card. With staggerChildren of 0.6 s × 5 cards = up to 3 s of stagger, the user sees the bypassed card for only ~7 s instead of the intended 10 s.

Fix — same file: key the 10 s timer off card mount so each card gets its full 10 s on screen:

// REMOVE the current useEffect at line 138-154
// REPLACE with: pass an onSkipExpire prop into AgentStatusCard,
// have AgentStatusCard call it after 10s of being mounted with status="unsupported".
And in AgentStatusCard.tsx:

useEffect(() => {
  if (status !== "unsupported") return;
  const t = setTimeout(() => onSkipExpire?.(agentId), 10_000);
  return () => clearTimeout(t);
}, [status, agentId, onSkipExpire]);
🟠 Bug 5.3 — Layout collapse when 4/5 cards hide. The grid is lg:grid-cols-3 (line 253). When 4 are hidden and only 1 remains, that one card spans only 1/3 of the row leaving an awkward empty 2/3. Add a centered single-card layout:

className={`grid gap-6 ${
  visibleAgents.length === 1 ? "grid-cols-1 max-w-xl mx-auto"
  : visibleAgents.length === 2 ? "grid-cols-1 md:grid-cols-2"
  : "grid-cols-1 md:grid-cols-2 lg:grid-cols-3"
}`}
Verification checklist:

 On /evidence, 5 agent cards render
 Each card shows “Validating file type…” for ~1.2 s
 Unsupported cards switch to “Bypassed” with skip message
 After 10 s, unsupported cards animate out; remaining grid centers
 Run a .png upload → only Image, Object, Metadata stay; Audio + Video fade out
STEP 6. Active agents stream live progress + show initial findings
Files: useSimulation.ts, AgentStatusCard.tsx, AgentProgressDisplay.tsx

✅ Live progress text streams via agentUpdates[agentId].thinking. Reveal queue (revealQueue) gates progressive disclosure.

🔴 Bug 6.1 — revealQueue stalls indefinitely if a reveal animation hook throws. useInvestigation.ts:285 shows decision buttons only when revealQueue.length === 0. If an entry never gets dequeued (e.g. unmount during animation, see useSimulation.ts:797-834), the user is stuck — no Accept / Deep button ever appears.

Fix — apps/web/src/hooks/useSimulation.ts add a watchdog that drains stuck items:

useEffect(() => {
  if (revealQueue.length === 0) return;
  const t = setTimeout(() => {
    // Force-drain any reveal that has been queued > 8 s
    setRevealQueue([]);
    isRevealingRef.current = false;
  }, 8000);
  return () => clearTimeout(t);
}, [revealQueue.length]);
🔴 Bug 6.2 — Decision buttons depend purely on backend status === "awaiting_decision". useInvestigation.ts:525 — if the backend never sends that status (e.g. SSE disconnect after all completed events), the buttons never appear even though every supported agent is done.

Fix — apps/web/src/hooks/useInvestigation.ts add a fallback:

const awaitingDecision =
  status === "awaiting_decision" ||
  (phase === "initial" &&
   expectedAgentIds.size > 0 &&
   expectedCompletedCount >= expectedAgentIds.size &&
   !revealPending);
🟠 Bug 6.3 — Initial findings never re-render if user scrolls and the card unmounts. AgentStatusCard uses local state for the “show details” toggle. If visibleAgents reorders due to the layout fix above, React will key by agent.id and remount, dropping local state. Hoist toggle state into AgentProgressDisplay keyed by agentId.

🟡 Bug 6.4 — degraded: true findings have no visible badge. Findings include degraded and fallback_reason (lines 28–29) but AgentStatusCard doesn’t surface them. Add a small amber pill: Tool fallback used: {fallback_reason} so investigators trust the report less when degraded.

Verification checklist:

 Each running card shows live thinking text streaming
 On agent finish, findings reveal one-by-one
 Decision buttons appear after the last reveal completes
 Kill SSE manually after all agents done → buttons still appear via fallback
 Findings with degraded: true show amber badge
STEP 7. Initial analysis decision buttons
File: AgentProgressDisplay.tsx:284-317

✅ Buttons render when awaitingDecision && phase === "initial" && revealQueue.length === 0 && !arbiterDeliberating.

🟠 Bug 7.1 — Disabled state during navigation does not include a spinner on Accept. accept-analysis-btn (line 295) has disabled={isNavigating} but no visible spinner; user clicks again, gets nothing. Mirror the deep button:

<button data-testid="accept-analysis-btn" disabled={isNavigating} ...>
  {isNavigating ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
  Accept Verdict
</button>
🟠 Bug 7.2 — Mobile viewport: bottom dock overlaps last agent card. fixed bottom-12 left-1/2 -translate-x-1/2 (line 290). Add pb-32 to the grid container so the last card scrolls clear:

<div className="flex flex-col w-full max-w-[1560px] mx-auto gap-8 pb-48 pt-24" ...>
(currently pb-36).

STEP 8. Accept Analysis → Arbiter overlay → Result page (initial)
File: useInvestigation.ts:417-437

🔴 Bug 8.1 — Errors in handleAcceptAnalysis are silently swallowed. catch {} (line 432) hides every failure. If the report fetch fails or the user’s session expired, the user sees the arbiter overlay forever, then it disappears, and nothing happens.

Fix — apps/web/src/hooks/useInvestigation.ts show an error and reset:

} catch (err) {
  setIsNavigating(false);
  setArbiterDeliberating(false);
  toast.destructive({
    title: "Council synthesis failed",
    description: err instanceof Error ? err.message : "Could not finalize verdict.",
  });
  return;  // do not navigate
}
🔴 Bug 8.2 — waitForFinalReport returns false on timeout but code still routes. useInvestigation.ts:429 — the return value of waitForFinalReport is discarded. If polling exhausts 5 minutes without status === "complete", the code still calls router.push("/result"), sending the user to a results page that has no report.

Fix:

const ok = await waitForFinalReport(sid, setArbiterLiveText, 300_000, arbiterAbortControllerRef.current.signal);
if (!ok) {
  toast.destructive({ title: "Council synthesis timed out", description: "Try again from the report page." });
  setIsNavigating(false);
  setArbiterDeliberating(false);
  return;
}
router.push("/result", { scroll: true });
🟠 Bug 8.3 — arbiterLiveText not cleared between sessions. If user accepts, comes back, accepts another file, the old arbiter live text is briefly visible. Reset in triggerAnalysis:

setArbiterLiveText("");
Verification checklist:

 Click Accept → overlay shows live council text
 On success → routes to /result with rendered report
 Disconnect API mid-arbiter → toast appears, no broken /result page
STEP 9. Deep Analysis → live streaming → Decision buttons
Files: useInvestigation.ts:439-455, AgentProgressDisplay.tsx:320-347

✅ Phase switches to "deep", clearCompletedAgents() resets the grid, agents re-stream.

🔴 Bug 9.1 — Deep phase grid is empty on hard refresh during deep run. AgentProgressDisplay.tsx:156-164 derives initialAgentIds from forensic_initial_agents storage. On refresh mid-deep, that key may be absent (it was cleared by an earlier reset). Falls back to supportedAgentIdsForMime — fine — but if MIME is also missing the grid renders zero cards.

Fix — apps/web/src/components/evidence/AgentProgressDisplay.tsx:

const initialAgentIds = useMemo<string[]>(() => {
  if (phase !== "deep") return [];
  const raw = storage.getItem<AgentUpdate[]>("forensic_initial_agents", true);
  if (Array.isArray(raw) && raw.length) {
    return raw.map((a) => a.agent_id).filter((id): id is string => typeof id === "string");
  }
  const fromMime = Array.from(supportedAgentIdsForMime(mimeType || undefined));
  if (fromMime.length) return fromMime;
  // Last-ditch: show every non-arbiter agent so the grid is never empty.
  return allValidAgents.map(a => a.id);
}, [phase, mimeType]);
🔴 Bug 9.2 — Decision dock condition for deep is too tight. line 321: !awaitingDecision && phase === "deep" && revealQueue.length === 0 && (allAgentsDone || pipelineStatus === "complete"). If backend emits awaiting_decision even on deep finish (some pipelines do, for HITL), the buttons NEVER appear in deep phase because of !awaitingDecision.

Fix:

{phase === "deep" && revealQueue.length === 0 && (allAgentsDone || pipelineStatus === "complete") && !arbiterDeliberating && (
🟠 Bug 9.3 — “Run Deep Analysis” called twice if user double-clicks. handleDeepAnalysis guards via investigationInFlightRef.current, but the button itself doesn’t disable. Add disabled={isNavigating || phase === "deep"} so it greys out immediately on first click.

Verification checklist:

 Click DEEP ANALYSIS → grid resets, agents re-stream
 Live tool descriptions appear (from extended toolset)
 Refresh mid-deep → grid renders the same agents
 On deep complete → New Ingestion + View Report dock appears
STEP 10. New Analysis → file upload modal
File: useInvestigation.ts:478-486

🔴 Bug 10.1 — Aborts not propagated to in-flight arbiter polling. handleNewUpload resets state but does NOT call arbiterAbortControllerRef.current?.abort(). If user clicks New Analysis while arbiter is deliberating, polling continues in background and the next investigation’s state can be polluted.

Fix — apps/web/src/hooks/useInvestigation.ts:478:

const handleNewUpload = useCallback(() => {
  playSound("click");
  arbiterAbortControllerRef.current?.abort();          // <-- ADD
  arbiterAbortControllerRef.current = null;            // <-- ADD
  setArbiterDeliberating(false);                        // <-- ADD
  setArbiterLiveText("");                               // <-- ADD
  setFile(null);
  setPhase("initial");
  setWsConnectionError(null);
  lastSessionIdRef.current = null;
  storage.removeItem("forensic_session_id");           // <-- ADD: prevent auto-reconnect to old session
  storage.removeItem("forensic_initial_agents");       // <-- ADD
  storage.removeItem("forensic_deep_agents");          // <-- ADD
  resetSimulation();
  router.push("/?upload=1");
}, [resetSimulation, playSound, router]);
🟠 Bug 10.2 — ?upload=1 query is dropped if route guard intercepts. HeroAuthActions.tsx:51-60 reads it once on mount. If the user is unauthenticated and your app somehow redirects, the param is lost. Defensive: also store a one-shot flag:

sessionOnlyStorage.setItem("fc_open_upload_once", "1");
// in HeroAuthActions: also check this key, then remove it
Verification checklist:

 After deep, click New Ingestion → routes to /, modal opens immediately
 Old session_id no longer in storage
 Network tab shows no zombie polls after click
STEP 11. View Report → Arbiter deliberation → Result page (deep)
File: useInvestigation.ts:488-505

🔴 Bug 11.1 — Identical issues 8.1 / 8.2 here. Errors silenced (finally only resets flags), waitForFinalReport return value ignored.

Fix — apps/web/src/hooks/useInvestigation.ts:488 mirror the Accept fix:

const handleViewResults = useCallback(async () => {
  if (isNavigating) return;
  playSound("complete");
  storage.setItem("forensic_deep_agents", completedAgentsRef.current, true);
  setIsNavigating(true);
  setArbiterDeliberating(true);
  const sid = storage.getItem("forensic_session_id");
  try {
    if (!sid) throw new Error("No active session");
    arbiterAbortControllerRef.current = new AbortController();
    const ok = await waitForFinalReport(sid, setArbiterLiveText, 600_000, arbiterAbortControllerRef.current.signal);
    if (!ok) throw new Error("Report synthesis timed out");
    router.push("/result", { scroll: true });
  } catch (err) {
    toast.destructive({
      title: "Could not load report",
      description: err instanceof Error ? err.message : "Try again.",
    });
  } finally {
    setIsNavigating(false);
    setArbiterDeliberating(false);
  }
}, [playSound, router, isNavigating]);
Note: deep-analysis reports can take >5 min for video files; bumped timeout to 600_000 ms (10 min).

🟠 Bug 11.2 — /result reads forensic_is_deep to decide which payload to render. Verify apps/web/src/app/result/page.tsx and useResult.ts actually flip on this flag. If not, deep page reuses initial findings. Quick check:

grep -n "forensic_is_deep" apps/web/src
Verification checklist:

 Click View Report → arbiter overlay → routes to /result
 Result page shows deep findings (compare to initial)
 Arbiter timeout shows toast, stays on /evidence
STEP 12. Cross-cutting issues (do these last; they affect every step)
🔴 Bug 12.1 — PageTransition exit blocks navigation feel laggy. apps/web/src/app/evidence/page.tsx:102 wraps in PageTransition. Combined with mode="popLayout" inside the agent grid, exit animations stack. Keep PageTransition only on top-level routes; remove the <> fragment-with-key churn. Set mode="wait" on the inner AnimatePresence and mode="sync" here.

🔴 Bug 12.2 — crypto.randomUUID() in triggerAnalysis will throw on insecure (http://) browsers. useInvestigation.ts:233. If the prod is plain http, this crashes the entire upload flow.

Fix:

const uuid = (typeof crypto !== "undefined" && "randomUUID" in crypto)
  ? crypto.randomUUID()
  : Math.random().toString(36).slice(2) + Date.now().toString(36);
const caseId = storage.getItem("forensic_case_id") || "CASE-" + uuid;
🟠 Bug 12.3 — validateError text dangles. apps/web/src/app/evidence/page.tsx:148 only renders the “Initializing the forensic workspace…” block when !validationError. If validation fails, you see neither the upload form nor the error inline. Fix by surfacing validationError in the upload-form area always.

🟠 Bug 12.4 — revealPending is exported but revealQueue exposed too. Pick one and remove the other to stop drift.

🟡 Bug 12.5 — Sound: deep-analysis & accept-verdict buttons miss playSound("click"). Already partially wired (playSound("arbiter_start"), playSound("think")), but a generic click is missing → audio tactile feedback feels inconsistent. Add playSound("click") at the top of handleAcceptAnalysis, handleDeepAnalysis, handleViewResults, handleNewUpload.

🟡 Bug 12.6 — Storage cleared too aggressively on reset. resetSimulation clears state but keeps forensic_session_id. The auto-reconnect block in the useEffect (line 361) then races with a new upload. Either clear it on reset or block auto-reconnect when a new upload is in flight.

EXECUTION ORDER (recommended)
#	Phase	File(s)	Time
1	Bugs 2.1, 2.2, 2.3	HeroAuthActions.tsx, UploadModal.tsx	15 min
2	Bug 3.1	UploadSuccessModal.tsx	10 min
3	Bugs 4.1, 4.2, 12.2	useInvestigation.ts	20 min
4	Bugs 5.1, 5.2, 5.3	AgentProgressDisplay.tsx, AgentStatusCard.tsx	30 min
5	Bugs 6.1, 6.2, 6.4	useSimulation.ts, useInvestigation.ts, AgentStatusCard.tsx	30 min
6	Bugs 7.1, 7.2	AgentProgressDisplay.tsx	10 min
7	Bugs 8.1, 8.2, 8.3	useInvestigation.ts	15 min
8	Bugs 9.1, 9.2, 9.3	AgentProgressDisplay.tsx, useInvestigation.ts	15 min
9	Bug 10.1	useInvestigation.ts	5 min
10	Bug 11.1	useInvestigation.ts	10 min
11	Bugs 12.1, 12.3, 12.5, 12.6	various	20 min
Total: ~3 hours of focused frontend work. No backend changes needed for the workflow you described.

MASTER FUNCTIONAL CHECKLIST (single-page tick sheet)
Landing → CTA

 Hero + CTA visible, no console errors
 CTA opens UploadModal
 Backend down → CTA → file → Begin → modal closes, error modal shows
 Back from /evidence works without stuck spinner
Upload → Success modal

 File select transitions to UploadSuccessModal
 X / ESC closes back to upload
 Begin Analysis routes to /evidence with overlay
Analysis progress overlay

 Overlay covers route transition
 Dismisses on first agent update OR after 20 s safety
 Auth fail → overlay dismisses + toast
Evidence page

 5 agent cards render
 Each shows "Validating file type…" briefly
 Unsupported cards show "Bypassed" → fade after 10 s
 Layout reflows when cards leave (1/2/3-col responsive)
Active agents

 Live "thinking" text streams per running card
 Findings reveal one-by-one when agent finishes
 degraded: true findings show amber badge
Decision dock (initial)

 Appears only after all reveals complete
 Buttons disable + show spinner during nav
 No overlap with last card on mobile
Accept Analysis

 Arbiter overlay shows live council text
 On success → /result renders report
 On timeout → toast + stays on /evidence
Deep Analysis

 Grid resets to only previously-supported agents
 Live streaming resumes
 Refresh mid-deep keeps grid populated
Decision dock (deep)

 New Ingestion + View Report dock appears
 New Ingestion aborts polls, clears storage, opens modal on /
 View Report → arbiter overlay → /result with deep payload
Cross-cutting

 http://localhost (no HTTPS) upload works (no crypto.randomUUID crash)
 Sound effects on all decision clicks
 No zombie network requests after route changes
 No console errors throughout the entire flow
When every box is ticked the workflow you described — landing → CTA → upload → success → overlay → evidence → 5 agents validate → skipped fade → live progress → initial findings → decision → arbiter → result → deep → decision → new/view report — will work end-to-end without dead ends.

Ping me if you want me to drill into a specific bug, write the patch directly, or audit /result and the report-rendering layer next.
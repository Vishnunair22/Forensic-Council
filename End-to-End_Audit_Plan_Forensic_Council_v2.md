# End-to-End Audit Plan — Forensic Council (v2, Updated)

> **What changed in v2 (read this first):** This revision was produced after reading the
> actual application source (`apps/web` and `apps/api`). The original plan was substantively
> accurate, but a handful of claims were wrong against the real code and a few real gaps were
> missing. Every correction is called out inline with a **`[v2 CORRECTION]`** or **`[v2 NEW]`**
> tag so you can see exactly what moved. The corrections that matter most:
>
> 1. **The worker is NOT Celery.** It is a custom Redis-queue consumer started with
>    `command: ["worker"]` and health-checked by `scripts/worker_healthcheck.py`. The original
>    CP0 augmentation (`celery -A app.worker inspect ping`) would simply fail. Fixed in CP0.
> 2. **The database tables are not `sessions` / `investigation_checkpoints`.** The real schema
>    (`alembic/versions/0001_initial_schema.py`) creates: `users`, `session_reports`,
>    `investigation_state`, `user_sessions`, `audit_log`, `chain_of_custody`,
>    `evidence_artifacts`, and `hitl_checkpoints`. Fixed in CP23.
> 3. **There is a stray temp file** — `apps/api/get_session_details_temp.py` — that must be
>    removed. Added to CP22.
> 4. **An existing Playwright e2e + accessibility suite already exists** under `apps/web/tests/`
>    and was never referenced. It is now a first-class regression gate (CP20 + new CP25).
> 5. The `/session-expired` eyebrow copy is "Security Boundary", not "System Halt". Fixed in CP1.6.
>
> Everything else from the original plan is preserved.

---

## Operating Standard (applies to every checkpoint)

**On design audits.** Every element on screen gets named and evaluated — not just the
prominent ones. Background layers (gradient blobs, noise textures, canvas elements),
decorative rings and lines, spacing between every component, border radii, opacity levels on
text and borders, icon sizes and stroke weights, font sizes and weights at every breakpoint,
shadow and glow values, and hover/focus/active states on every interactive element. If an
element exists in the DOM it gets audited. Nothing is assumed "fine" because it looks roughly
correct.

**On flow audits.** Every step is executed and verified — not just the happy path. When a
defect is found mid-step, it is fixed surgically at that step, the fix is verified to not have
broken adjacent elements visually or functionally, and only then does the audit continue.
Findings are never logged-and-deferred. A flow is not marked done until every step has passed
in the same session, in order, with no fresh issue appearing.

**Execution gates.** Each checkpoint must fully pass before the next begins. Fix findings
in-place during the relevant checkpoint — do not accumulate a debt list.

**Before you begin.** Create the live tracking file (see end of document).

---

## CHECKPOINT 0 — Infrastructure & Endpoint Readiness

**Goal:** Confirm the Docker stack is live, all services respond, and the full API surface is
reachable before touching any UI.

Steps:

1. `GET /health` and `GET /api/v1/health` — expect 200. Note: this is a *deep* health check
   (verifies Postgres, Redis, Qdrant, migration state) and returns 503 if any dependency is
   down.
2. `GET /live` and `GET /api/v1/live` — expect 200. This is the *lightweight* liveness probe;
   it does not check dependencies.
3. `GET /api/v1/health/ml-tools` — record every tool's ready/degraded status; document any
   degraded tools before the UI audit begins so degradation findings aren't confused with bugs.
4. `GET /api/v1/health/tools` — verify the tool registry is fully populated.
5. `POST /api/v1/auth/login` with the dev credentials (`investigator` / value of
   `BOOTSTRAP_INVESTIGATOR_PASSWORD`) — receive a JWT; store it for all subsequent calls.
   Note the demo-user fallback only works when `APP_ENV != production`.
6. `GET /api/v1/auth/me` — confirm identity round-trips correctly.
7. `GET /api/v1/sessions` — verify the endpoint responds even if empty.
8. `POST /api/v1/auth/refresh` — verify a fresh token is issued from the existing one.
9. WebSocket handshake smoke test: open `WS /api/v1/sessions/bad-id/live` with the
   `forensic-v1` subprotocol — expect close code **4004**; open with no auth — expect **4001**.
10. `GET /api/v1/metrics/public` — verify the public metrics endpoint responds.
11. **`[v2 CORRECTION]` Worker liveness — the worker is a Redis-queue consumer, not Celery.**
    Verify the worker container is alive and heartbeating, not with a Celery command (there is
    no Celery in this app), but with the project's own healthcheck script:
    `docker compose exec worker python /app/scripts/worker_healthcheck.py`
    — expect exit code 0 and `Worker heartbeat present: forensic:worker:heartbeat`. A missing
    heartbeat means the worker is dead and the investigation pipeline will hang silently while
    every health endpoint above still returns 200.

**Pass criteria:** All health endpoints 200, JWT issued and refreshable, WS error codes
correct (4004 / 4001), metrics accessible, worker heartbeat present.
**Gate:** Do not proceed if any health endpoint fails, the JWT cannot be obtained, or the
worker heartbeat is missing.

---

## CHECKPOINT 0.5 — Global A11y Structure

**Goal:** Verify the HTML-level a11y foundation that every subsequent checkpoint depends on.
These are impossible to test inside individual component checkpoints.

Steps:

1. Open `http://localhost:3000` and immediately press Tab — verify the skip-to-main-content
   link appears visually above the navbar with correct styling (`fc-surface-elevated`,
   readable text, focus ring). Source: `layout.tsx` skip-link anchor.
2. Activate the skip link with Enter — verify focus jumps to `#main-content`, bypassing the
   navbar entirely.
3. Verify `<html lang="en" dir="ltr">` is present in the DOM (`layout.tsx`).
4. Verify `<main id="main-content">` wraps all page content and carries `pt-16` offset for the
   fixed navbar.
5. Verify the page `<title>` is "Forensic Council" on `/`, and follows the
   `%s | Forensic Council` template on `/evidence` and `/result/{sessionId}` (metadata
   template confirmed in `layout.tsx`).
6. Verify the `viewport` config has no `user-scalable=no` or `maximum-scale` — confirmed
   `width: device-width, initialScale: 1` only; AT zoom is not blocked.
7. Verify `GlobalNavbar` renders `<nav>` with a main-navigation label.
8. Verify the navbar brand button has the correct contextual `aria-label` (resets the session
   when one is active; returns to top when on home with no session).
9. Verify the navbar hides on scroll down and reappears on scroll up; verify it stays visible
   (and reachable) when `isKeyboardUser` is true — Tab into the navbar while scrolled and
   confirm it is not hidden and focus is not trapped behind a hidden element.
10. Verify both Google Fonts (Inter, JetBrains Mono) load with `display: swap` (confirmed in
    `layout.tsx`) — no invisible text during load.
11. Open Chrome DevTools → Rendering → emulate `prefers-reduced-motion: reduce` — reload and
    confirm no animations play on the landing page.
12. Run a Lighthouse Accessibility audit on `/` — record the score as the baseline; any item
    below 90 is a finding.

**Pass criteria:** Skip link works; `lang`/`dir`/`#main-content` present; titles update per
route; viewport allows zoom; navbar a11y intact and does not trap keyboard users; fonts
swapped; no animation under reduced motion; Lighthouse score documented.

---

## CHECKPOINT 1 — App Load, Refresh, Reset

**Goal:** Confirm cold load, hard refresh, direct navigation, and browser-back all behave
cleanly with no console errors or hydration mismatches.

Steps:

1. Open `http://localhost:3000` cold — zero console errors.
2. Hard refresh (Ctrl+Shift+R) — no hydration mismatch; no `suppressHydrationWarning` warnings
   leaking into the console.
3. Navigate directly to `/evidence` with no session — verify a graceful redirect or empty
   state, not a blank crash.
4. Navigate directly to `/result` — verify `ResultClientRedirect` behavior (redirects to the
   latest session or shows the `ResultStateView` empty state).
5. Navigate directly to `/result/invalid-session-id` — verify `ResultStateView` renders an
   empty/error state, not a blank page.
6. Navigate to `http://localhost:3000/totally-invalid-route` — verify `not-found.tsx` renders
   with the "404 — Route Not Found" eyebrow, the "Page Not Found" `<h1>`, a "Dashboard" link
   to `/`, and a "New Investigation" link to `/?upload=1`.
7. Verify the 404 "New Investigation" link goes to `/?upload=1` (not bare `/`) — confirmed in
   `not-found.tsx`.
8. Open `/?upload=1` directly in a fresh tab — verify `HeroAuthActions` auto-opens the upload
   modal on mount, then strips the `?upload` param from the URL without a full navigation.
9. Verify `sessionStorage` and `localStorage` are clean on a fresh load — no keys from prior
   sessions bleeding in.
10. Verify `RouteExperience` clears the `data-fc-loading` body attribute when the pathname does
    not start with `/result`.
11. Verify `RouteExperience` scroll-to-top fires on forward navigation but NOT on browser
    back/forward (popstate correctly detected via `isPopRef`).

**Pass criteria:** No console errors on cold load; all direct-nav edge cases resolve cleanly;
404 renders and links correctly; `/?upload=1` auto-opens the modal; popstate scroll preserved.

---

## CHECKPOINT 1.5 — Session Reconnect Flow

**Goal:** Verify Effect B in `useInvestigation` — navigating to `/evidence` with an existing
`SESSION_ID` in `localStorage` reconnects correctly without starting a new investigation. This
path is entirely separate from the upload flow and is never exercised otherwise.

Steps:

1. Complete a full investigation to the `awaiting_decision` / HITL pause point (initial
   analysis done, HITL not yet submitted).
2. Close the tab — do not navigate.
3. Open a new tab and go to `/evidence` directly.
4. Verify Effect B fires: the hook reads `SESSION_ID` from `localStorage`, calls
   `GET /api/v1/sessions/{id}/arbiter-status`, finds the session still active, and reconnects
   the WebSocket via `connectWebSocket(sid, true)`.
5. Verify agent cards restore from `localStorage` (`INITIAL_AGENTS:{sid}`) — agents show their
   completed state, not blank cards.
6. Verify the HITL decision UI reappears so the investigator can continue.
7. **Completed-session redirect:** complete an investigation all the way to the report
   (arbiter status `complete`), then navigate to `/evidence`. Verify Effect B detects
   `status: "complete"` and immediately pushes to `/result/{sid}` without showing the evidence
   page at all.
8. **Expired-session clear:** with an expired/deleted session in `localStorage`, navigate to
   `/evidence`. Verify the hook gets `not_found` from `arbiter-status`, clears the stale
   session, shows a destructive "Session expired" toast, and leaves the user on a clean
   evidence page.
9. **`FC_NO_RECONNECT` flag:** after clicking "New Analysis" on the evidence page, navigating
   back to `/evidence` must NOT reconnect to the old session — verify the flag is set and
   cleared correctly.

**Pass criteria:** Reconnect restores agent state and HITL UI; completed session redirects to
result; expired session clears with a toast; `FC_NO_RECONNECT` prevents unwanted reconnects.

---

## CHECKPOINT 1.6 — Session Expired Page

**Goal:** The `/session-expired` page renders correctly, both buttons produce the right side
effects, and the design is audited.

Steps:

1. Navigate directly to `/session-expired` — verify `SessionExpiredClient` renders without a
   crash.
2. **`[v2 CORRECTION]`** ui-ux-pro-max design audit: `GlassPanel`, the `ShieldAlert` icon, the
   eyebrow micro-accent text — note the actual eyebrow copy is **"Security Boundary"** (the
   original plan said "System Halt"; audit against the real string). Also audit heading
   hierarchy, button spacing, and the red accent glow blob behind the panel.
3. A11y: verify the `<h1>` has an `aria-label` describing "Session expired"; both buttons have
   `aria-label`; the `ShieldAlert` and `Cpu` decorative icons have `aria-hidden`; focus order
   is logical (heading → description → buttons).
4. **"Return to Hub" while already on `/`:** verify it dispatches
   `window.dispatchEvent(new Event("fc:reset-home"))` rather than a `router.push` that would
   loop — and verify `HeroAuthActions` handles the event by closing any open modals and
   resetting file state.
5. **"Return to Hub" while on `/session-expired`:** verify `router.push("/")` fires and the
   landing page loads cleanly.
6. **"New Intake":** verify `FC_OPEN_UPLOAD_ONCE=1` is set in `sessionStorage`, the router
   pushes to `/`, and the upload modal auto-opens on landing via the `openOnce` check.
7. Verify the upload modal opened via "New Intake" has clean state — no stale file from a
   prior session.
8. Tab through the page — both buttons reachable with correct focus styles.

**Pass criteria:** Design clean; both button side effects correct; `fc:reset-home` dispatches
correctly; "New Intake" auto-opens a clean upload modal; a11y attrs present; keyboard nav works.

---

## CHECKPOINT 2 — Landing Page Design Audit

**Goal:** Full visual and a11y audit of the landing page at `/`.

Design steps:

1. Full-page screenshot of `/`.
2. ui-ux-pro-max audit covering every element top to bottom:
   - **Hero:** typography hierarchy, gradient/glassmorphism, CTA button prominence.
   - **AgentsSection:** spin rings must be CSS (`[animation:spin_Xs_linear_infinite]`), not
     Framer Motion `rotate: 360` — confirm per the project rule; card grid spacing.
   - **HowWorksSection:** step numbering, connector lines, icon–text alignment.
   - **GlobalNavbar:** brand logo, sticky behavior, scroll-hide behavior.
   - **GlobalFooter:** alignment, link contrast.
   - **LandingBackground:** no layout shift, no paint flicker.
   - Color-palette cohesion across all sections.
   - Responsive breakpoints: mobile (375px), tablet (768px), desktop (1280px).

A11y steps:

3. Verify heading hierarchy: one `<h1>` in the hero, `<h2>` on each major section, `<h3>`
   within cards — no skipped levels.
4. Verify each major `<section>` has `aria-labelledby` pointing to its heading.
5. Verify all decorative elements (gradient blobs, background rings) have `aria-hidden="true"`.
6. Verify the CTA button has a descriptive `aria-label` and a visible focus ring at 200% zoom.
7. Run a Lighthouse accessibility audit — score must be ≥ 90; note any contrast failures.
8. Run the axe-core browser extension — flag any WCAG AA contrast failures. Pay specific
   attention to `fc-text-muted`, `fc-text-faint`, `fc-eyebrow`, and `text-white/60` on dark
   backgrounds; sample actual rendered colors with the DevTools color picker (4.5:1 target).
9. While on the landing page, press Tab — the skip link must be the very first focusable
   element.
10. With OS reduced motion enabled, reload — verify no spinning rings and no entrance
    animations play; layout intact.

**Pass criteria:** ui-ux-pro-max clean; CSS spin rings confirmed; heading hierarchy correct;
Lighthouse ≥ 90; axe-core zero critical findings; contrast passes AA; skip link first on Tab;
reduced motion respected.

---

## CHECKPOINT 3 — Landing Page CTA → Upload Modal Flow

Steps:

1. Re-confirm `/?upload=1` auto-opens the upload modal in the visual context (also covered in
   CP1).
2. Click the primary CTA — verify `UploadModal` opens (not `UploadSuccessModal`).
3. Verify `document.body.style.overflow === "hidden"` immediately after the modal opens
   (overflow lock managed by `HeroAuthActions`, not inside the modal).
4. Verify `DialogTitle` is "Upload Evidence" (sr-only in the DOM, screen-reader-visible).
5. Verify `onFocusOutside` prevention — clicking inside the dialog wrapper does not close it.
6. Verify Escape closes the modal and restores `body.overflow` to `""`.
7. Verify backdrop click closes the modal (Radix `onOpenChange` fires).
8. **Focus return:** after the modal closes via Escape or backdrop, verify focus returns to the
   CTA button (`ctaRef`) — not lost on `document.body`.
9. **Keyboard open:** Tab to the CTA, press Enter — verify the modal opens identically to a
   mouse click.
10. Verify parallel pre-auth (`autoLoginAsInvestigator()` / `__pendingFileStore.authPromise`)
    is kicked off on CTA click — not deferred to file selection.
11. Verify clicking the CTA again while the modal is open does nothing (no double-open, no
    state reset).
12. **Focus trap:** with the modal open, Tab through close button → dropzone → file input —
    verify focus does not escape the dialog.

**Pass criteria:** Modal opens; overflow locked; Escape/backdrop dismiss correct; focus returns
to CTA; auth prefetch fires on CTA click; focus trap confirmed.

---

## CHECKPOINT 4 — Upload Modal Design Audit

Steps:

1. Screenshot the open upload modal.
2. ui-ux-pro-max audit: glassmorphism container, `backdrop-blur` on overlay, drag-drop zone
   dashed border, icon color, button states (idle/hover/dragging), close X position.
3. Verify accepted file types are communicated: "images, video, audio (max 50MB)".
4. Verify the close X is at least a 40×40px touch target (`w-10 h-10`), has
   `aria-label="Close upload dialog"`, and the X icon has `aria-hidden="true"`.
5. Verify the drag-over visual state changes (border becomes solid primary, background tints,
   icon turns primary, text changes to "Drop Evidence").
6. Verify the `dragLeave` child-element false-positive is handled — moving the mouse from the
   drop zone onto a child element does NOT cancel the drag state.
7. Verify the processing-state spinner is CSS `animate-spin`, not Framer Motion `rotate: 360`.
8. A11y — dropzone: `role="button"`, `tabIndex={0}`, descriptive `aria-label`,
   `aria-describedby` includes `upload-file-help` always and `upload-error` only when an error
   is present.
9. A11y — error state: submit an invalid file — verify `role="alert"` fires on the error
   paragraph (`id="upload-error"`) for an immediate AT announcement.
10. A11y — loading state: after a valid file is selected, verify `role="status"` on the spinner
    and `aria-live="polite"` on the "Preparing secure channel…" text.
11. A11y — keyboard: press Enter on the focused dropzone — file picker opens; press Space —
    file picker opens.
12. Verify `useReducedMotion` suppresses entrance/exit animations.

**Pass criteria:** Design clean; drag states correct; CSS spin confirmed; all a11y attrs
verified and keyboard-triggerable; error fires as `role="alert"`.

---

## CHECKPOINT 5 — File Picker → Selection → Upload Success Modal

Steps:

1. Click the dropzone to open the native file picker; select a valid JPEG under 50MB.
2. Verify `playSound("success-chime")` fires in `UploadModal.selectFile` — NOT on
   `UploadSuccessModal` mount.
3. Verify `__pendingFileStore.file` is populated: in the console, `window.__pendingFileStore?.file`
   should be the selected `File` object.
4. Verify `UploadSuccessModal` renders with the correct filename and formatted file size.
5. **Thumbnail capture (image):** verify a 240px JPEG thumbnail is captured and stored in
   `localStorage` under `STORAGE_KEYS.THUMBNAIL` — check via DevTools → Application → Local
   Storage.
6. **Thumbnail clear (non-image):** select an MP3 — verify the thumbnail key is CLEARED from
   `localStorage` (not left stale from a prior image test); repeat for an MP4.
7. **Rejection — invalid type:** select a `.pdf` — verify the error appears inside the modal
   with `role="alert"`, no crash, no navigation.
8. **Rejection — oversized:** select a file > 50MB — verify the size rejection appears with
   `role="alert"`.
9. Verify dropping a file onto the dropzone behaves identically to picking via the file input.
10. Verify the 600ms debounce on `selectFile` prevents double-submission (rapid clicking
    cannot open two success modals).
11. Verify a re-selected invalid file after a prior error clears the old error before showing
    the new one.

**Pass criteria:** Success chime fires in the upload modal; store populated; thumbnail captured
for images and cleared for non-images; rejections show `role="alert"`; no double-submission.

---

## CHECKPOINT 6 — Upload Success Modal Design Audit

Steps:

1. Screenshot the success modal with an image file selected.
2. ui-ux-pro-max audit: file icon/thumbnail area, filename text, file size, "Begin
   Investigation" and "Upload Different File" buttons, `backdrop-blur-xl` on the overlay,
   glassmorphism consistency.
3. Verify the X button calls `onDismiss` — NOT `onNewUpload` (Phase 3 fix; confirm intact).
4. Verify backdrop click calls `onDismiss`.
5. Verify "Upload Different File" calls `onNewUpload` → clears `selectedFile` → returns to
   `UploadModal` within the same Radix Dialog.
6. Verify the modal does NOT set `document.body.style.overflow` itself (managed solely by
   `HeroAuthActions`).
7. Verify `onDismiss` is a required prop (TypeScript confirms — no default).
8. Verify the `isHandingOff` guard prevents a double-tap of "Begin Investigation".
9. A11y: `DialogTitle` switches to "Evidence Ready" when the success modal is active; all
   buttons have visible text; icons inside buttons have `aria-hidden`.
10. A11y: verify focus is placed on the first interactive element when transitioning from
    `UploadModal` to `UploadSuccessModal` within `AnimatePresence`.
11. Tab through the modal — "Upload Different File" and "Begin Investigation" both reachable,
    correct tab order.

**Pass criteria:** Design clean; `backdrop-blur-xl` present; dismiss behavior correct;
double-tap guarded; `DialogTitle` updates; focus placed correctly on transition.

---

## CHECKPOINT 7 — Upload Success Modal → Loading Overlay Flow

Steps:

1. Click "Begin Investigation".
2. Verify `clearInvestigationPersistence()` fires before any new state is set.
3. Verify `POST /api/v1/investigate` fires with the correct multipart form: `file`, `case_id`
   (starts with `CASE-`), `investigator_id` (matches `REQ-\d{5,10}`).
4. Verify a 200 response with `session_id`, `case_id`, `status: "started"`.
5. Verify `session_id` is written to BOTH `localStorage` (`SESSION_ID` key) and a session
   cookie: `document.cookie` should contain `SESSION_ID={uuid}; path=/; max-age=3600;
   SameSite=Lax`.
6. Verify the cookie name matches what the WS auth layer expects — cross-check against the
   API contract's auth-cookie order (`fc_session`, `sessionid`, `access_token`).
7. Verify `INVESTIGATION_CTX` and the per-session storage keys (`INVESTIGATION_CTX:{sid}`) are
   written atomically.
8. Verify `FC_SHOW_LOADING=true` and `AUTO_START=true` are written to session-only storage
   before navigation; verify `FC_PENDING_FILE_META` is written with `{name, type, size,
   updatedAt}`.
9. Verify `GlobalLoadingOverlay` renders during the route change (reads `FC_SHOW_LOADING` from
   `sessionStorage` via the `fc_storage_update` event).
10. Verify the route changes to `/evidence`.
11. Verify `__pendingFileStore.file` is still accessible at `/evidence` on first render (not
    nulled before `triggerAnalysis` / Effect A reads it).
12. Verify `data-fc-loading="1"` is NOT set on `document.body` here — it is set only by
    `handleAcceptAnalysis` when navigating to `/result/{sid}` — and that `RouteExperience`
    clears it when the pathname stops starting with `/result`.
13. **409 duplicate path:** submit the same file again while the session is active — verify
    the frontend catches `DuplicateInvestigationError`, calls `restoreSimulationState` with
    saved agent data, reconnects to the existing session's WebSocket, shows "Reconnected to
    existing analysis" upload-phase text, and does not crash or start a new session.
14. **Rate limiting:** if a 429 is returned from `POST /investigate`, verify a destructive
    toast fires with the error message — not a blank error state.

**Pass criteria:** `POST /investigate` correct; cookie + `localStorage` written;
`GlobalLoadingOverlay` visible during nav; 409 reconnects with state restore; 429 produces a
toast.

---

## CHECKPOINT 8 — Loading Overlay Design & Safety

Steps:

1. Throttle the network (DevTools: Fast 3G) and trigger the upload → evidence transition.
2. Screenshot `LoadingOverlay` while active.
3. ui-ux-pro-max audit: full-viewport coverage, `backdrop-blur-2xl`, `bg-background/90`,
   left accent border, animated heading, debounced live text (80ms), monospace live text,
   CSS-pulsed dot, progress bar animation, `z-index` 10000 above all content.
4. Verify the text sanitizer strips `PIPELINE:`, `UPLOAD:`, `AUTH:`, `SYSTEM:` prefixes from
   backend messages before display.
5. Verify `aria-busy="true"` and `aria-label="Analysis in progress, please wait"` on the
   overlay root.
6. Verify `role="status"` + `aria-live="polite"` + `aria-atomic="true"` on the live-text
   paragraph.
7. **Dual `<h1>` check:** `LoadingOverlay` renders an `<h1>` via portal — while it is visible,
   count `<h1>` elements in the DOM. There should be only one visible `<h1>` at a time. If the
   landing-page `<h1>` and the overlay `<h1>` coexist, flag as a finding (overlays should use
   `<p>` or `aria-label` instead of `<h1>`).
8. **`[v2 NOTE]`** The animated progress bar is a `<motion.div>` with no `role="progressbar"`
   and no `aria-valuenow/min/max`. It is decorative. Flag it: add `aria-hidden="true"` to make
   the decorative intent explicit (this is finding F-7 below).
9. Verify the overlay renders via `createPortal` into `document.body` — no z-index stacking
   issues from parent transforms.
10. Verify the overlay disappears cleanly when `/evidence` mounts and the stream becomes ready
    (or after `ANALYSIS_STARTUP_GRACE_MS`), with a 2.5s minimum display enforced — no flash of
    unstyled content after exit.
11. **8-second hard safety timeout:** block the WebSocket endpoint (DevTools → Network → block
    `ws://localhost:8000` / `*/live`) — the overlay must dismiss after 8s with a "Connection
    Timeout" destructive toast. Separately, stop the backend container and confirm the same.
12. Restart the backend — verify the app recovers cleanly from that state.
13. Reduced motion: with OS reduced motion enabled, verify the pulsing dot and progress-bar
    animation are suppressed and the `<h1>` has no entry animation.

**Pass criteria:** Design clean; ARIA correct; dual-`<h1>` finding documented; portal z-index
correct; 2.5s minimum enforced; 8s safety timeout fires with toast; clean exit; reduced motion
respected.

---

## CHECKPOINT 8.5 — WebSocket Connection Failure + Retry

**Goal:** When the WebSocket fails to connect, `wsConnectionError` triggers `ForensicErrorModal`
and `retryWsConnection` recovers cleanly.

Steps:

1. Block the WebSocket endpoint (DevTools → Network → block `*/live`) before triggering an
   investigation.
2. Verify `wsConnectionError` is set after the connect promise rejects and `ForensicErrorModal`
   renders — determine and document whether the transient variant ("Stream Synchronization
   Lost") or full quarantine mode fires for a hard WS failure.
3. ui-ux-pro-max audit of `ForensicErrorModal`: danger accent, "Quarantine Protocol Active"
   eyebrow, error-code display, UTC timestamp pinned at modal mount (not drifting per render),
   "Retry Analysis" and "Return to Hub" buttons.
4. A11y: `Dialog.Title` and `Dialog.Description` both render; `role="dialog"` +
   `aria-modal="true"` applied by Radix; `aria-label="Close"` on the X; `playSound("alert-error")`
   fires on open.
5. Unblock the WebSocket — click "Retry Analysis" — verify `retryWsConnection` fires:
   `startSimulation()` is called, `connectWebSocket(sid)` reconnects, `ForensicErrorModal`
   dismisses, analysis resumes.
6. Verify retry respects `lastSessionIdRef` — if a session ID exists it reconnects to that
   session, not a fresh one.
7. Click "Return to Hub" — verify `router.push("/")`, session storage cleaned, no stale
   loading state persists.
8. Verify focus is not lost to `document.body` after the modal dismisses (retry or hub).
9. **SSE fallback:** verify `GET /api/v1/sessions/{session_id}/progress` (SSE) is reachable as
   a fallback and returns the same event types as the WebSocket.
10. Test the transient variant: simulate a brief disconnect/reconnect — verify the
    transient-style message appears instead of full quarantine mode.

**Pass criteria:** `ForensicErrorModal` renders for WS failure; retry reconnects to the correct
session; hub navigation cleans state; focus managed; SSE endpoint reachable.

---

## CHECKPOINT 9 — Evidence Page Load & AgentProgressDisplay Audit

Steps:

1. Trigger a fresh investigation — let it reach the evidence page with the WebSocket connected.
2. Verify the WebSocket opens to `WS /api/v1/sessions/{session_id}/live` with the `forensic-v1`
   subprotocol.
3. Verify the `CONNECTED` message is received and handled without error and without showing as
   raw JSON in the UI.
4. Verify all expected agent slots render in their initial state (waiting/queued).
5. Verify `ActiveAgentsPanel` count badge shows the correct number for the file's MIME type.
6. Verify `SkippedAgentsPanel` shows agents not applicable to the file type.
7. Verify `isReconnecting` shows a reconnecting indicator when Effect B is active — not a
   blank state.
8. Verify the navbar page label changes to "Evidence Intake".

Design steps:

9. Screenshot `AgentProgressDisplay` before analysis starts.
10. ui-ux-pro-max audit: the `<h1>` "Forensic Analysis" heading size/weight, phase badge, live
    status text area, `ActiveAgentsPanel` / `SkippedAgentsPanel` accordion styling, agent card
    grid (1/2/3 columns per count), card spacing, `ArbiterCard` waiting-state styling, status
    dot colors for each agent state.

A11y steps:

11. Verify `aria-label="Agent forensic analysis progress"` on the outer container div.
12. Verify the live status line has `role="status"` + `aria-live="polite"` +
    `aria-atomic="false"`.
13. Tab to the "Active Agents" accordion button — verify `aria-expanded={false}` initially and
    `aria-controls="active-agents-panel"`; press Enter to expand, verify `aria-expanded`
    becomes true and the panel appears; press Enter again to collapse.
14. Same test for `SkippedAgentsPanel` with `aria-controls="skipped-agents-panel"`.
15. Verify the `w-2 h-2` colored status dots in the expanded panel are `aria-hidden="true"` and
    the adjacent text label is always present and accurate (color is not the only signal).
16. Verify the whole evidence page has a logical Tab order: navbar → main → `<h1>` → accordion
    buttons → agent cards → decision buttons (when visible).

**Pass criteria:** WS connects; initial state correct; both accordions keyboard-operable with
correct ARIA; live status region announced; status dots have text companions; Tab order logical.

---

## CHECKPOINT 10 — Initial Analysis: Full Pipeline Verification

### Sub-phase A — Image Evidence (Agents 1, 3, 5)

1. Submit a valid JPEG — verify `AGENT_UPDATE` messages arrive for Agent 1 (Image), Agent 3
   (Object-Scene), Agent 5 (Metadata).
2. Verify Agent 1 fires: `ela_full_image`, `jpeg_ghost_detect`, `copy_move_detect`,
   `splicing_detect`, `deepfake_frequency`, `diffusion_detector`.
3. Verify Agent 3 fires: `object_detection`, `lighting_check`, `scale_validation`.
4. Verify Agent 5 fires: `exif_extract`, `anomaly_score`, `steganography_scan`, `hash_verify`.
5. Verify Agents 2 and 4 appear in `SkippedAgentsPanel` with a "Not applicable for image
   files" label — they never show as running and never return error findings.

### Sub-phase B — Audio Evidence (Agents 2, 5)

6. Submit a valid WAV or MP3 — start a new investigation.
7. Verify Agent 2 fires: `speaker_diarization`, `anti_spoofing`, `prosody_analysis`,
   `codec_fingerprint`, `audio_splice_detect`, `voice_clone_detect` (and `noise_analysis` /
   `enf_analysis` if present).
8. Verify Agent 5 fires for audio: `exif_extract` and file-structure tools still apply.
9. Verify Agents 1, 3, 4 are skipped/not-applicable — not crashed, not errored.
10. Verify `av_sync_verify` is NOT called (no video track to sync against).

### Sub-phase C — Video Evidence (Agents 1, 2, 3, 4, 5)

11. Submit a valid MP4 — start a new investigation.
12. Verify Agent 4 fires: `optical_flow`, `frame_extraction`, `frame_consistency`,
    `face_swap_detect`, `video_metadata`, `forgery_detector`, `liveness_check`,
    `frequency_gan`, `rolling_shutter`.
13. Verify Agent 2 fires audio-track tools, including `av_sync_verify` (video has both tracks).
14. Verify Agent 1 fires on extracted keyframes: `ela_full_image`, `deepfake_frequency`.
15. Verify Agent 3 fires on video frames: `object_detection`, `lighting_check`.
16. Verify `supportedAgentIdsForMime("video/mp4")` in the console returns the correct agent set.

### Sub-phase D — Tool Quality & Live Display

17. Cross-reference `GET /api/v1/health/ml-tools` against which tools actually fire — no tool
    calls a model that is not loaded/ready.
18. Verify every `AGENT_UPDATE` message contains `agent_id`, `message`, and optionally
    `tool_name` — never a raw Python exception string.
19. Verify the live progress text in `ActiveAgentsPanel` updates per tool for the running
    agent (each `tool_name` renders via `getLiveProgressDescriptor`).
20. Verify each `AGENT_COMPLETE` fires per agent and updates the card to a complete state with
    verdict and confidence.
21. Verify no agent returns empty findings — every agent that runs returns ≥ 1 finding with a
    confidence score.

### Sub-phase E — Live Region Frequency Check (a11y)

22. With NVDA / Narrator active, run the analysis and count AT announcements per minute from
    `aria-live="polite"` regions.
23. Verify announcements are intelligible (no raw JSON, no "undefined", no empty strings).
24. Verify the frequency is not overwhelming — target ≤ 1 announcement per 3–4 seconds during
    active analysis.

### Sub-phase F — Pipeline Pause

25. Verify the `PIPELINE_PAUSED` WS message fires after all agents complete.
26. Verify `GET /api/v1/sessions/{session_id}` status is `paused`.
27. Verify `playSound("analysis_done")` fires exactly once (guarded by
    `analysisCompleteSoundedRef`).

**Pass criteria:** All file-type-appropriate agents fire with correct tools; skipped agents
shown (not errored); live display updates; `PIPELINE_PAUSED` received; AT announcements
intelligible and not overwhelming.

---

## CHECKPOINT 10.5 — Toast Notification Audit

**Goal:** Verify every critical toast fires correctly, with the right severity, and is
announced by AT.

| Toast | How to trigger | Expected severity |
|---|---|---|
| "File selection was lost after refresh" | Hard-refresh mid-pending-file with `AUTO_START=true` but no `__pendingFileStore.file` | Destructive |
| "Authentication failed" | Block `POST /api/v1/auth/login` during upload | Destructive |
| "Investigation Failed" | Upload when rate-limited (429) or with `/investigate` blocked | Destructive |
| "Evidence file rejected" | Provide an invalid MIME type via the auto-start path | Destructive |
| "Connection Timeout" | Block the WS for 8+ seconds after upload | Destructive |
| "Council synthesis failed" | Return an error from `arbiter-status` during deliberation | Destructive |
| "Decision Failed" | Block `POST /api/v1/hitl/decision` | Destructive |
| "Session expired" (reconnect) | Reconnect to a session where `arbiter-status` returns `not_found` | Destructive |
| "PDF export unavailable" | Trigger PDF export when WeasyPrint is not available | Warning |

A11y checks for each toast:

1. Verify `Toaster` renders toasts with `role="alert"` for destructive and `role="status"` for
   warning/info.
2. Verify NVDA / Narrator announces each toast without requiring user interaction.
3. Verify toasts auto-dismiss without trapping focus.
4. Verify multiple rapid toasts stack correctly without overlapping unreadably.

**Pass criteria:** All 9 toast types fire with correct severity; AT announces each one; no
focus trap; stacking correct.

---

## CHECKPOINT 11 — HITL Checkpoint: Decision UI & Arbiter Deliberation

### Sub-phase A — `HITLCheckpointModal` Design & A11y

1. Screenshot `HITLCheckpointModal` when the `HITL_CHECKPOINT` WS message is received.
2. ui-ux-pro-max audit: two-column layout, Evidence Brief panel, Decision Required panel,
   radiogroup grid, textarea, "Finalize Decision" button.
3. Verify `GET /api/v1/sessions/{session_id}/checkpoints` returns the pending checkpoint with
   the correct `checkpoint_id` (sourced from the `hitl_checkpoints` table).
4. A11y: `role="radiogroup"` with `aria-labelledby="protocol-selection-label"` on the decision
   grid.
5. A11y: each decision button has `role="radio"` and `aria-checked` toggling correctly.
6. A11y: Arrow-key navigation — Right/Down moves to the next option, Left/Up to the previous,
   focus follows selection (roving tabindex) — verify live.
7. A11y: the textarea has `aria-labelledby="hitl-notes-label"` — AT reads "Supplemental
   Documentation" as the field label.
8. A11y: the validation error has `role="alert"` — fires immediately when "Finalize Decision"
   is clicked without a selection.
9. A11y: the `ShieldAlert` icon in the modal header has `aria-hidden="true"`.
10. A11y: verify the elapsed timer in `ArbiterDeliberationOverlay` ("1:23" format) is announced
    sensibly by AT, not as "1 colon 23".

### Sub-phase B — Accept Path

11. Select "APPROVE" and click "Finalize Decision".
12. Verify `POST /api/v1/hitl/decision` fires with `{"decision": "APPROVE", "checkpoint_id":
    "...", "agent_id": "...", "session_id": "..."}`.
13. Verify `ArbiterDeliberationOverlay` appears with `aria-busy="true"`,
    `aria-label="Consensus Synthesis in progress"`, and `role="status"` + `aria-live="polite"`
    on the live text.
14. Verify the `ShieldCheck` icon in `ArbiterDeliberationOverlay` has `aria-hidden="true"`
    (finding F-6 below — flag if missing).
15. Verify `POST /api/v1/sessions/{session_id}/resume` fires with `{"deep_analysis": false}`.
16. Verify Groq is used for Arbiter synthesis (backend logs / monitoring).
17. Verify `PIPELINE_COMPLETE` then `FINAL_REPORT` WS messages arrive.
18. Verify navigation to `/result/{sid}` fires with the `data-fc-loading` bridge set first.

### Sub-phase C — Arbiter Status Polling Edge Cases

19. Monitor `GET /api/v1/sessions/{session_id}/arbiter-status` polling — verify exponential
    backoff (interval grows up to a 3000ms cap).
20. Simulate a `status: "unreachable"` response — verify the frontend falls back to WS
    reconnect rather than showing an error.
21. Simulate 5 consecutive `status: "not_found"` responses — verify an error is thrown and a
    destructive toast fires.

### Sub-phase D — Reject / Alternate Decision Path

22. Run a second investigation to the HITL pause.
23. Select a non-APPROVE decision (e.g. "TERMINATE") — verify `POST /api/v1/hitl/decision`
    fires with that decision.
24. Verify the pipeline halts — `PIPELINE_COMPLETE` or `ERROR` WS message follows.
25. Verify the UI handles the terminated state gracefully — not stuck on the HITL modal; shows
    an appropriate result or error state.
26. Repeat with "OVERRIDE" / "REDIRECT" and a custom note — verify the note field is included
    in the request body.

**Pass criteria:** HITL radiogroup keyboard-navigable; all decision variants fire correct API
calls; Arbiter overlay a11y correct; unreachable handled via WS fallback; termination handled
gracefully.

---

## CHECKPOINT 12 — Result Page: Full Design Audit (Initial Analysis)

Render-order audit, top to bottom — every section named and verified:

1. **Tab Navigation bar** — `role="tablist"`, two tabs (Analysis, History), `aria-selected`,
   `aria-controls`, roving tabindex; Arrow Left/Right switches tabs; tab icons have
   `aria-hidden`; the inactive tab panel has the `hidden` attribute (verify AT cannot reach
   hidden panel content).
2. **EvidenceHeader + EvidenceThumbnail** — filename, MIME type, pipeline start time, case ID
   all populated; thumbnail shows for images, file-type icon for audio/video.
3. **VerdictSection** — `<section>` with `<h2>` verdict label; verdict badge color matches the
   verdict type; confidence percentage shown numerically. **Findings F-1, F-2, F-3 apply
   here** — verify and fix during this checkpoint.
4. **ArcGauge** — `role="meter"`, `aria-valuemin=0`, `aria-valuemax=100`,
   `aria-valuenow={clampedValue}`, SVG `role="img"` with `aria-labelledby`, `<title>` set to
   "Confidence score: X%". **Findings F-4, F-5 apply here** — the outer dashed ring uses
   `animate={{ rotate: 360 }}` (confirmed at `ArcGauge.tsx:121`) and `useAnimatedValue` uses a
   raw `requestAnimationFrame` loop (confirmed at `ArcGauge.tsx:6-27`) with no
   `prefers-reduced-motion` check.
5. **AgentsStrip** — all fired agents shown as badges; skipped agents absent or visually
   differentiated; color is not the only differentiator (badge labels present).
6. **DegradationBanner** — must NOT appear in a clean run; verify it is driven by
   `report.degradation_flags` length, not hardcoded.
7. **KeyFindings** — all findings populated, each with text and severity; none display raw
   JSON or `[object Object]`.
8. **AgentAnalysisTab** — `<section aria-label="Agent analysis findings">`, `<h2>Agent
   Findings</h2>`; per-agent `AgentFindingCard` expands to tool-level findings; `initialFindings`
   and `deepFindings` filtered correctly per phase.
9. **AgentFindingSubComponents** — sub-findings show tool name, confidence, result text; no
   `undefined`/`null` displayed.
10. **DeepModelTelemetry** — model names and inference times visible; only appears for the
    deep phase or when telemetry data exists.
11. **FindingsMetadata** — evidence hash, case ID, investigator ID, chain-of-custody refs all
    populated.
12. **ExecutionTimeline / TimelineTab** — agent execution order correct; start/end times
    present; visual timeline renders.
13. **ReportIntegrity** — report signature present; signing timestamp non-null; integrity hash
    is a valid SHA-256 hex string.
14. **ReportFooter** — forensic disclaimer text and version number present.
15. **PageNavigation** — "New Analysis" and "Back to Home" buttons. **Finding F-9 applies.**
16. **ExportDropdown / ActionDock** — dropdown trigger keyboard-accessible; items reachable by
    Tab; closes on Escape; no focus trap inside the dropdown.

Global result-page a11y:

17. Heading hierarchy: an `<h1>` must exist on the result page; `<h2>` per section; no skipped
    levels.
18. Run a Lighthouse accessibility audit on the result page — score ≥ 90.
19. Verify color contrast of all text against the actual rendered background — especially the
    `VerdictSection`, where colored text sits on a semi-transparent gradient.
20. Verify `ConfidencePill` in agent cards uses color + numeric percentage. **Finding F-11
    applies.**

**Pass criteria:** All 16 sections populated with real data; no undefined fields; heading
hierarchy intact; Lighthouse ≥ 90; all flagged findings fixed in-place during this checkpoint.

---

## CHECKPOINT 13 — History Panel: Design & Functional Audit

Steps:

1. Switch to the "History" tab — verify `role="tabpanel"` with `id="tabpanel-history"` and
   `aria-labelledby="tab-history"`.
2. ui-ux-pro-max audit: panel layout, history item cards, verdict badge color, confidence
   pill, timestamp, file-type icon.
3. Verify the completed investigation appears with correct filename, verdict, timestamp, case
   ID, and file-type icon.
4. Thumbnail a11y: for image/video items with a thumbnail, verify `<img src={thumbnail}
   alt={fileName}>` — `alt` is the filename (not empty, not "thumbnail").
5. Icon-fallback a11y: for audio/doc items with no thumbnail, verify the fallback `<div>` +
   icon has either `role="img"` + `aria-label` or `aria-hidden` on the icon plus adjacent
   accessible text. **Finding F-8 applies** — flag if there is no text alternative.
6. `ConfidencePill` a11y: the percentage number is accessible; color is supplemental.
7. Verify the "Current" badge appears on the original session when browsing history from a
   result page.
8. Click a history item — verify navigation to `/result/{sessionId}` and that the result loads
   for that session.
9. Select one history item via its checkbox — verify "Clear selected" removes only that item.
10. Select multiple items — verify "Clear selected" removes all selected.
11. Click "Clear all" — verify all history is cleared and the empty state renders.
12. Verify the empty-state design: meaningful message, no orphaned UI, no blank space.
13. Verify history persists through a page refresh (reads from `persistentStorage` /
    `localStorage`).
14. A11y: history item action buttons (select, navigate, delete) are keyboard-reachable with
    descriptive `aria-label` values.

**Pass criteria:** History records correctly; all CRUD operations work; thumbnail/icon a11y
correct; persists through refresh.

---

## CHECKPOINT 14 — Export Buttons & Navigation

Steps:

1. **JSON export:** open the export dropdown → "Download JSON" — verify
   `GET /api/v1/sessions/{session_id}/report/download` fires, the response has
   `Content-Disposition: attachment`, and the file downloads as valid JSON with the full
   `ReportDTO`.
2. **PDF export via ActionDock:** click "Export" in the fixed bottom dock — verify
   `GET /api/v1/sessions/{session_id}/report/pdf` fires.
3. If WeasyPrint is available: the PDF downloads as `forensic-report-{sid[:8]}.pdf`.
4. If WeasyPrint is unavailable: `toast.warning` fires with a "Downloading the report as JSON
   instead." message and JSON actually downloads — the user is never silently handed the wrong
   file type.
5. Verify `ActionDock` is fixed `bottom-0` and does not overlap result-page content at 1280px
   and 375px.
6. Verify `ActionDock` respects `safe-area-inset-bottom` for notched mobile screens.
7. `ActionDock` a11y: `HomeIcon`, `Plus`, `Download` icons inside buttons — verify each button
   has an `aria-label`. **Finding F-10 applies** (icons missing `aria-hidden`; non-blocking
   because AT reads the label).
8. Verify the export button's `aria-label` toggles to "Exporting report…" during export and
   reverts to "Export report" after.
9. `PageNavigation` a11y — same icon flag (F-9); buttons have visible text so it is minor.
10. `RouteExperience` popstate: on the result page, scroll down significantly → click Back →
    Forward — verify scroll position is restored, not reset to top.
11. "New Analysis" from the result page: verify it sets `FC_NO_RECONNECT` and
    `FC_OPEN_UPLOAD_ONCE`, pushes to `/?upload=1`, and the upload modal auto-opens on landing.
12. "Back to Home" from the result page: verify navigation to `/`, the landing page loads
    cleanly, and no stale session state is visible.

**Pass criteria:** Both export formats work (PDF or graceful JSON fallback); `ActionDock`
layout correct; scroll position preserved on popstate; "New Analysis" resets cleanly.

---

## CHECKPOINT 15 — Deep Analysis: Full Pipeline & Result Page

### Sub-phase A — Trigger

1. At the HITL checkpoint, select a non-APPROVE decision and proceed, OR use the deep-analysis
   button in `AgentProgressDisplay`.
2. Verify `POST /api/v1/sessions/{session_id}/resume` fires with `{"deep_analysis": true}`.
3. Verify `storage.setItem(IS_DEEP, "true")`.
4. Verify `clearCompletedAgents()` fires — agent cards reset to their initial state for the
   deep pass.
5. Verify `setPhase("deep")` — the heading changes to "Deep Analysis" with a "Phase 2" badge.

### Sub-phase B — Deep Pipeline Verification

6. Verify agents re-fire with extended tool passes (more tools or deeper model parameters than
   the initial analysis).
7. Verify `AGENT_COMPLETE` fires for each agent with deep-phase findings.
8. Verify deep-phase agent cards show `phase === "deep"` styling (if any differentiation
   exists).
9. Verify `PIPELINE_COMPLETE` arrives and the "View Report" + "New Analysis" buttons appear.
10. Verify clicking "View Report" calls `handleViewResults` → `waitForFinalReport`, which polls
    `arbiter-status` with exponential backoff for up to 600,000ms (10 min).
11. Verify `ArbiterDeliberationOverlay` shows during the `waitForFinalReport` polling — this is
    the deep path, distinct from the initial-analysis arbiter overlay via `handleAcceptAnalysis`.
12. Verify the `data-fc-loading` bridge is set before `router.push` to the result page.

### Sub-phase C — Deep Analysis Result Page

13. Navigate to the result page — verify `isDeepPhase` is true.
14. Re-audit all 16 result-page sections from CP12 with deep-analysis data.
15. Verify `DeepModelTelemetry` shows extended model data (additional models, longer inference
    times vs the initial run).
16. Verify the Arbiter summary is a deeper synthesis — references more tools/agents than the
    initial summary.
17. Verify `per_agent_findings` contains both initial and deep findings per agent, filtered
    correctly in `AgentAnalysisTab` (`analysis_phase === "deep"` for deep findings).
18. Test both JSON and PDF export on the deep-analysis result.
19. Verify the history panel reflects the deep-analysis session correctly.

**Pass criteria:** Deep analysis triggers correctly; agent cards reset and re-run;
`waitForFinalReport` polls correctly; the result page shows richer data than the initial run;
both exports work.

---

## CHECKPOINT 16 — Final End-to-End Integrity Pass

### Sub-phase A — Clean Full Run

1. Open a fresh incognito window → `http://localhost:3000`.
2. Complete the full journey with no interventions: Landing → CTA → Upload (JPEG) → Success
   Modal → Begin Investigation → Evidence page → full initial analysis → HITL Accept → Arbiter
   overlay → Result page.
3. Time each phase: upload < 2s, initial analysis 30–120s, Arbiter synthesis < 15s — flag
   anything outside range.
4. Zero console errors or warnings throughout.
5. `GET /api/v1/sessions/{session_id}/quota` — verify token usage is logged and `degraded:
   false`.

### Sub-phase B — Keyboard-Only Navigation (a11y)

6. Repeat the entire flow with no mouse — keyboard only.
7. Landing: Tab to CTA → Enter to open the modal.
8. Upload modal: Tab to dropzone → Enter to open the file picker → select a file → Tab to
   "Begin Investigation" → Enter.
9. Evidence page: Tab through accordion controls → Enter to expand → Tab to decision buttons →
   Enter to accept.
10. HITL modal: Tab to the decision grid → Arrow keys to select APPROVE → Tab to the textarea
    → Tab to Finalize → Enter.
11. Result page: Tab through all sections, operate accordions (`AgentFindingCard`), Arrow keys
    between tabs, Tab to the export dropdown and operate it with the keyboard.
12. Document every point where focus is lost, stuck, or ambiguous — each is a blocking finding.

### Sub-phase C — Screen Reader (NVDA) Spot Checks (a11y)

13. With NVDA / Narrator, navigate the landing page — headings announced with levels; skip
    link announced on Tab.
14. Open the upload modal — "Upload Evidence" dialog title announced on open.
15. During analysis — `aria-live="polite"` pipeline status updates announced without being
    excessively noisy.
16. At the HITL modal — "Protocol Selection" radiogroup label announced; each radio option's
    label and description read on selection; `role="alert"` validation error announced
    immediately.
17. On the result page — `role="meter"` on `ArcGauge` announces "Confidence score: X%"; "Agent
    Findings" section heading announced; tab switching announces `aria-selected`.

### Sub-phase D — Reduced Motion OS-level Test (a11y)

18. Enable "Reduce motion" in the OS accessibility settings.
19. Hard-reload `http://localhost:3000` — verify no CSS animations on `AgentsSection` spin
    rings, no entrance animations on landing sections.
20. Run a full analysis — verify the `LoadingOverlay` pulsing dot is static, the
    `ArbiterDeliberationOverlay` progress bar is static, all Framer Motion animations
    suppressed.
21. Explicitly verify `ArcGauge`'s `useAnimatedValue` counter — it uses a raw
    `requestAnimationFrame` loop with no `prefers-reduced-motion` check (confirmed in source);
    confirm whether the number still animates under reduced motion and fix per finding F-5.
22. Verify the `GlobalNavbar` scroll-hide/show animation is disabled under reduced motion.

### Sub-phase E — Mobile Responsive

23. Set the viewport to 375px wide (iPhone SE).
24. Landing page: hero text does not overflow; CTA full-width; `AgentsSection` cards stack.
25. Upload modal: fills the viewport width; dropzone usable; close button reachable.
26. Evidence page: agent card grid collapses to a single column; accordion panels readable.
27. Result page: `VerdictSection` metric strip wraps/stacks at 375px (confidence % is hidden on
    `sm:block` — verify it is still in the accessible DOM); `ActionDock` respects
    `safe-area-inset-bottom`; tabs fit without overflow.

### Sub-phase F — Design Cohesion Cross-Screen

28. Full-page screenshots of: Landing, Evidence (mid-analysis), Evidence (HITL modal),
    `ArbiterDeliberationOverlay`, Result page (initial), Result page (deep).
29. Final ui-ux-pro-max pass across all six screens — verify consistent font tokens, color
    palette, glassmorphism treatment, border radii, spacing scale, and focus-ring style.

**Pass criteria:** Full journey completes without errors; keyboard-only run has zero focus-loss
points; NVDA announces all critical state transitions; reduced motion disables all animations
(including the `ArcGauge` counter once F-5 is fixed); mobile layout intact; design cohesive
across all screens.

---

## CHECKPOINT 17 — Error Pages & Global Error Boundary

**Goal:** Verify every error surface renders cleanly and recovers.

Steps:

1. Force a render error on the landing page — verify `app/error.tsx` renders with a heading, a
   "Try again" reset action, and no raw stack trace shown to the user.
2. Force an error on `/evidence` — verify `app/evidence/error.tsx` renders the route-scoped
   boundary, not the global one.
3. Force an error on `/result/{sid}` — verify `app/result/error.tsx` renders.
4. Trigger a top-level failure — verify `app/global-error.tsx` renders (it replaces the entire
   document, so confirm it carries its own `<html>`/`<body>`).
5. ui-ux-pro-max audit of each error page: consistent glassmorphism, danger accent, button
   styling matching the rest of the app.
6. A11y on each error page: an `<h1>` is present; the reset/retry button has a clear label and
   is keyboard-operable; decorative icons have `aria-hidden`.
7. Verify the reset action actually recovers (re-renders the route) rather than just reloading.

**Pass criteria:** All four error boundaries render cleanly; reset recovers; no raw stack
traces; a11y intact.

---

## CHECKPOINT 18 — Cross-Browser & Responsive Layout

**Goal:** Confirm layout integrity beyond the primary test browser.

Steps:

1. Run the golden path (CP16 Sub-phase A) in Chromium, Firefox, and WebKit/Safari.
2. At each of 375px / 768px / 1280px, screenshot Landing, Evidence, and Result and compare
   against the Chromium baseline — flag layout breaks, overflow, or font-rendering differences.
3. Verify the WebSocket connects in all three browsers (subprotocol negotiation can differ).
4. Verify file upload via drag-drop and via the native picker in all three.
5. Verify backdrop-blur degrades gracefully where unsupported.

**Pass criteria:** Golden path completes in all three browsers; no layout breaks at any
breakpoint; WebSocket and upload work everywhere.

---

## CHECKPOINT 19 — Performance & Reduced Motion Final Pass

Steps:

1. Run a Lighthouse Performance audit on `/` and on a populated result page — record LCP, CLS,
   TBT; flag CLS > 0.1 or LCP > 2.5s.
2. Verify `LandingBackground` and all overlays cause no measurable layout shift (CLS
   contribution ≈ 0).
3. Verify code-split boundaries: the result/evidence bundles are not pulled into the landing
   page's initial JS.
4. Verify images use appropriate formats and the thumbnail capture does not block the main
   thread noticeably.
5. Re-run the full reduced-motion sweep from CP16 Sub-phase D as a final confirmation after all
   F-4 / F-5 fixes are in place.

**Pass criteria:** Lighthouse Performance documented; CLS ≤ 0.1; no animation leaks under
reduced motion.

---

## CHECKPOINT 20 — Full Golden-Path Regression

**Goal:** A single uninterrupted end-to-end run confirming no checkpoint fix introduced a
regression elsewhere.

Steps:

1. Fresh incognito window — run the complete journey: Landing → upload → evidence → initial
   analysis → HITL → arbiter → result → export → history → deep analysis → result → export.
2. Zero console errors or warnings at any point.
3. **`[v2 NEW]` Run the existing automated suites as the regression backstop:**
   - `cd apps/web && npx playwright test` — run `full_journey.spec.ts`,
     `browser_journey.spec.ts`, `upload-route-flow.spec.ts`, `storage-isolation.spec.ts`,
     `accessibility.spec.ts`. All must pass.
   - `full_journey.live.spec.ts` should be run against the live stack as the live-mode
     confirmation.
   - Run the component a11y tests under `apps/web/tests/accessibility/`
     (`accessibility.test.tsx`, `pages.test.tsx`, `hitl_completion.test.tsx`).
4. Confirm every finding F-1 through F-11 is resolved and the relevant automated test (or a
   manual re-check) confirms it.

**Pass criteria:** Full manual journey completes cleanly; the entire Playwright e2e suite and
the component a11y suite pass; all 11 findings resolved.

---

## CHECKPOINT 21 — Gitignore Tightening

Steps:

1. Review `.gitignore` — confirm it excludes build artifacts, `node_modules`, `.next`,
   coverage and test artifacts, `/exports/`, `/downloads/`, `/reports/`, and the session-local
   audit plan files (`FULL_APP_AUDIT.md`, `end to end audit plan.md`).
2. Run `git status --ignored` — verify no secret, key, evidence, or generated file is tracked
   that should be ignored.
3. Confirm `storage/keys/` and any signing-key material are ignored and not committed.
4. Confirm `storage/evidence/` sample data and `apps/web/jest-results.json` are ignored.
5. Verify `.dockerignore` excludes the same noise from build contexts (it should mirror the
   relevant entries so build contexts stay small).

**Pass criteria:** No artifact, secret, key, or generated file is tracked; `.gitignore` and
`.dockerignore` are consistent.

---

## CHECKPOINT 22 — Project Cleanup

Steps:

1. **`[v2 NEW]` Remove the stray temp file** `apps/api/get_session_details_temp.py` — it is a
   leftover scratch script sitting at the API package root and is not imported anywhere.
   Confirm with `grep -r get_session_details_temp apps/` that nothing references it, then
   delete it.
2. Scan for other `*_temp.*`, `*.bak`, `scratch.*`, `TODO.txt`, and commented-out dead-code
   blocks across `apps/api` and `apps/web` — remove or resolve.
3. Verify `storage/evidence/` contains no committed real evidence fixtures beyond the intended
   `.gitkeep` / `incoming` placeholders.
4. Confirm there are no duplicate or unused components in `apps/web/src/components` (cross-check
   each file is imported somewhere).
5. Verify the docs in `/docs` have no stale references to removed files; check
   `DOCUMENTATION_INVENTORY.md` matches the actual file set.

**Pass criteria:** `get_session_details_temp.py` deleted; no stray scratch files; no
committed real evidence; no dead components; docs inventory accurate.

---

## CHECKPOINT 23 — Docker Dev + Prod Build Workflow

Steps:

1. From a clean state, `docker compose -f infra/docker-compose.yml up --build` — verify all
   services reach a healthy state: `redis`, `qdrant`, `postgres`, `jaeger`, `migration`
   (exits 0), `backend`, `worker`, `caddy`, `frontend`, `prometheus`.
2. Verify the `migration` container runs `alembic upgrade head` then `init_db.py` and exits
   cleanly (it must NOT fall back to a bare `init_db.py`, which would bypass migrations).
3. **`[v2 CORRECTION]` Verify the schema after migration.** The original plan checked for
   `sessions` and `investigation_checkpoints` tables — those names are wrong. The real schema
   (`alembic/versions/0001_initial_schema.py`) creates: `users`, `session_reports`,
   `investigation_state`, `user_sessions`, `audit_log`, `chain_of_custody`,
   `evidence_artifacts`, and `hitl_checkpoints`. Verify connectivity and spot-check the real
   tables:
   - `docker compose exec backend python -c "import asyncio; from core.persistence.postgres_client import get_postgres_client; asyncio.run(get_postgres_client())"` — connects cleanly.
   - `docker compose exec postgres psql -U forensic_user -d forensic_council -c "\dt"` — confirm
     all eight tables above are present.
4. Run the dev overlay: `docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up`
   — verify hot-reload works (the frontend uses `WATCHPACK_POLLING`; the backend uses
   `WATCHFILES_FORCE_POLLING`) and host-side ports are exposed per the dev overlay.
5. Run the prod overlay: `docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml up --build`
   — verify the frontend builds the `runner` target (not `development`) and the backend runs
   in production mode. Confirm the "you forgot the prod overlay" banner does NOT appear.
6. **`[v2 NEW]` Observability verification:**
   - Open `http://localhost:9090` (Prometheus) → Status → Targets — verify the `forensic_api`
     scrape target (`backend:8000`, metrics path `/api/v1/metrics/raw`) shows **UP**.
   - Open `http://localhost:16686` (Jaeger) — after one full investigation run, verify at
     least one trace appears for `forensic_api` / `forensic_worker`.
7. Verify the worker container's healthcheck (`scripts/worker_healthcheck.py`) reports healthy
   and that `forensic:worker:heartbeat` exists in Redis.
8. Verify Caddy reverse-proxies the frontend and API correctly (the app is reachable through
   Caddy, not only via the direct container ports).
9. Verify `infra/validate_production_readiness.sh` passes against the prod overlay.

**Pass criteria:** All services healthy; migration applies the real schema and exits 0; the
eight expected tables exist; dev hot-reload works; prod overlay builds the `runner` target;
Prometheus target UP; Jaeger shows traces; worker heartbeat present; Caddy routes correctly;
the readiness script passes.

---

## CHECKPOINT 24 — Documentation Verification

Steps:

1. Verify `README.md` setup steps work end-to-end on a clean checkout.
2. Verify `infra/DOCKER_BUILD.md` and `infra/README.md` match the actual compose files and the
   CP23 workflow above.
3. Verify `docs/API_CONTRACT.md` matches the live route surface — every route confirmed in the
   codebase (`/api/v1/auth/{login,refresh,logout,me}`, `/api/v1/investigate`,
   `/api/v1/sessions/...`, `/api/v1/hitl/decision`, `/api/v1/sessions/{id}/checkpoints`,
   `/api/v1/sessions/{id}/arbiter-status`, `/api/v1/sessions/{id}/resume`,
   `/api/v1/sessions/{id}/report/{download,pdf}`, `/api/v1/sessions/{id}/progress` SSE,
   `WS /api/v1/sessions/{id}/live`, `/api/v1/metrics/{public,raw,prometheus}`,
   `/health`, `/live`, `/api/v1/health/{ml-tools,tools}`).
4. Verify `docs/AGENT_CAPABILITIES.md` matches the tool sets verified in CP10.
5. Verify `docs/AI_CONTEXT.md`, `docs/ARCHITECTURE.md`, and `docs/COMPONENTS.md` reflect the
   current component inventory after the CP22 cleanup.
6. Verify `docs/PRODUCTION_CHECKLIST.md` and `docs/OPERATIONAL_RUNBOOK.md` reference real
   commands (no Celery commands — the worker is the custom Redis-queue consumer).
7. Verify `docs/CHANGELOG.md` has an entry for this audit pass.
8. Verify `DOCUMENTATION_INVENTORY.md` lists every doc file and nothing stale.

**Pass criteria:** All docs match the live codebase; setup steps work on a clean checkout; no
references to non-existent commands, routes, or files.

---

## CHECKPOINT 25 — Automated Test Suite Health *(`[v2 NEW]`)*

**Goal:** The repository already ships a substantial automated suite — it was never referenced
in the original plan. A live audit that ignores it leaves the project's own regression net
unverified. This checkpoint confirms the suite is green so future changes are protected.

Steps:

1. **Backend tests** — `cd apps/api && pytest` across the existing suites: `tests/unit`,
   `tests/integration`, `tests/contracts`, `tests/security`, `tests/system`, `tests/infra`.
   Record pass/fail counts; every failure is a finding.
2. **Frontend unit/integration** — `cd apps/web && npm test` (Vitest/Jest) across
   `tests/unit` and `tests/integration`.
3. **Frontend e2e** — `cd apps/web && npx playwright test` using `playwright.config.ts`:
   `full_journey.spec.ts`, `full_journey_phase7.spec.ts`, `browser_journey.spec.ts`,
   `upload-route-flow.spec.ts`, `storage-isolation.spec.ts`, `accessibility.spec.ts`.
4. **Live e2e** — run `full_journey.live.spec.ts` against the running stack.
5. **Contract tests** — confirm `tests/contracts` still matches `docs/API_CONTRACT.md` after
   any route touched during the audit.
6. **Load tests** — optionally run `tests/load` to confirm no obvious regression in throughput
   under concurrent investigations.
7. For any test that is skipped, xfail-ed, or flaky, document why — a silently skipped test is
   a finding.

**Pass criteria:** All backend and frontend suites green (or every exception explicitly
justified); the Playwright e2e suite passes against the live stack; contract tests match the
documented API surface.

---

## Consolidated Findings (Defects Found During Code Reading — Fix In-Place During Audit)

These were identified by reading the source. Each is fixed surgically during the checkpoint
noted, then verified.

| # | Component | Finding | Severity | Fix during |
|---|---|---|---|---|
| F-1 | `VerdictSection` | `VerdictIcon` and three `MetricCell` icons missing `aria-hidden="true"` | Minor | CP12 |
| F-2 | `VerdictSection` | `MetricCell` progress bars missing `role="progressbar"`, `aria-valuenow/min/max` | Moderate | CP12 |
| F-3 | `VerdictSection` | Color alone conveys severity in metric bars (WCAG 1.4.1) | Moderate | CP12 |
| F-4 | `ArcGauge` | Outer dashed ring uses Framer Motion `animate={{ rotate: 360 }}` (`ArcGauge.tsx:121`) — violates the CSS-spin rule | Minor | CP12 |
| F-5 | `ArcGauge` | `useAnimatedValue` RAF loop (`ArcGauge.tsx:6-27`) has no `prefers-reduced-motion` check — the counter animates even under reduced motion | Moderate | CP12 / CP16-D |
| F-6 | `ArbiterDeliberationOverlay` | `ShieldCheck` icon missing `aria-hidden="true"` | Minor | CP11 |
| F-7 | `LoadingOverlay` | Animated progress bar `<motion.div>` missing `role="progressbar"` attrs — mark `aria-hidden="true"` (decorative) | Moderate | CP8 |
| F-8 | `HistoryPanel` | Icon fallback for non-thumbnail items (`<div>` + icon) has no text alternative | Moderate | CP13 |
| F-9 | `PageNavigation` | `Plus` and `Home` icons missing `aria-hidden` (buttons have visible text — non-blocking) | Minor | CP12 / CP14 |
| F-10 | `ActionDock` | `HomeIcon`, `Plus`, `Download` icons missing `aria-hidden` (buttons have `aria-label` — non-blocking) | Minor | CP14 |
| F-11 | `ConfidencePill` | Color-only confidence encoding — the percentage number mitigates it but there is no supplemental text label | Minor | CP12 / CP13 |

---

## Execution Order & Tool Assignment

Each checkpoint must fully pass before the next begins. Findings are fixed in-place during the
relevant checkpoint — no debt list.

| Checkpoints | Primary tools |
|---|---|
| 0, 23 | Bash (curl / `docker compose` / `psql` / `redis`) |
| 0.5, 1, 1.5, 1.6, 3, 7, 8.5, 9, 17, 18 | live browser verification |
| 2, 4, 6, 8, 9, 11, 12, 13, 14, 15, 16, 17 | ui-ux-pro-max design audit + live browser |
| 10, 10.5, 11, 14 | Bash (API calls) + live browser |
| 16-C, 16-D | NVDA / Windows Narrator + OS reduced-motion |
| 19 | Lighthouse / DevTools Performance |
| 20, 25 | Playwright + pytest + Vitest (automated suites) |
| 21, 22, 24 | Bash + source review |
| All | Source cross-reference whenever live behavior is ambiguous |

---

## Coverage Summary

The 27 checkpoints (0, 0.5, 1, 1.5, 1.6, 2–25) cover the full application surface end-to-end:
infrastructure and auth round-trip; global a11y scaffold; cold load, refresh, and direct-nav
edge cases; session reconnect and expired-session handling; the landing page; the full CTA →
modal → upload → evidence flow; the loading overlay and its safety timeout; WebSocket failure
and retry; the evidence page and agent pipeline across image / audio / video; toast paths;
the HITL decision UI and arbiter deliberation; the result page section-by-section; deep
analysis; history; export; error boundaries; cross-browser and responsive layout; performance
and reduced motion; the full golden-path regression; gitignore; project cleanup; the Docker
dev/prod workflow with observability; documentation; and the existing automated test suite.

When every checkpoint reaches its pass criteria — including the v2 corrections to CP0 (worker
healthcheck), CP23 (real schema tables), CP22 (stray-file removal), and CP25 (automated suite)
— the application can be considered fully audited and production-ready.

---

## Before You Begin — Create the Live Tracking File

Create a file named `AUDIT_PROGRESS.md` at the repo root with one row per checkpoint
(0, 0.5, 1, 1.5, 1.6, 2–25), columns: `Checkpoint | Status | Findings opened | Findings fixed
| Notes`. Update it as each checkpoint closes. It is already covered by `.gitignore`'s
session-local audit-plan exclusion pattern, so confirm it will not be committed.

Say **"start checkpoint 0"** to begin.

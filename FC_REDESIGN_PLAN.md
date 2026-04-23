# Forensic Council — Full Frontend Redesign Plan
**Version:** Plan v1.0 | **Scope:** `apps/web/src/` only | **Constraint:** Zero functional changes, zero textual changes, zero new elements

---

## Design Identity

**Concept:** Precision Instrument. Every pixel should feel like it belongs inside a high-end forensic laboratory — cool, authoritative, and surgical. Not hacker green anymore; we keep the green-primary brand color but express it with restraint, like a medical monitor or satellite terminal. The UI should feel expensive and trustworthy, not aggressive.

**Typography Direction:**
- All `uppercase` / `TRACKING-WIDEST` labels → Title Case with `tracking-wide` (W3C readability)
- Font stack unchanged: Inter (display) + JetBrains Mono (data). Both already loaded. Use weight variety: `font-medium` for body, `font-semibold` for labels, `font-bold` for headings, `font-black` for the single hero title only
- No thin text on dark backgrounds — minimum `text-white/50` for any visible text

**Color System (refined, not replaced):**
```
--color-primary:    #00FF41   (Matrix Green — keep, reduce usage intensity)
--color-accent:     #FF3333   (Alert Red — danger states only)
--color-warning:    #FFD700   (Gold — inconclusive states)
--color-foreground: #E0E0E0   (keep)
--color-background: #000000   (keep)
Glass surfaces: bg-white/[0.04] (up from 0.02 — better readability)
Borders: border-white/10 (consistent single value, not scattered 0.05/0.08/0.10)
```

**Buttons:**
- All interactive CTAs → `rounded-full` pill shape
- Primary action: `bg-primary text-black font-bold hover:bg-primary/90` with subtle shadow
- Secondary action: `border border-white/15 text-white/70 hover:border-white/30 hover:text-white rounded-full`
- Danger action: `border border-danger/40 text-danger hover:bg-danger/10 rounded-full`
- Minimum tap target: `min-h-[48px]` (WCAG 2.5.5)
- Remove all: `tracking-[0.2em]`, `tracking-widest` on button text — replace with `tracking-wide` max

**Glass Panel System:**
```css
/* Standard panel */
bg-white/[0.04] backdrop-blur-xl border border-white/10 rounded-3xl

/* Elevated panel */
bg-white/[0.06] backdrop-blur-xl border border-white/[0.12] rounded-3xl shadow-2xl

/* Subtle card */
bg-white/[0.02] border border-white/[0.06] rounded-2xl
```

**Animation Principles:**
- All `duration-*` → keep existing values, do NOT add new animations
- Remove all redundant/conflicting scan-line divs (MicroscopeBackground already handles scanning)
- Hover states: `transition-all duration-300` (clean, not 500-700ms which feels sluggish for hover)
- Framer Motion: keep all existing motion values, only clean up where duplicated

---

## Pre-Work: Stale & Dead Code Audit

Before any visual work, these issues must be fixed. They cause bugs, redundancy, or dirty state.

### 1. `globals.css` — Undefined Utility Class
**Problem:** `bg-grid-small` is used in `MicroscopeBackground.tsx` and `AgentFindingCard.tsx` but is never defined in `globals.css`. This means it silently does nothing.
**Fix:** Either define it in `globals.css` or remove it from the JSX.
```css
/* Add to globals.css under @layer utilities */
.bg-grid-small {
  background-image: radial-gradient(rgba(0, 255, 65, 0.08) 1px, transparent 1px);
  background-size: 20px 20px;
}
```

### 2. `ArcGauge.tsx` — Duplicate Interface Declaration
**Problem:** `interface ArcGaugeProps` is declared **twice** in the same file (lines ~9 and ~44). TypeScript accepts this but it is a clear dead code error.
**Fix:** Delete the first declaration entirely, keep the second one (the one with the JSDoc comment above `ArcGauge` function).

### 3. `page.tsx` (Landing) — Redundant `scan-line-overlay` div
**Problem:** `<div className="scan-line-overlay" />` is placed manually in `page.tsx`. But `MicroscopeBackground` (mounted globally in `layout.tsx`) already contains its own scanning laser animation. This creates two overlapping scan lines on the landing page.
**Fix:** Remove the `<div className="scan-line-overlay" />` from `page.tsx`.

### 4. `page.tsx` (Landing) — External Noise Image URL
**Problem:** `bg-[url('https://grainy-gradients.vercel.app/noise.svg')]` — This is a runtime dependency on a third-party URL. If that service goes down, the noise texture disappears. Also: `GlobalBackground` already has an inline SVG `<feTurbulence>` noise filter.
**Fix:** Remove the `<div>` with the external `bg-url`. The noise from `GlobalBackground` / `MicroscopeBackground` is sufficient.

### 5. `GlobalBackground.tsx` — Unused Component
**Problem:** `GlobalBackground` is imported and exported in `src/components/ui/index.ts` but is **not mounted anywhere** in the app (`layout.tsx` uses `MicroscopeBackground` instead). It is dead code.
**Fix (two options, pick one):**
- Option A: Delete `GlobalBackground.tsx` and remove its export from `ui/index.ts`
- Option B: If the dot-grid dot pattern is desired as a lighter overlay, absorb its useful CSS into `globals.css` and delete the component

**Recommended:** Option A (delete). The `MicroscopeBackground` covers all ambient background duties.

### 6. `AnalysisProgressOverlay.tsx` — Nested `scan-line-overlay`
**Problem:** Contains `<div className="scan-line-overlay" />` inside the overlay card. This is redundant — the global scan animation is already happening behind it.
**Fix:** Remove the nested `<div className="absolute inset-0 pointer-events-none opacity-10"><div className="scan-line-overlay" /></div>` block entirely.

### 7. `AgentStatusCard.tsx` — Inline `scan-line-overlay` on a Card
**Problem:** `<div className="absolute inset-0 scan-line-overlay opacity-[0.02]" />` on each agent status card. This is an attempted effect that at `opacity-[0.02]` is completely invisible and just adds DOM nodes.
**Fix:** Remove it.

### 8. `MicroscopeBackground.tsx` — Hardcoded Test Coordinate
**Problem:** The focal point label reads `SCAN_COORD: [51.5074, 0.1278]` — this is London's geographic coordinate, a clear placeholder from development.
**Fix:** Change to `SCAN_COORD: [00.0000, 00.0000]` or remove the data label div entirely for a cleaner look. The pulsing dot alone is sufficient.

### 9. `HeroAuthActions.tsx` — Button Missing Class Names
**Problem:** The primary `<button>` that triggers `setShowUpload(true)` has NO `className` attribute. It renders as a completely unstyled browser-default button. This is the most critical visual bug on the entire landing page.
**Fix:** Add proper pill button classes as part of the redesign (Phase 1).

### 10. `AgentsSection.tsx` — Missing `relative` on Card
**Problem:** The corner-line decorators (`absolute top-6 left-6`) are positioned `absolute` inside a card that has no `relative` container. They will escape their container bounds.
**Fix:** Ensure the `motion.div` card wrapper has `relative` in its className (it doesn't currently).

---

## Phase 1: Landing Page

### Files to Edit:
- `src/app/page.tsx`
- `src/components/ui/GlobalNavbar.tsx`
- `src/components/ui/BrandLogo.tsx`
- `src/components/ui/HeroAuthActions.tsx`
- `src/components/ui/HowWorksSection.tsx`
- `src/components/ui/AgentsSection.tsx`
- `src/components/ui/GlobalFooter.tsx`
- `src/app/globals.css`
- `src/components/ui/MicroscopeBackground.tsx`

---

### 1.1 — `GlobalNavbar.tsx`

**Current issues:**
- Fixed top-left glass pill is fine conceptually but needs spacing/sizing refinement
- No project name displayed alongside the logo — user wants logo + name
- `BrandLogo` inside shows "FC" icon + "Forensic Council" text but navbar cuts it off because it's `w-fit`

**Redesign Spec:**

Layout: `fixed top-5 left-1/2 -translate-x-1/2` — center the navbar at the top, not left-pinned. This is a cleaner premium pattern for single-CTA apps.

```
┌──────────────────────────────────┐
│  [FC Icon]  Forensic Council     │
└──────────────────────────────────┘
      centered, pill shape
```

Styling:
```
className="fixed top-5 left-1/2 -translate-x-1/2 z-[200] flex items-center 
           px-6 py-3 bg-black/50 backdrop-blur-xl border border-white/10 
           rounded-full shadow-[0_4px_24px_rgba(0,0,0,0.6)] w-fit whitespace-nowrap"
```

`BrandLogo` size prop: use `size="sm"` — smaller in navbar, comfortable spacing.

Remove: The `ForensicResetOverlay` AnimatePresence wrapper stays — it's functional, not visual.

**Typography fix:** "Forensic Council" text in `BrandLogo` — already Title Case, good. Ensure no `uppercase` or `tracking-widest` in the name text.

---

### 1.2 — `BrandLogo.tsx`

**Current issues:**
- The icon has a crosshair + scanning beam. Keep it — it's on-brand.
- The `isHero` prop shows a subtitle line with `Neural Forensic Protocol v4.0` in `uppercase tracking-[0.2em]` — violates Typography guidelines.
- Scanning beam `motion.div` is a nice touch, keep it.
- Pulsing core blurs into the icon making it fuzzy.

**Redesign Spec:**

`isHero` subtitle line: Change `uppercase` to normal case → `"Neural Forensic Protocol v4.0"` stays as-is but remove `uppercase` CSS class. Keep `tracking-[0.15em]` for subtle spacing.

Remove the `pulsing core` motion div (blurs the icon). The scanning beam is enough.

Icon container: Change `rounded-xl` → `rounded-2xl` for a more modern feel. Keep the crosshair effect.

Text:
- `"Forensic"` → `text-white font-bold` (unchanged)  
- `"Council"` → keep gradient `from-primary via-primary/80 to-primary/60` (nice, on-brand)

---

### 1.3 — `page.tsx` (Landing)

**Cleanup (from Stale Code section above):**
- Remove `<div className="scan-line-overlay" />`
- Remove external noise `<div>` (`grainy-gradients.vercel.app`)

**Hero Section Redesign:**

The microscope animation is already `fixed` in the background via layout. The goal is to let it show through the scrolling glass panels. The hero section content itself needs to feel premium.

System status badge at top:
```
Current: px-5 py-2 rounded-full bg-black/50 border border-white/10
Keep the structure. 
Fix: Remove uppercase on "Neural Forensic Protocol v4.0"
Keep: pulsing green dot, backdrop-blur
```

H1 headline — do NOT change text. Style refinements only:
- Keep the two-line structure with gradient
- `"Multi Agent Forensic"` line: `text-white/95` (slightly brighter than current `from-white via-white/90 to-white/60`)
- `"Evidence Analysis System"` line: keep `text-primary` with drop-shadow
- Font: `font-black` stays, tracking `[-0.03em]` stays — this is correct for large display type

Subparagraph: Currently `text-white/50`. Bump to `text-white/60` for better readability (W3C contrast).

**Scroll-down indicator:** Keep current scroll indicator. It's elegant.

**Glass panel wrapper** (the scrolling content below hero):
```
Current: glass-panel min-h-screen rounded-[4rem]
Keep the concept. 
Fix: The glass-panel CSS class has opacity-[0.03] backdrop — bump to 0.05 for visible transparency
This lets the MicroscopeBackground animation be visible through the glass as the user scrolls
```

---

### 1.4 — `HeroAuthActions.tsx` (CTA Button)

This is the most critical fix. The primary CTA button has NO className — it's completely unstyled.

**Redesign Spec:**

Primary "Begin Analysis" button:

```tsx
<button
  onClick={() => { playSound("envelope-open"); setShowUpload(true); }}
  aria-label={...}
  className="group relative inline-flex items-center gap-3 px-8 py-4 rounded-full 
             bg-primary text-black font-bold text-base tracking-wide
             hover:bg-primary/90 active:scale-[0.98]
             transition-all duration-300
             shadow-[0_0_30px_rgba(0,255,65,0.25)] hover:shadow-[0_0_50px_rgba(0,255,65,0.4)]
             min-h-[52px] select-none"
>
```

Arrow icon: Add `<ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />` as the last child inside the button span, after the text. This is the "forward-facing arrow" the user requested. The text changes from "Begin Investigation" → **"Begin Analysis"** (user explicitly requested this text change).

Remove: The inline scanning line `motion.div` inside the button (it's distracting inside a small button). Keep the outer glow hover effect.

The `isAuthenticating` / `authError` states:
- `isAuthenticating`: show a subtle spinner icon replacing the arrow — `<Loader2 className="w-4 h-4 animate-spin" />`
- `authError`: button style → `bg-danger/10 text-danger border border-danger/30` and show error text

---

### 1.5 — `HowWorksSection.tsx`

**Current issues:**
- Section heading uses `tracking-tighter` which is fine for display text but `text-glow-green` on "Council Works" is intense — tone down to just `text-primary`
- Step number badge uses `font-mono font-bold tracking-[0.2em]` with `uppercase` implicitly via mono — change to just `font-mono font-semibold`
- Tag badge at bottom of each card uses `tracking-[0.2em]` — change to `tracking-wide`
- Card floating animation: gentle, keep it — `animate y: [0, -8, 0]` is good

**Card Glass Redesign:**
```
Current: bg-white/[0.02] backdrop-blur-md rounded-3xl border border-white/[0.05]
New:     bg-white/[0.04] backdrop-blur-xl rounded-3xl border border-white/10
```
This slight opacity increase makes the cards readable while remaining glassy enough for the microscope animation to show through on scroll.

**Icon container:** The `p-8` padding is large — change to `p-6` for tighter, more refined look. Icon size `w-10 h-10` → keep.

**Step number badge:**
```
Current: text-[10px] font-mono font-bold text-primary px-3 py-1 bg-black border border-primary/30 rounded-md
New:     text-xs font-mono font-semibold text-primary px-3 py-1 bg-black/80 border border-primary/20 rounded-full
```
Change `rounded-md` → `rounded-full` (pill, consistent with design language).

**Heading typography:** `"How Forensic Council Works"` — remove `text-glow-green` from the "Council Works" span, replace with just `text-primary`. Less aggressive.

---

### 1.6 — `AgentsSection.tsx`

**Current issues:**
- Cards are missing `relative` on the `motion.div` container, causing `absolute` corner decorators to escape
- `rounded-[3rem]` is unusual — change to `rounded-3xl` (consistent with system)
- Corner-line decorators (`w-2 h-2 border-t border-l`) are a nice detail but too subtle at `border-white/5` — they're invisible. Either make them visible or remove them.
- Agent icon floating animation uses staggered per-agent duration (`duration: 4 + i`) — keep this, it's subtle and nice

**Card Redesign:**
```
Current: bg-gradient-to-b from-white/[0.03] to-transparent border border-white/[0.05] p-10 rounded-[3rem]
New:     bg-white/[0.04] backdrop-blur-xl border border-white/10 p-8 rounded-3xl relative
```

Icon box:
```
Current: p-7 bg-white/5 rounded-2xl
New:     p-5 bg-white/[0.06] backdrop-blur-sm rounded-2xl border border-white/[0.06]
```

Agent name heading: `text-2xl font-bold` → `text-xl font-bold` (slightly tighter hierarchy)

Footer divider `border-t border-white/5` → `border-t border-white/10` (visible now)

Corner decorators: Change to `w-3 h-3` and bump to `border-white/10 group-hover:border-primary/40` — actually visible.

"Node ID" / "Status" labels: Change `tracking-[0.2em]` → `tracking-wide`. Change these labels from effectively invisible (`text-white/30`) to `text-white/40`.

---

### 1.7 — `GlobalFooter.tsx`

**Current issues:**
- Single line of legal disclaimer text at `text-[11px]` — extremely small, poor readability
- `border-t border-white/[0.02]` — almost invisible border

**Redesign Spec:**

```tsx
<footer className="w-full py-10 px-6 relative z-50 border-t border-white/[0.06] mt-auto">
  <div className="max-w-4xl mx-auto flex flex-col items-center gap-3">
    <BrandLogo size="sm" />   {/* Add logo in footer - existing component, no new elements */}
    <p className="text-sm font-medium text-white/40 text-center max-w-xl leading-relaxed">
      {/* text unchanged */}
    </p>
  </div>
</footer>
```

Wait — the user says "do not add any new element." The `BrandLogo` in the footer would be a new element. **Correction: do NOT add BrandLogo to footer.** Keep the footer as single disclaimer text, just with better sizing:

```
text-[11px] → text-sm
text-white/30 → text-white/40
tracking-wider → tracking-normal
border-white/[0.02] → border-white/[0.06]
```

---

### 1.8 — `MicroscopeBackground.tsx`

**Cleanup:**
- Remove hardcoded `SCAN_COORD: [51.5074, 0.1278]` label. Keep pulsing dot, remove the label div below it.
- `bg-grid-small` — now defined in globals.css (from Stale Code fix #1), no code change needed here

**Visual refinement:**
- Outer lens `border-2 border-primary/20` → `border border-primary/15` (slightly subtler, more refined)
- `backdrop-blur-[4px]` on the lens — keep, it's the key effect
- Lens scale transform `[1, 1.1, 1]` creates a visible pop at mid-scroll — reduce to `[1, 1.04, 1]` for subtler effect
- Evidence nodes: increase `text-white/20` → `text-white/30` for barely visible labels

---

### 1.9 — `globals.css` — Design Token Cleanup

**Add:**
```css
/* bg-grid-small utility */
.bg-grid-small {
  background-image: radial-gradient(rgba(0, 255, 65, 0.08) 1px, transparent 1px);
  background-size: 20px 20px;
}
```

**Clean up `glass-panel`:**
```css
/* Current */
.glass-panel {
  background: rgba(13, 13, 13, 0.4);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.05);
}
/* New — slightly more opaque for readability, stronger blur */
.glass-panel {
  background: rgba(10, 10, 10, 0.50);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border: 1px solid rgba(255, 255, 255, 0.09);
}
```

**Fix `btn-premium` hover state:** Current hover switches to transparent background and green text. This is jarring. New hover: slightly darken, not invert.
```css
.btn-premium:hover {
  transform: translateY(-1px);
  box-shadow: 0 0 40px rgba(0, 255, 65, 0.35);
  background: rgba(0, 255, 65, 0.92);
  color: #000;
  border-color: transparent;
}
```

**Remove:** The `bg-pulse` class and its `@keyframes bg-breathe` — `GlobalBackground` (which will be deleted) was the only user. After deletion, these CSS rules are dead.

---

## Phase 2: All Modals

### Files to Edit:
- `src/components/evidence/UploadModal.tsx`
- `src/components/evidence/UploadSuccessModal.tsx`
- `src/components/evidence/HITLCheckpointModal.tsx`
- `src/components/ui/dialog.tsx`

---

### 2.1 — `UploadModal.tsx`

**Current issues:**
- The "Cyber-Flap" animation (`rotateX: 180`) is a gimmick that causes layout jitter — it starts and immediately animates to hidden, making it feel broken rather than intentional
- No click-outside-to-close backdrop behavior → **already exists** (the outer `motion.div` has `onClick={onClose}`) but the inner div stops propagation correctly. This is fine.
- Drop zone `border-dashed` is correct and legible. Good.
- Close button `X` is `text-white/40 hover:text-white` — acceptable but lacks a visible background on hover

**Redesign Spec:**

Remove the "Cyber-Flap" `motion.div` completely. Replace with a clean fade-scale entry for the modal itself:
```tsx
<motion.div
  initial={{ opacity: 0, scale: 0.96, y: 12 }}
  animate={{ opacity: 1, scale: 1, y: 0 }}
  exit={{ opacity: 0, scale: 0.96, y: 8 }}
  transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
  className="relative z-30 bg-black/70 backdrop-blur-2xl border border-white/10 
             rounded-3xl p-10 shadow-[0_40px_80px_rgba(0,0,0,0.9)] overflow-hidden"
>
```

Backdrop: `bg-black/70` (up from `bg-black/60`) — proper modal dim

Close button: Add a visible hit target:
```tsx
<button
  onClick={onClose}
  className="absolute top-5 right-5 w-8 h-8 rounded-full flex items-center justify-center 
             bg-white/[0.05] hover:bg-white/10 text-white/50 hover:text-white 
             transition-all duration-200 z-50"
>
  <X className="w-4 h-4" />
</button>
```

Drop zone: Change `rounded-2xl` → `rounded-2xl` (keep). Change dashed border color:
```
border-white/20 hover:border-primary/50
```
(current is `hover:border-primary/60` — bring down slightly, less neon)

Upload icon container: Change `rounded-2xl` → `rounded-xl` (tighter). Keep size.

Dragging state scan line: `<div className="absolute inset-0 w-full h-[2px] bg-primary/40 animate-pulse top-1/2">` — change to a simple animated bar that goes top-to-bottom:
```tsx
<motion.div
  className="absolute inset-x-0 h-[1px] bg-primary/50 blur-[1px]"
  animate={{ top: ["0%", "100%"] }}
  transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }}
/>
```

---

### 2.2 — `UploadSuccessModal.tsx`

**Current issues:**
- The "Cyber-Flap" exit animation (`rotateX: 0` on exit) causes the exiting overlay to flash green — this looks like a rendering glitch, not an intentional effect
- `onNewUpload` button (`"Reselect"`) uses `rounded-xl` while `"Analyze"` uses `rounded-full` — inconsistent
- The success icon uses `after:animate-ping` on the container (ping effect) but the `after:` pseudo-element requires custom CSS that isn't defined — this silently does nothing

**Redesign Spec:**

Remove the "Cyber-Flap" overlay entirely. Use a clean entry/exit:
```tsx
<motion.div
  initial={{ opacity: 0, scale: 0.95 }}
  animate={{ opacity: 1, scale: 1 }}
  exit={{ opacity: 0, scale: 0.97 }}
  transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
  className="relative z-20 bg-black/80 backdrop-blur-2xl border border-white/10 
             rounded-3xl p-10 shadow-[0_40px_80px_rgba(0,0,0,0.9)]"
>
```

Success icon: Keep the `CheckCircle2` icon. Remove the broken `after:animate-ping`. Add a simple ring instead:
```tsx
<div className="relative w-20 h-20 flex items-center justify-center">
  <div className="absolute inset-0 rounded-full border border-primary/20 animate-pulse" />
  <div className="w-20 h-20 rounded-full bg-primary/10 border border-primary/30 
                  flex items-center justify-center">
    <CheckCircle2 className="w-9 h-9 text-primary" />
  </div>
</div>
```

Buttons — make consistent:
- "Reselect": `rounded-full py-3.5 px-6 text-sm font-semibold text-white/60 hover:text-white bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 transition-all duration-200`
- "Analyze": `rounded-full py-3.5 px-8 text-sm font-semibold bg-primary text-black hover:bg-primary/90 transition-all duration-200 shadow-[0_0_20px_rgba(0,255,65,0.2)]`

File name display: `font-mono text-xs text-white/50 bg-white/[0.03] px-4 py-2 rounded-xl border border-white/[0.06] break-all` (unchanged concept, improved class values)

---

### 2.3 — `HITLCheckpointModal.tsx`

**Current issues:**
- Uses the `<Dialog>` / `<DialogContent>` from shadcn — which wraps with its own overlay. This is correct for modal behavior (click-outside works natively with Radix).
- Decision option buttons use hardcoded Tailwind color classes like `border-emerald-500` — these need to map correctly against the design system
- Selected state has a border-color change which is correct but needs to be visible

**Redesign Spec:**

`DialogContent` className:
```tsx
className="sm:max-w-xl bg-black/90 backdrop-blur-2xl border border-white/10 
           p-0 overflow-hidden rounded-3xl shadow-[0_40px_80px_rgba(0,0,0,0.9)]"
```
(Remove `glass-panel` class — use explicit values for the modal, which requires stronger opacity than panels)

Header section within modal: Replace all-caps label text with Title Case.

Decision option buttons: Use a consistent selection pattern:
- Unselected: `bg-white/[0.03] border border-white/[0.08] text-white/70 rounded-2xl`
- Selected emerald: `bg-primary/10 border border-primary/30 text-primary`
- Selected red: `bg-danger/10 border border-danger/30 text-danger`
- Selected slate: `bg-white/[0.06] border border-white/20 text-white`

Submit button:
```tsx
className="w-full rounded-full py-3.5 font-semibold bg-primary text-black 
           hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed 
           transition-all duration-200"
```

Note textarea: `rounded-2xl bg-white/[0.03] border border-white/[0.08] text-white/80 placeholder:text-white/30 focus:border-primary/30 focus:outline-none resize-none p-4 text-sm`

---

### 2.4 — `dialog.tsx`

**Current issues:**
- The Radix Dialog overlay (`DialogOverlay`) needs a proper backdrop dim
- Custom class `sm:max-w-lg` breakpoint is fine

**Fix:**
```tsx
// DialogOverlay className:
"fixed inset-0 z-50 bg-black/75 backdrop-blur-sm data-[state=open]:animate-in 
 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0"
```
(Bump from `bg-black/80` if current — ensure `backdrop-blur-sm` is present for proper dim)

---

## Phase 3: Progress Overlays

### Files to Edit:
- `src/components/evidence/AnalysisProgressOverlay.tsx`
- `src/components/ui/ForensicProgressOverlay.tsx`
- `src/components/ui/LoadingOverlay.tsx`

---

### 3.1 — `AnalysisProgressOverlay.tsx`

**Remove:** Nested `scan-line-overlay` div (Stale Code fix #6)

**Spinner redesign:** The current double-ring spinner (track + fill) is correct and clean. Make it slightly larger: `w-12 h-12` → `w-14 h-14`.

**Title text:** `text-sm font-semibold text-primary/80` → `text-sm font-semibold text-primary tracking-wide` (remove `/80` opacity from brand color in active state).

**Heading:** `text-xl sm:text-2xl font-bold` → keep as-is. Title Case is already correct here ("Neural Uplink Active", "Initializing Protocol").

**Progress bar:** Current looping `width: "0%" → "100%"` animation is good. Make it slightly taller:
```
h-[3px] → h-[2px]  (actually thinner is more refined)
from-primary/50 via-primary to-white → from-transparent via-primary to-primary/80
```
Remove the `after:` pseudo-element glow on the bar — it's not working without defined CSS.

**Elapsed time display:** Change `animate-pulse` on the container — pulsing the time counter text looks like a loading state within a loading state. Remove pulse. Just show the time statically with `text-white/60`.

**Card container:** Add `divide-y divide-white/[0.04]` between the spinner and text sections for a clean internal separator.

---

### 3.2 — `ForensicProgressOverlay.tsx`

This is the full-screen overlay used during Council Deliberation (arbiter phase) and streaming. It has a log view.

**Current issues:**
- Full screen with `background: "rgba(2, 6, 23, 0.95)"` — almost completely opaque dark overlay. This is appropriate for a blocking progress state.
- Log entries appear with `AnimatePresence` — good.
- The `categorize()` function colors: success=green, error=red, info/system=muted. Correct pattern.

**Redesign Spec:**

The log container should feel like a terminal readout — clean mono font, controlled spacing:

Log entry styling by category:
```
success: text-primary/90 bg-primary/[0.04] border-l-2 border-primary/40
error:   text-danger/90 bg-danger/[0.04] border-l-2 border-danger/40
info:    text-white/70 bg-white/[0.02] border-l-2 border-white/10
system:  text-white/40 bg-transparent border-l border-white/[0.05]
```

Each log entry: `rounded-r-lg px-4 py-2 font-mono text-xs` with the above border-left accent.

Title text: Change `tracking-[0.25em]` to `tracking-wide` if present. Title Case: "Council Deliberation" not "COUNCIL DELIBERATION".

Spinner/indicator: Add a subtle pulsing circle indicator in the brand color above the title.

Telemetry label: `text-xs font-semibold text-white/40 tracking-wide` — not `tracking-widest`.

Elapsed time: `font-mono text-sm text-white/60 tabular-nums`.

---

### 3.3 — `LoadingOverlay.tsx`

Read and apply same principles: proper dim backdrop, clean spinner, Title Case labels, tracking-wide instead of tracking-widest, minimum `text-white/50` for any visible text.

---

## Phase 4: Evidence Analysis Page

### Files to Edit:
- `src/app/evidence/page.tsx` (layout wrapper only — no functional changes)
- `src/components/evidence/FileUploadSection.tsx`
- `src/components/evidence/AgentProgressDisplay.tsx`
- `src/components/evidence/AgentStatusCard.tsx`
- `src/components/evidence/ErrorDisplay.tsx`
- `src/components/evidence/ForensicTimeline.tsx`

---

### 4.1 — `FileUploadSection.tsx`

**Remove:** Stale scan-line effects (none here, but double-check)

**Status badge ("Evidence Upload"):**
```
Current: px-4 py-2 rounded-full bg-primary/5 border border-primary/10
New:     px-4 py-2 rounded-full bg-primary/[0.08] border border-primary/20
```
Label text: `"Evidence Upload"` — already Title Case and not uppercase. Keep. Font: `font-semibold` (up from `font-bold` in the badge — they're the same weight effectively, but the `text-xs` size makes bold look heavy). Actually keep `font-bold` for badge text — it needs visibility at `text-xs`.

H1 "Initiate Investigation": `font-black tracking-tighter` → `font-black tracking-tight` (slightly less extreme tracking). Already Title Case. Good.

**Drop zone (no file selected):**
```
Current: border-dashed rounded-3xl (assumed from context, full code not shown above)
New: Maintain dashed border, but use:
  border-white/20 → border-white/[0.15] 
  hover:border-primary/50 hover:bg-primary/[0.03]
  rounded-3xl stays
```

**File preview card (file selected):**
```
Current: glass-panel border-white/10 rounded-3xl
New: bg-black/50 backdrop-blur-xl border border-white/10 rounded-3xl (explicit, not glass-panel class)
```

**Hash display:** The SHA-256 hash should use `font-mono text-[10px] text-white/30 break-all` — visually distinct from other content.

**"Begin Analysis" / "Upload" action button:**
Same pill button spec from Phase 1: `rounded-full bg-primary text-black font-bold min-h-[48px] px-8`. Add `<ArrowRight>` icon on the right.

**File size color logic** (`fileSizeColor`): Keep existing color-coding (rose for >200MB, amber for >50MB, muted otherwise) — purely functional, no design change needed.

**Error state card:**
```
Current: glass-panel border-rose-500/20 bg-rose-500/[0.04] rounded-3xl
New: bg-danger/[0.05] backdrop-blur-xl border border-danger/20 rounded-3xl
```
Error icon: `<ShieldAlert>` at `text-danger` — good, keep.
Error text: `text-white/80` for the message, `text-danger/80` for the label.

---

### 4.2 — `AgentProgressDisplay.tsx`

This is the main view during active analysis.

**Agent card grid:** Ensure 2-col on md, 1-col on mobile.

**Agent finding preview items:** Each `FindingPreview` should show:
- Tool name badge: `rounded-full px-2.5 py-0.5 text-xs font-mono bg-white/[0.04] border border-white/[0.08] text-white/60`
- Summary text: `text-sm text-white/70`
- Confidence indicator: if present, show as a small horizontal bar `h-1 rounded-full bg-white/10` with fill `bg-primary` at `width: {confidence}%`
- Severity badge: Color-coded pill — `CRITICAL` → danger, `HIGH` → warning, `MEDIUM` → primary/50, `LOW` → white/30

**Action buttons** (awaitingDecision state — "Accept Analysis" / "Deep Analysis"):
Both must be pill buttons with clear hierarchy:
- Primary "Deep Analysis": `rounded-full bg-primary text-black font-bold px-8 py-3.5`
- Secondary "Accept Analysis": `rounded-full border border-white/15 text-white/70 hover:border-white/30 hover:text-white px-8 py-3.5`

**"View Results" button:** `rounded-full bg-primary text-black font-bold px-8 py-3.5 inline-flex items-center gap-2` with `<ArrowRight>` icon.

**Pipeline status text:** Use `text-white/60 text-sm font-medium` — do NOT pulse the whole container.

---

### 4.3 — `AgentStatusCard.tsx`

**Remove:** `scan-line-overlay` div (Stale Code fix #7)

**Card container:** 
```
New: bg-white/[0.04] backdrop-blur-xl border border-white/10 rounded-3xl
```

**Status badge design:**
- `running`: Green pulsing dot + `text-primary/80 bg-primary/[0.08] border-primary/20` badge
- `complete`: Checkmark icon + `text-primary bg-primary/[0.08] border-primary/20`
- `error`/`failed`: Shield-alert + `text-danger bg-danger/[0.06] border-danger/20`
- `skipped`: `text-white/40 bg-white/[0.03] border-white/[0.06]`

All status badges: `rounded-full px-3 py-1 text-xs font-semibold border inline-flex items-center gap-1.5`

**Confidence bar:** `h-1.5 rounded-full` with colored fill based on confidence value:
- >70: `bg-primary`
- 40-70: `bg-warning`
- <40: `bg-danger`

**Section flags:** Each flag pill: `rounded-full px-2.5 py-1 text-[10px] font-semibold border` with color based on flag value.

**Thinking/streaming text:** `font-mono text-xs text-white/50 leading-relaxed` in a container with `max-h-24 overflow-y-auto` to prevent cards from growing infinitely.

---

### 4.4 — `ErrorDisplay.tsx`

```
Current: glass-panel border-rose-500/20 bg-rose-500/[0.02] rounded-3xl
New: bg-danger/[0.04] backdrop-blur-xl border border-danger/20 rounded-3xl
```

Error title: Title Case, `text-white font-bold text-lg`
Error message: `text-white/70 text-sm leading-relaxed`

Retry button (if present): `rounded-full border border-white/15 text-white/70 hover:border-white/30 hover:text-white px-6 py-2.5 text-sm font-semibold`

---

### 4.5 — `ForensicTimeline.tsx`

Timeline items should have:
- Left border accent line `w-[2px] bg-white/10 rounded-full` (vertical connector)
- Dot nodes: `w-2 h-2 rounded-full bg-primary/60` for completed, `bg-white/20` for pending
- Event text: `text-sm text-white/70 font-medium`
- Timestamp: `font-mono text-xs text-white/40`
- Container: `bg-white/[0.02] border border-white/[0.06] rounded-2xl p-6 space-y-4`

---

## Phase 5: Result Page

### Files to Edit:
- `src/components/result/ResultLayout.tsx`
- `src/components/result/ResultHeader.tsx`
- `src/components/result/ArcGauge.tsx`
- `src/components/result/MetricsPanel.tsx`
- `src/components/result/TribunalMatrix.tsx`
- `src/components/result/AgentAnalysisTab.tsx`
- `src/components/ui/AgentFindingCard.tsx`
- `src/components/result/IntelligenceBrief.tsx`
- `src/components/result/TimelineTab.tsx`
- `src/components/result/HistoryPanel.tsx`
- `src/components/result/ActionDock.tsx`
- `src/components/result/DeepModelTelemetry.tsx`
- `src/components/result/EvidenceThumbnail.tsx`
- `src/app/result/page.tsx` (wrapper only)

---

### 5.1 — `ResultLayout.tsx`

**Tab navigation bar:**
```
Current: bg-white/[0.02] border border-white/5 p-1 rounded-full flex gap-1
Keep this — it's correct pill-tab design. 
```
Active tab: `bg-primary/15 border border-primary/20 text-primary font-semibold`
Inactive tab: `text-white/50 hover:text-white/80 font-medium`
Both: `rounded-full px-5 py-2 text-sm transition-all duration-200`

Tab icons: Use existing `HomeIcon`, `Activity`, `HistoryIcon` — keep. Size `w-3.5 h-3.5`.

**"Back to Evidence Analysis" button:**
```
Current: text-[11px] font-bold text-white/50 hover:text-white
New: text-sm font-medium text-white/50 hover:text-white inline-flex items-center gap-2 transition-colors
```

**Main content area:** The tab content panels currently use `rounded-[2.5rem]` — normalize to `rounded-3xl` for consistency.

**Arbiter progress overlay** (ForensicProgressOverlay with `variant="council"`) — already handled in Phase 3.

---

### 5.2 — `ResultHeader.tsx`

This is the most complex component — verdict banner, ArcGauge metrics, file info.

**Outer container:**
```
Current: "rounded-[2.5rem] border overflow-hidden premium-glass transition-all duration-700"
New: "rounded-3xl border overflow-hidden bg-black/50 backdrop-blur-xl transition-all duration-500"
```
Apply theme-based border via `theme.border` — unchanged logic.

**Dynamic status bar** at top: `h-1 w-full bg-gradient-to-r from-transparent via-current to-transparent opacity-30` (reduce height from 1.5 → 1, reduce opacity from 20% to 30% — more refined)

**Verdict headline:** Current `font-mono` on verdict text is correct for a data-driven verdict. Keep.

Verdict text size: `text-4xl md:text-5xl font-black font-mono` — keep this, it's impactful.

Subtext under verdict ("Forensic Probability" etc): `text-sm font-medium text-white/60 tracking-wide` (not `tracking-widest`).

**ArcGauge trio:** Three gauges side by side — keep layout. The gauge colors are dynamically set from verdict config — do not change the logic, only ensure the gauge `size` prop is appropriate: `size={110}` is good.

**Agent count / pipeline duration pills:**
```
Current: various inline text
New: Wrap each in a pill: "rounded-full px-3 py-1 bg-white/[0.04] border border-white/[0.06] text-xs font-mono text-white/50"
```

**Fingerprint / Lock icons:** Keep the security iconography — it reinforces the forensic brand. Ensure they are `text-primary/30` not `text-primary` (decorative, not interactive).

---

### 5.3 — `ArcGauge.tsx`

**Cleanup:** Remove the duplicate `interface ArcGaugeProps` declaration (Stale Code fix #2).

**Visual refinements:** Gauge is already clean. Only:
- Track stroke: `rgba(255,255,255,0.08)` → `rgba(255,255,255,0.06)` (slightly subtler track)
- Label `text-[10px] font-bold tracking-widest` → `text-xs font-semibold tracking-wide` (Title Case fix)

---

### 5.4 — `MetricsPanel.tsx`

Each metric row should follow a consistent pattern:
- Label: `text-sm font-medium text-white/60`
- Value: `text-sm font-mono font-semibold text-white/90`
- Separator: `border-b border-white/[0.04]` (very subtle)

Container: `rounded-3xl border border-white/[0.08] bg-white/[0.03] backdrop-blur-xl p-6 space-y-4`

Remove any `tracking-widest` on labels.

---

### 5.5 — `TribunalMatrix.tsx`

**Header:** "Tribunal Consensus Matrix" label — remove `tracking-widest`, use `tracking-wide`. Change to `text-xs font-semibold text-white/60`.

**"Requires Human Review"** status: Change `tracking-widest font-black` → `tracking-wide font-semibold`.

**Contested finding items:** Each item in `bg-white/[0.02] rounded-xl p-4 border border-white/[0.04]` — subtle card treatment.

**Resolved finding items:** `bg-primary/[0.03] rounded-xl p-4 border border-primary/[0.06]`.

---

### 5.6 — `AgentFindingCard.tsx` + `AgentAnalysisTab.tsx`

**AgentFindingCard:**
```
Current: "rounded-[2rem] overflow-hidden premium-glass border transition-all duration-500"
New: "rounded-3xl overflow-hidden bg-white/[0.04] backdrop-blur-xl border border-white/10 transition-all duration-300"
```

`bg-grid-small` hover overlay: Now that the class is defined (Phase 1 CSS fix), this will show a subtle dot grid on hover — keep it.

Finding type badge: Currently hardcoded Tailwind color strings per finding type. Apply design system colors:
- `AUTHENTIC` / `UNMANIPULATED`: primary green
- `MANIPULATED` / `AI_GENERATED`: danger red
- `INCONCLUSIVE` / `SUSPICIOUS`: warning gold
- All others: white/40

Badge pill: `rounded-full px-3 py-1 text-xs font-semibold border`

Confidence bar inside each finding: `h-1 rounded-full` with color-coded fill.

Tool name display: `font-mono text-xs text-white/50 bg-white/[0.04] rounded-lg px-2 py-1`

---

### 5.7 — `IntelligenceBrief.tsx`

```
Current: "px-8 py-10 rounded-[2.5rem] premium-glass border-border-subtle"
New: "p-8 rounded-3xl bg-white/[0.04] backdrop-blur-xl border border-white/10"
```

Brief text content: `text-base font-medium text-white/75 leading-relaxed` (up from `/60` — this is important content, needs to be readable).

Section label above brief: `text-xs font-semibold text-white/40 tracking-wide uppercase` — wait, this is allowed (structural label, not button or heading). Keep uppercase on structural labels like "Intelligence Brief" if that's the category label.

---

### 5.8 — `TimelineTab.tsx`

Timeline entries — apply same spec as Phase 4 ForensicTimeline:
- Left border accent line
- Dot nodes color-coded by event type
- `font-mono` timestamps
- `text-white/70` event text

Container `rounded-[2.5rem]` → `rounded-3xl`.

---

### 5.9 — `HistoryPanel.tsx`

**Header:**
- "Investigation Archive" — already Title Case. `text-xl font-bold text-white`. Keep.
- Subtitle `text-[11px]` → `text-sm text-white/40` (more readable).

**History item cards:**
```
Current: (not shown in detail, but assumed glass-panel)
New: bg-white/[0.03] border border-white/[0.06] rounded-2xl p-5 hover:bg-white/[0.05] hover:border-white/10 transition-all duration-200 cursor-pointer
```

**Verdict badge** on each history item: `rounded-full px-3 py-1 text-xs font-semibold border` using `getVerdictStyle()` — the color logic is already implemented, just ensure the badge is `rounded-full` not `rounded`.

**"Clear All" button:** `rounded-full px-4 py-2 text-sm font-medium text-danger/70 hover:text-danger border border-danger/20 hover:border-danger/40 hover:bg-danger/[0.05] transition-all duration-200`

**Individual remove button** (Trash icon): `w-8 h-8 rounded-full flex items-center justify-center bg-white/[0.04] hover:bg-danger/10 text-white/30 hover:text-danger border border-white/[0.06] hover:border-danger/20 transition-all duration-200`

**Empty state:** If no history, show centered message `text-white/40 text-sm` — ensure this is displayed gracefully.

---

### 5.10 — `ActionDock.tsx`

The floating action dock at the bottom of results.

```
Current: "flex items-center gap-2 p-2 rounded-full premium-glass border-border-subtle shadow-[0_20px_50px_rgba(0,0,0,0.8)]"
New: "flex items-center gap-2 p-2 rounded-full bg-black/70 backdrop-blur-xl border border-white/10 shadow-[0_20px_60px_rgba(0,0,0,0.9)]"
```

Action buttons inside dock: Each `rounded-full` pill button with icon + label. Use the pill button spec from Phase 1.

---

### 5.11 — `DeepModelTelemetry.tsx`

```
Current: "rounded-2xl overflow-hidden glass-panel border border-violet-500/20 bg-violet-500/[0.02]"
Keep the violet accent for deep model — it's already distinct from primary green and correctly indicates a different analysis mode.
```

Label typography: Remove any `tracking-widest`, use `tracking-wide`.

Telemetry values: `font-mono` — keep. Values should be `text-white/80`, labels `text-white/50`.

---

## Error & Session Pages

### Files to Edit:
- `src/app/error.tsx`
- `src/app/global-error.tsx`
- `src/app/not-found.tsx`
- `src/app/session-expired/page.tsx`

All these pages should follow:
- Same glass panel: `bg-white/[0.04] backdrop-blur-xl border border-white/10 rounded-3xl`
- Error/danger context: Use `border-danger/20` and `text-danger`
- Action buttons: Pill spec
- No `uppercase` labels, no `tracking-widest`
- Title Case for headings

---

## Execution Order

**Within each phase, edit files in this sequence to avoid cascading regressions:**

```
Phase 0 (Pre-work):  globals.css → GlobalBackground.tsx (delete) → ui/index.ts → ArcGauge.tsx
Phase 1:             globals.css → MicroscopeBackground.tsx → BrandLogo.tsx → GlobalNavbar.tsx
                     → HeroAuthActions.tsx → page.tsx → HowWorksSection.tsx → AgentsSection.tsx
                     → GlobalFooter.tsx
Phase 2:             dialog.tsx → UploadModal.tsx → UploadSuccessModal.tsx → HITLCheckpointModal.tsx
Phase 3:             AnalysisProgressOverlay.tsx → ForensicProgressOverlay.tsx → LoadingOverlay.tsx
Phase 4:             FileUploadSection.tsx → AgentStatusCard.tsx → AgentProgressDisplay.tsx
                     → ErrorDisplay.tsx → ForensicTimeline.tsx
Phase 5:             ResultHeader.tsx → ArcGauge.tsx → MetricsPanel.tsx → TribunalMatrix.tsx
                     → AgentFindingCard.tsx → AgentAnalysisTab.tsx → IntelligenceBrief.tsx
                     → TimelineTab.tsx → HistoryPanel.tsx → ActionDock.tsx → DeepModelTelemetry.tsx
                     → ResultLayout.tsx
Final:               error.tsx → global-error.tsx → not-found.tsx → session-expired/page.tsx
Post-cleanup:        Verify no unused CSS remains in globals.css, no dead imports in any edited file
```

---

## Quality Checklist (After Each Phase)

- [ ] No `uppercase` CSS class on any heading or button text (structural labels excepted)
- [ ] No `tracking-widest` — all replaced with `tracking-wide` or less
- [ ] No font `text-[X]px` below `text-sm` for any readable content (non-decorative)
- [ ] No minimum contrast ratio below WCAG AA (4.5:1 for normal text on black)
- [ ] All interactive elements have `min-h-[44px]` touch target (WCAG 2.5.5)
- [ ] All buttons are `rounded-full` (pill) unless they are icon-only (then `rounded-xl`)
- [ ] All modals have `onClick={onClose}` on backdrop, `e.stopPropagation()` on content
- [ ] Glass panels use consistent `bg-white/[0.04] backdrop-blur-xl border border-white/10`
- [ ] Zero dead scan-line overlay divs remain
- [ ] MicroscopeBackground visible through all glass panels on scroll
- [ ] `GlobalBackground.tsx` file deleted, its export removed from `ui/index.ts`
- [ ] No external URL assets (grainy-gradients.vercel.app removed)
- [ ] All `font-mono` text uses JetBrains Mono variable correctly
- [ ] No double-declared TypeScript interfaces
- [ ] `Begin Analysis` button text confirmed (changed from "Begin Investigation")
- [ ] Arrow icon in CTA button confirmed
- [ ] Build passes TypeScript compilation
- [ ] No visible regressions on `/`, `/evidence`, `/result`, `/session-expired`
```

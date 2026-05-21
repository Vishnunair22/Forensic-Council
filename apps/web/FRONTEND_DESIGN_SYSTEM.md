# Frontend Design System — Precision Frosted Glass

## 1. Product Design Thesis

The app is a premium forensic analysis interface.

It must feel:

- modern
- slick
- precise
- court-grade
- evidence-first
- trustworthy
- glassy but readable
- high-contrast
- calm under pressure

The app must not feel like:

- a crypto dashboard
- a hacker terminal
- a sci-fi HUD
- a gaming interface
- a generic SaaS admin panel
- a neon cyber dashboard

The core visual language is:

> Precision Frosted Glass

Every major UI element should feel like part of one unified glass operating system: cards, agent panels, buttons, modals, nav, upload areas, tabs, docks, badges, and result containers.

Glass is used for depth and cohesion, not decoration.

Readability always wins over transparency.

---

# 2. Core Visual Identity

## 2.1 Design Name

**Precision Frosted Glass**

## 2.2 Design Principle

The entire app uses a controlled frosted-glass material system with rounded edges, subtle light reflection, soft depth, and strong text contrast.

The UI should feel premium and cohesive end-to-end.

## 2.3 One-Line Rule

> All UI chrome must use the same frosted glass material language. Transparency, blur, border highlights, and depth are allowed only when they improve clarity, hierarchy, and polish.

---

# 3. Non-Negotiable Rules

These rules are mandatory. No exceptions without explicit documentation.

## 3.1 Readability

Text must always be readable.

Never place important text directly over busy visuals without a dark glass surface behind it.

Minimum text opacity for **readable UI text**:

```txt
Primary text:   96–100%   (page titles, verdicts, key numbers)
Secondary text: 78–86%    (body text, labels, descriptions)
Muted text:     62–72%    (metadata, helper text)
Faint text:     55% min   (timestamps, non-critical chrome text)
```

Text opacity below `55%` is banned for readable UI text.

**Glass surface constraint:** Text rendered inside `fc-surface-elevated` or `fc-surface-overlay` must use `fc-text-muted` (68%) as the readable minimum — not `fc-text-faint`. The backdrop content beneath a glass surface is variable; `fc-text-faint` at 55% cannot be guaranteed to meet WCAG 4.5:1 in all real-world conditions. `fc-text-faint` inside elevated/overlay surfaces is permitted only for timestamps, decorative separators, and non-readable chrome.

**Allowed exceptions** (not readable text — these are visual chrome):
- Decorative icon buttons: opacity can be lower when they have a visible hover target (e.g., `text-white/30 hover:text-white/90`)
- Separator characters (`·`, `/`) used as visual dividers
- `placeholder:text-white/*` on form inputs (placeholders are hints, not readable content)
- Status indicator dots (`w-1.5 h-1.5 rounded-full`) where the dot itself communicates state visually
- Interactive elements where the low-opacity state is intentionally distinct from a hover/active state

## 3.2 Glass Consistency

All major UI containers must use the canonical glass surface system (see Section 6).

Do not create one-off card styles with random borders, shadows, and background opacity values. When a custom background is absolutely required (e.g., inside a canvas-level full-bleed section), document the exception inline.

## 3.3 Rounded Shape Language

The app uses soft rounded geometry.

Required shape language:

```txt
Cards:                rounded-2xl or rounded-3xl
Modals:               rounded-3xl  (2rem)
Buttons:              rounded-full  (pill)
Badges:               rounded-full
Input fields:         rounded-2xl or rounded-full depending on context
Panels/docks:         rounded-2xl or rounded-3xl
```

Sharp corners (`rounded-none`, `rounded-sm`) are not allowed.

## 3.4 Case Rules

Forced uppercase is banned.

Allowed:

```txt
Title Case labels
Sentence case descriptions
Real acronyms: AI, PDF, API, SHA, MIME, URL, ID
```

Banned:

```txt
text-transform: uppercase
Tailwind `uppercase` class
Tracking-heavy all-caps labels
Fake terminal labels in all caps
```

## 3.5 Motion

Motion must be subtle and functional. Default duration: **160ms**. Maximum: **200ms** for expand/collapse.

Allowed:

```txt
Opacity fade: 0 → 1
Y offset: 4px max (initial: y:4, animate: y:0)
whileTap scale: 0.98 only on interactive buttons (press feedback)
Status dot animate-pulse: only on functional indicator dots (w-1.5/w-2 rounded-full)
Progress bar linear movement
Color/border/background transitions on hover (160ms ease)
Accordion height: 0 → auto with opacity, 200ms max
```

Banned:

```txt
Scale entrances/exits on containers, cards, modals, or panels
hover:scale-*
group-hover:scale-*
animate-pulse on icons or containers
animate-pulse used decoratively (not communicating live state)
scan beam effects
orbit animation
spring or bounce (type: "spring")
duration > 200ms for any entrance
y offset > 4px
large sliding or parallax effects
```

The only allowed Framer Motion transition is `{ duration: 0.16, ease: "easeOut" }` for entrances and `{ duration: 0.16 }` for exits. All other durations and easing are banned unless the element is a progress bar or an accordion.

## 3.6 Color

Teal is the product accent and primary action identity.

Teal should be used for:

```txt
Primary CTA buttons
Active state
Focus ring
Progress state
Analysis state
Subtle hover tint
Selected navigation
```

Teal should not be used everywhere.

Semantic colors must only represent meaning:

```txt
Red:    danger, destructive action, deception, severe risk
Amber:  caution, uncertainty, review needed
Emerald: verified, authentic, complete
Blue:   information or neutral process (use sparingly)
```

Semantic colors must not be used as decorative glows.

---

# 4. Color System

## 4.1 Base Background

The app uses a dark forensic background. The root canvas is `#02040A`.

Canonical globals.css tokens:

```css
@theme {
  --color-background: #02040A;
  --color-primary: #5eead4;       /* teal-300 */
  --color-danger:  #f43f5e;
  --color-warning: #f59e0b;
  --color-success: #10b981;
}
```

## 4.2 Text Classes

Four canonical text utility classes, defined in globals.css:

```txt
fc-text-primary       → rgba(255,255,255,0.98)   page titles, verdicts, key numbers
fc-text-secondary     → rgba(255,255,255,0.82)   normal body text, labels
fc-text-muted         → rgba(255,255,255,0.68)   metadata, helper text
fc-text-faint         → rgba(255,255,255,0.55)   timestamps, faint chrome text (decorative only inside glass)
```

Never use `text-white/X` with X < 55 for readable text. Use the canonical classes instead.

**`fc-text-faint` inside `fc-surface-elevated` or `fc-surface-overlay`:** Restricted to decorative/non-readable chrome. Readable content in these contexts must use `fc-text-muted` (68%) minimum, because the variable glass backdrop makes 55% opacity unreliable for WCAG compliance. This does not affect `fc-text-faint` on standard backgrounds or `fc-surface-quiet`/`fc-surface` where the backdrop opacity is more controlled.

Do not create new text utility classes outside this hierarchy.

## 4.3 Teal Brand Accent

Teal is the primary action color. The canonical token is `--color-primary: #5eead4`.

Use `text-primary`, `border-primary`, `bg-primary` via Tailwind. Do not hardcode teal hex values in component files.

## 4.4 Semantic Colors

| Purpose   | Token               | Usage                                        |
|-----------|---------------------|----------------------------------------------|
| Danger    | `--color-danger`    | Errors, destructive actions, deception       |
| Warning   | `--color-warning`   | Caution, uncertainty, review needed          |
| Success   | `--color-success`   | Verified, authentic, complete                |

Never use semantic colors for decoration or chrome.

---

# 5. Typography System

## 5.1 Font Behavior

Typography should feel clean, precise, and readable. Use strong hierarchy, not decorative effects.

## 5.2 Text Scale

Use Tailwind's system scale, not arbitrary pixel values:

```txt
Page title:      text-4xl to text-6xl
Section title:   text-2xl to text-3xl
Card title:      text-lg to text-xl
Body:            text-sm to text-base
Metadata:        text-xs
```

**Banned arbitrary sizes:**

```txt
text-[10px]   → use text-xs
text-[11px]   → use text-xs
text-[13px]   → use text-sm
text-[15px]   → use text-base
```

Arbitrary font sizes are only allowed when the exact pixel value is a documented design constraint that cannot be approximated by a system token.

## 5.3 Eyebrow Labels

Eyebrows are allowed for section metadata. They must not be forced uppercase.

```css
.fc-eyebrow {
  font-size: 0.75rem;  /* text-xs */
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var canonical fc-text-muted or fc-text-faint;
}
```

Usage example: `<span className="fc-eyebrow fc-text-faint">Phase 01</span>`

`uppercase` class on eyebrows is banned.

## 5.4 Tracking

Use Tailwind's tracking scale:

```txt
tracking-tight   (-0.025em)
tracking-normal  (0)
tracking-wide    (0.025em)
tracking-wider   (0.05em)
tracking-widest  (0.1em)
```

Arbitrary tracking values like `tracking-[0.18em]` or `tracking-[0.3em]` are discouraged. Use `tracking-wider` or `tracking-widest` as approximations.

---

# 6. Surface System

All cards, panels, modals, upload zones, docks, and agent containers must use canonical surface classes. Do not create one-off surface styles.

## 6.1 Surface Decision Tree

Pick the **lowest tier** that is still visible at the given nesting depth:

```txt
fc-surface-solid    → fully opaque (#060D18), no glass
                      use for visual anchor points that must not blend into background
                      example: sidebar rails, opaque section dividers

fc-surface-quiet    → subtle frosted glass, default choice
                      use for inner containers, cards nested inside a page section, list items
                      example: agent cards, history list items, nested panels

fc-surface          → standard frosted glass
                      use for primary cards/panels sitting directly on the page background
                      example: main section containers, feature cards

fc-surface-elevated → prominent frosted glass
                      use for dialogs, feature callouts, cards that demand visual hierarchy
                      example: checkpoint modals, HITL panels, important result cards

fc-surface-overlay  → maximum frosted glass
                      use for modal backdrops and critical overlays floating above all content
                      example: UploadModal, ForensicErrorModal, ArbiterDeliberationOverlay
```

**Rule:** Adjacent surfaces must differ by exactly one tier. Never skip tiers.

## 6.2 Solid Surface

```css
.fc-surface-solid {
  position: relative;
  border-radius: 1.5rem;
  border: 1px solid rgba(255,255,255,0.12);
  background: #060D18;
  box-shadow: 0 8px 28px rgba(0,0,0,0.45);
}
```

## 6.3 Quiet Surface (default)

```css
.fc-surface-quiet {
  position: relative;
  border-radius: 1.5rem;
  border: 1px solid rgba(255,255,255,0.13);
  background:
    linear-gradient(180deg, rgba(255,255,255,0.072), rgba(255,255,255,0.038)),
    rgba(8,13,24,0.64);
  backdrop-filter: blur(18px) saturate(125%);
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.09),
    0 12px 30px rgba(0,0,0,0.28);
}
```

## 6.4 Standard Surface

```css
.fc-surface {
  position: relative;
  border-radius: 1.5rem;
  border: 1px solid rgba(255,255,255,0.15);
  background:
    linear-gradient(180deg, rgba(255,255,255,0.088), rgba(255,255,255,0.046)),
    rgba(8,13,24,0.70);
  backdrop-filter: blur(22px) saturate(135%);
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.12),
    0 18px 44px rgba(0,0,0,0.32);
}
```

## 6.5 Elevated Surface

```css
.fc-surface-elevated {
  position: relative;
  border-radius: 1.75rem;
  border: 1px solid rgba(255,255,255,0.17);
  background:
    linear-gradient(180deg, rgba(255,255,255,0.095), rgba(255,255,255,0.050)),
    rgba(8,13,24,0.76);
  backdrop-filter: blur(24px) saturate(145%);
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.14),
    inset 0 -1px 0 rgba(255,255,255,0.045),
    0 22px 56px rgba(0,0,0,0.38);
}
```

## 6.6 Overlay Surface

```css
.fc-surface-overlay {
  position: relative;
  border-radius: 2rem;
  border: 1px solid rgba(255,255,255,0.18);
  background:
    linear-gradient(180deg, rgba(255,255,255,0.105), rgba(255,255,255,0.050)),
    rgba(5,10,20,0.88);
  backdrop-filter: blur(30px) saturate(155%);
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.18),
    inset 0 -1px 0 rgba(255,255,255,0.06),
    0 30px 80px rgba(0,0,0,0.48);
}
```

## 6.7 Light Reflection

Glass panels may include a subtle top highlight via a pseudo-element. The highlight must not exceed 12% white overlay at the top edge and must fade to 0% within 42% of the panel height.

## 6.8 Glass Nesting Limit — The Rule of Two

`backdrop-filter` forces a GPU compositing layer in the browser. Each nested blur layer compounds this cost. On integrated graphics — common on department-issued investigator hardware — two nested `backdrop-filter` surfaces degrade frame rate noticeably; three or more cause visible jank.

**The Rule:** A maximum of two `backdrop-filter` surfaces may overlap on the Z-axis at any time.

The permitted stack:

```txt
Level 0: Page background (#02040A)               — no backdrop-filter
Level 1: Glass card / panel                       — one backdrop-filter (fc-surface, fc-surface-quiet, fc-surface-elevated)
Level 2: Glass modal / overlay                    — one backdrop-filter (fc-surface-overlay + fc-modal-backdrop)
```

`fc-modal-backdrop` counts as one blur layer. If the modal shell is `fc-surface-overlay` (layer two), the interior of that modal cannot contain any additional blurred surfaces.

**If a card must live inside a glass modal:**

```txt
Use fc-surface-solid (fully opaque, no backdrop-filter)
OR use a non-blurred translucent fallback: background: rgba(8,13,24,0.72), no backdrop-filter
Do NOT use fc-surface-quiet, fc-surface, or fc-surface-elevated inside fc-surface-overlay
```

This rule applies to the Z-axis overlap region only. Two separate glass surfaces that do not visually overlap (e.g., a sidebar card and a main content card on the same page) are not subject to this constraint.

---

# 7. Button System

Buttons must be pill-shaped (`border-radius: 999px`). The app uses four button types: `fc-btn-primary`, `fc-btn-secondary`, `fc-btn-ghost`, `fc-btn-danger`.

## 7.1 Primary Button

Use for the highest-priority action on any screen.

```txt
Begin Analysis, Upload Evidence, Continue, Confirm, Generate Report, View Report, Proceed
```

Properties:
- Background: deep teal frosted glass gradient
- Color: `rgba(240,253,250,0.96)`
- Border: `rgba(94,234,212,0.46)`
- Min height: 44px
- Transition: 160ms ease on all interactive properties
- Disabled: opacity 0.48, no shadow
- Neon box shadow: a restrained teal ambient shadow (`0 0 28px rgba(45,212,191,0.14)`) is part of the canonical style — this is not a "neon glow" violation because it is defined in the system

## 7.2 Secondary Button

Use for supporting actions and navigation.

```txt
Back, Cancel, View Details, Download, Open Timeline, Switch Tab, Copy
```

Properties:
- Background: neutral white glass gradient
- Color: `rgba(255,255,255,0.78)`
- Border: `rgba(255,255,255,0.16)`
- Hover: teal-tinted glass
- Min height: 40px

## 7.3 Ghost Button

Use for low-priority inline actions.

```txt
Dismiss, Learn More, Expand, Collapse, Minor filters, Utility actions
```

Properties:
- Background: transparent
- Color: `rgba(255,255,255,0.68)`
- Border: transparent (visible on hover)
- Min height: 38px

## 7.4 Danger Button

Use for destructive or irreversible actions.

```txt
Delete, Remove Evidence, Clear Session, Reject, Reset
```

Properties:
- Background: `rgba(239,68,68,0.08)`
- Color: `rgba(254,202,202,0.94)`
- Border: `rgba(248,113,113,0.28)`
- Min height: 40px

## 7.5 Button Mapping

| Action               | Type                              |
|----------------------|-----------------------------------|
| Begin Analysis       | Primary                           |
| Upload Evidence      | Primary                           |
| Continue / Proceed   | Primary                           |
| Generate Report      | Primary                           |
| View Report          | Primary                           |
| Confirm Checkpoint   | Primary                           |
| Back / Cancel        | Secondary                         |
| View Details         | Secondary                         |
| Download Report      | Secondary or Primary (by context) |
| Copy Link            | Ghost                             |
| Dismiss              | Ghost                             |
| Expand Details       | Ghost                             |
| Delete / Remove      | Danger                            |
| Clear Session        | Danger                            |

## 7.6 Button Don'ts

```txt
Do not add hover:scale-* to buttons
Do not add shadow-[0_0_*] beyond the canonical button shadow
Do not use white primary buttons
Do not use blue/purple CTA buttons
Do not use uppercase button labels
```

---

# 8. Badge and Status System

Badges must be rounded pills. Use the `Badge` component or `fc-badge*` classes.

Text size in badges: `text-xs`. Do not use `text-[10px]` or `text-[11px]`.

| Class             | Color    | Usage                               |
|-------------------|----------|-------------------------------------|
| `fc-badge`        | neutral  | General metadata tags               |
| `fc-badge-active` | teal     | Live/active/running state           |
| `fc-badge-danger` | red      | Error, deception, high-risk         |
| `fc-badge-warning`| amber    | Uncertainty, review needed          |
| `fc-badge-success`| emerald  | Verified, complete, authentic       |

Do not create one-off badge styles with inline `bg-*` and `border-*` values.

---

# 9. Modals and Overlays

All modals must use `fc-surface-overlay`.

Modal requirements:

```txt
Surface:          fc-surface-overlay
Border radius:    rounded-3xl (2rem)
Backdrop:         fc-modal-backdrop
Motion:           opacity + y:4px only (NO scale)
Duration:         160ms ease-out
Title:            Clear, readable, not uppercase
Body text:        fc-text-faint minimum (55%)
Primary action:   right side
Cancel/secondary: left side
Close button:     top-right, fc-text-faint with hover to white
No neon box shadows on modal containers
No border-color glow shadows
```

Modal backdrop class:

```css
.fc-modal-backdrop {
  background:
    radial-gradient(circle at top, rgba(20,184,166,0.08), transparent 34%),
    rgba(0,0,0,0.58);
  backdrop-filter: blur(12px);
}
```

Modal motion — **the only accepted pattern**:

```tsx
initial={{ opacity: 0, y: 4 }}
animate={{ opacity: 1, y: 0 }}
exit={{ opacity: 0, y: 4 }}
transition={{ duration: 0.16, ease: "easeOut" }}
```

Scale entrances/exits on modals are banned.

---

# 10. Agent Cards

Agent cards must use `fc-surface-quiet` (default) or `fc-surface-elevated` (for prominent/expanded state).

Each agent card includes:

```txt
Agent name
Short role badge
Current status
Confidence/progress when available
Expandable findings behind disclosure
```

Rules:

```txt
Use fc-surface-quiet or fc-surface-elevated
Border radius: rounded-2xl or rounded-3xl
Teal border only for active/running state
Semantic colors only for actual agent state (red = error, emerald = complete)
No decorative glowing borders
No uppercase labels
No terminal-style section headers
```

Agent state border classes:

```css
.fc-agent-active   { border-color: rgba(94,234,212,0.38); }
.fc-agent-complete { border-color: rgba(52,211,153,0.30); }
.fc-agent-error    { border-color: rgba(248,113,113,0.34); }
```

---

# 11. Inputs and Upload Areas

## 11.1 Input

```txt
Border radius:    rounded-2xl or rounded-full
Min height:       44px
Background:       rgba(255,255,255,0.055)
Border:           rgba(255,255,255,0.14)
Text:             rgba(255,255,255,0.96)
Placeholder:      rgba(255,255,255,0.20) — placeholder opacity is exempt from the 55% rule
Focus border:     rgba(94,234,212,0.52)
Focus shadow:     0 0 0 3px rgba(45,212,191,0.12)
Transition:       160ms ease
```

## 11.2 Upload Zone

```txt
Border radius:    rounded-3xl (2rem)
Border:           1px dashed rgba(94,234,212,0.34)
Background:       teal-tinted glass, fc-surface-elevated equivalent
Hover border:     rgba(94,234,212,0.58)
Transition:       160ms ease
No scale on hover or drag-over
```

## 11.3 Evidence File Name Display

After a file is accepted, its name is rendered inside a glass panel. File names are user-controlled and must be treated as adversarial input — a malicious actor can submit a file with a 500-character name, homoglyph sequences, or zero-width spaces. An unbounded file name will blow out flex containers, break glass boundaries, and can obscure adjacent UI elements (including action buttons like Delete or Proceed).

**Mandatory constraints for all rendered file names:**

```txt
Always truncate: overflow-hidden, text-overflow: ellipsis, white-space: nowrap
Always constrain the container: max-w-full or an explicit max-w-* — never fit-content or min-content
Always provide the full name via the title attribute for hover inspection
Never allow the file name to set the width of its parent glass panel
```

Canonical pattern:

```tsx
<span
  className="block truncate max-w-full text-sm fc-text-secondary"
  title={fileName}
>
  {fileName}
</span>
```

For hashes, raw output, and URLs displayed on this same screen, see **Section 20.5** (Forensic Data Rendering) for the full truncation and overflow ruleset.

---

# 12. Navigation

## 12.1 Global Navbar

The navbar is `position: fixed` at `top: 0`, height `64px` (`h-16`).

**All page `<main>` elements must have `pt-16` to clear the fixed navbar.** This is set once on the root layout `<main>` — do not add per-page top padding that compensates for the navbar independently.

Rules:

```txt
Height:       64px (h-16)
Background:   frosted glass with teal bottom accent gradient
Border:       1px solid rgba(255,255,255,0.08) on bottom
z-index:      50 minimum
No heavy glow
No uppercase nav labels
Teal only for active page indicator or primary CTA
Readable page label pill on right side
```

## 12.2 Navbar Offset Rule

Pages must not double-stack padding. The layout is:

```txt
layout.tsx <main>: pt-16  (clears navbar — always present)
Page sections:     py-10 to py-16 at most  (no py-32 or larger)
```

If a page has a secondary fixed bar (e.g., result tabs at `top-16`), add `pt-12` within that page's content container — not via the root `<main>`.

## 12.3 Action Docks

Action docks use `fc-surface-elevated`.

```txt
No massive shadows
No excessive blur beyond fc-surface-elevated spec
Primary action must be visually dominant
Secondary actions must be neutral glass
Mobile: minimum 44px tap targets for primary, 40px for secondary
```

---

# 13. Result Page

The result page is evidence-first.

Hierarchy:

```txt
1. Verdict
2. Evidence identity (file, hash, MIME type)
3. Confidence and integrity score
4. Intelligence brief (narrative synthesis)
5. Key findings
6. Agent details (collapsible)
7. Timeline and technical metadata
```

Rules:

```txt
Verdict must be immediately visible above the fold
Detailed logs must be behind disclosure (not expanded by default)
Semantic colors must map to forensic meaning — never decorative
Glass nesting follows the global Rule of Two (see Section 6.8) — no exceptions on this page
All evidence strings (file names, hashes, MIME types) follow the truncation rules in Sections 11.3 and 20.5
```

Verdict color mapping:

```txt
Authentic / verified:     emerald (--color-success)
Manipulated / deceptive:  red (--color-danger)
Uncertain / inconclusive: amber (--color-warning)
Processing / active:      teal (--color-primary)
```

## 13.1 Print and PDF Export Mode

"Court-grade" means the report must be as official on a printed page as on a monitor. Frosted glass, `backdrop-filter`, and dark backgrounds do not survive PDF export reliably — Chromium print, system print dialog, and headless renderers (Puppeteer, Playwright PDF) each handle `@media print` differently. `backdrop-filter` in particular is silently dropped or rendered opaque-black by most PDF engines.

**Primary mechanism: `data-print-mode` attribute, not `@media print` alone.**

Set `data-print-mode="true"` on `<html>` or `<body>` when the user triggers export. `@media print` may be used as a supplementary fallback but must not be the sole mechanism. Tailwind `print:` variants are insufficient for overriding `backdrop-filter` across all PDF paths.

When `data-print-mode="true"` is active:

```txt
All backdrop-filter surfaces:   → background: #ffffff, backdrop-filter: none
All dark backgrounds:           → #ffffff
Primary text (fc-text-primary): → #000000
Secondary text:                 → #1a1a1a
Muted text:                     → #4a4a4a
Faint text:                     → #6b7280
Teal accent (#5eead4):          → #0f766e  (darker teal — printable, high-contrast on white)
Glass borders:                  → #d1d5db  (gray-300)
All box-shadow / blur:          → removed
Badge backgrounds:              → semantic solid equivalents (danger → #dc2626, success → #15803d, etc.)
```

Implementation pattern in `globals.css`:

```css
[data-print-mode="true"] .fc-surface,
[data-print-mode="true"] .fc-surface-quiet,
[data-print-mode="true"] .fc-surface-elevated,
[data-print-mode="true"] .fc-surface-overlay,
[data-print-mode="true"] .fc-surface-solid {
  backdrop-filter: none;
  background: #ffffff;
  border-color: #d1d5db;
  box-shadow: 0 0 0 1px #d1d5db;
}

[data-print-mode="true"] .fc-text-primary   { color: #000000; }
[data-print-mode="true"] .fc-text-secondary { color: #1a1a1a; }
[data-print-mode="true"] .fc-text-muted     { color: #4a4a4a; }
[data-print-mode="true"] .fc-text-faint     { color: #6b7280; }
```

The print export button must set this attribute before triggering `window.print()` or the PDF generation call, and remove it after the dialog closes.

---

# 14. Landing Page

Rules:

```txt
Use frosted glass sections
Use teal CTA
Avoid white primary buttons
Avoid excessive radial glows
No forced uppercase
Keep hero text readable (fc-text-secondary minimum on body)
Keep background subtle — LandingBackground component handles canvas effects
```

The landing page shares the same material system as the app workspace. Section backgrounds may be more atmospheric (gradient radials, subtle noise), but all text and interactive elements follow the same rules.

---

# 15. Evidence Upload Flow

Rules:

```txt
Upload area: large fc-surface-elevated glass panel
Primary CTA: fc-btn-primary, teal
File metadata: fc-text-faint minimum (55%)
Errors: clear, restrained — red semantic only
Progress: visible via progress bar, not animated borders
No sound for routine card reveals (sound system rules apply)
No massive entrance animations on agent cards
```

---

# 16. Analysis Progress Flow

Rules:

```txt
Show current phase first (pipeline phase label)
Show agent activity second (agent cards grid)
Hide verbose logs behind disclosure (expandable card)
Use teal for active analysis state
Use emerald only for completed checks
Use amber only for review/uncertainty
Use red only for failures or high-risk issues
```

Allowed live indicators:

```txt
Small status dot (w-1.5 to w-2 h-1.5 to h-2 rounded-full) with animate-pulse
Subtle progress bar linear movement
Readable status text with fc-text-faint
Opacity fade for card entrance
```

Banned live indicators:

```txt
animate-pulse on icons (Activity, ShieldAlert, etc.)
Large pulsing borders
Scan beam effects
Orbit animations
Constant shimmer
Entrance scale animations on agent cards
```

---

# 17. Sound Design

Sound must be functional, not decorative.

Allowed sound events:

```txt
Upload accepted
Analysis started
Checkpoint required
Analysis completed
Error/failure
Verdict ready
```

Banned sound events:

```txt
Page load (functional sounds only, no ambient noise on load)
Card reveal (agent cards appearing is not a sound trigger)
Hover
Tab switch
Routine animation
Decorative ambience without user control
```

Required:

```txt
Global mute/sound toggle
Sound setting persistence across sessions
App fully usable with sound disabled
No autoplay ambience without user consent
```

---

# 18. Motion System

## 18.1 Standard Transition

```css
.fc-transition {
  transition:
    background-color 160ms ease,
    border-color 160ms ease,
    color 160ms ease,
    box-shadow 160ms ease,
    opacity 160ms ease;
}
```

## 18.2 Allowed Motion

| Pattern                     | Spec                                                              |
|-----------------------------|-------------------------------------------------------------------|
| Page / section reveal       | `opacity: 0→1, y: 4→0, duration: 160ms, ease: easeOut`           |
| Card reveal                 | `opacity: 0→1, y: 4→0, duration: 160ms, ease: easeOut`           |
| Modal / overlay entrance    | `opacity: 0→1, y: 4→0, duration: 160ms, ease: easeOut` (no scale)|
| Accordion open/close        | `height: 0→auto, opacity: 0→1, duration: 200ms max`              |
| Button press feedback       | `whileTap: { scale: 0.98 }` only — no other scale usage          |
| Progress bar                | `width: 0→N%, duration: 200ms, ease: easeOut`                    |
| Status indicator dot        | `animate-pulse` allowed on `w-1.5/w-2 rounded-full` dots only    |
| Color/border hover          | `160ms ease` via `fc-transition`                                  |

## 18.3 Banned Motion

```txt
scale entrance/exit on any container, card, or modal
hover:scale-* or group-hover:scale-*
animate-pulse on icons, text, or containers
decorative pulsing borders
scan beam effects
orbit animations
spring (type: "spring") transitions
duration > 200ms for any entrance or exit
y offset > 4px on entrance
large parallax or translate effects
```

## 18.4 Transition Duration Reference

```txt
Interactive state (hover/focus): 150–160ms
Entrance animation:              160ms
Exit animation:                  160ms
Accordion:                       200ms max
Progress bar fill:               200ms
All other motion:                160ms
```

## 18.5 Reduced Motion

All Framer Motion animations must respect `useReducedMotion()`:

```tsx
const prefersReducedMotion = useReducedMotion();
initial={prefersReducedMotion ? false : { opacity: 0, y: 4 }}
```

Global CSS fallback in globals.css:

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
  }
}
```

---

# 19. Shadow Rules

## 19.1 Allowed Shadows

```txt
Depth shadows using rgba(0,0,0,*):     Always allowed — pure black is depth
fc-surface inset highlights:            Always allowed — part of glass material
fc-btn-primary ambient teal shadow:     Allowed — defined in canonical button spec
Focus ring:                             0 0 0 3px rgba(45,212,191,0.22) — allowed
```

## 19.2 Banned Shadows

```txt
Neon glow shadows on containers: shadow-[0_0_*px_rgba(<color>,*)] on cards/modals/panels
Neon glow shadows on icons:      shadow-[0_0_*px_rgba(<color>,*)] on icon wrappers
Hover-added glow shadows:        hover:shadow-[0_0_*]
Colored glow on badges:          Except canonical badge box-shadow (none by default)
```

The distinction: `shadow-[0_0_80px_-20px_rgba(0,0,0,0.8)]` is a **depth shadow** (black, allowed). `shadow-[0_0_30px_rgba(79,142,247,0.35)]` is a **neon glow** (colored, banned on containers).

The `fc-btn-primary` box shadow includes a teal glow component — this is pre-approved as part of the button system and is not a violation.

---

# 20. Accessibility Rules

Accessibility is mandatory.

## 20.1 Contrast

```txt
No readable text below 55% opacity
Placeholder text and decorative icons are exempt from the 55% rule
No text directly over busy backgrounds without a glass surface
Interactive labels must be readable at default state (not just on hover)
```

## 20.2 Focus

All interactive elements must have visible focus.

```css
:where(:focus-visible) {
  outline: none;
  box-shadow:
    0 0 0 6px rgba(79,142,247,0.18),
    0 0 0 2px rgba(94,234,212,0.60);
}
```

## 20.3 Touch Targets

```txt
Primary buttons:   44px minimum height
Secondary buttons: 40px minimum height
Icon buttons:      40px × 40px minimum
```

## 20.4 Color Independence

Every status must include at least one non-color cue:

```txt
Text label
Icon
Shape
Position
aria-label / aria-live
```

## 20.5 Forensic Data Rendering

Forensic strings — file names, SHA-256/MD5 hashes, MIME types, raw log output, URLs, and all user-submitted content — are variable-length and uncontrolled. They must never be allowed to dictate the width, height, or overflow behavior of a glass panel.

**Truncation rules:**

```txt
Evidence file names:    truncate (overflow hidden, text-overflow ellipsis, white-space nowrap)
Hash strings:           font-mono + break-all, or truncate with a visible copy-to-clipboard action
Raw string output:      break-words or break-all inside a max-height constrained scrollable container
URLs:                   break-all or truncate + full value in title attribute or tooltip on hover
MIME types / labels:    truncate — these can be arbitrarily long in malformed files
```

**Container constraints:**

```txt
Glass panels must use rigid width constraints (max-w-* or w-full within a constrained parent)
Glass panels with variable-length content must have explicit max-height on scrollable regions
Do not use min-content or fit-content as panel width when content is user-generated
All display containers for evidence strings must use overflow-hidden or overflow-x-auto — never overflow-visible
```

**Canonical hash display pattern:**

```tsx
<span className="font-mono text-xs fc-text-muted break-all select-all">
  {hash}
</span>
```

When truncation is preferred over line-breaking (e.g., inside a narrow card column):

```tsx
<span
  className="font-mono text-xs fc-text-muted truncate block max-w-[240px]"
  title={hash}
>
  {hash}
</span>
```

The `title` attribute is required on truncated hashes so investigators can read the full value on hover without expanding the layout.

---

# 21. Tailwind Usage Rules

## 21.1 Use System Tokens Over Arbitrary Values

Preferred over arbitrary:

| Arbitrary           | Use instead      |
|---------------------|------------------|
| `text-[10px]`       | `text-xs`        |
| `text-[11px]`       | `text-xs`        |
| `text-[13px]`       | `text-sm`        |
| `tracking-[0.18em]` | `tracking-wider` |
| `tracking-[0.3em]`  | `tracking-widest`|
| `gap-[5px]`         | `gap-1`          |
| `blur-[120px]`      | `blur-3xl`       |

## 21.2 Allowed Arbitrary Values

```txt
Exact opacity fractions: rgba values in style props for glass backgrounds
Layout constraints: w-[1px] for hair-line separators
Scroll behavior: scroll-margin, scroll-padding when needed
```

## 21.3 Discouraged Patterns

```txt
bg-white/[0.02]          → use bg-white/5 (≈0.020) or bg-white/[0.025] if needed
shadow-[0_0_*_rgba(*)]   → only allowed for the canonical button shadow
text-white/*             → use fc-text-* classes for all readable text
```

---

# 22. Class Inventory

The canonical class set. These are the only classes that should be used for major UI elements.

## Surfaces
```txt
fc-surface-solid      opaque anchor, no glass
fc-surface-quiet      subtle frosted glass (default card)
fc-surface            standard frosted glass
fc-surface-elevated   prominent frosted glass
fc-surface-overlay    maximum frosted glass (modals)
fc-surface-crisp      transparent with thin border (borderless sections)
```

## Text
```txt
fc-text-primary       98% white
fc-text-secondary     82% white
fc-text-muted         68% white
fc-text-faint         55% white (minimum for readable text)
fc-eyebrow            xs, semi-bold, letter-spaced label
```

## Buttons
```txt
fc-btn-primary
fc-btn-secondary
fc-btn-ghost
fc-btn-danger
```

## Badges
```txt
fc-badge
fc-badge-active
fc-badge-danger
fc-badge-warning
fc-badge-success
```

## Utilities
```txt
fc-input
fc-upload-zone
fc-modal-backdrop
fc-focus-ring
fc-transition
fc-agent-active
fc-agent-complete
fc-agent-error
```

**Legacy aliases that no longer exist (do not use):**
```txt
btn-primary           → fc-btn-primary
btn-horizon-primary   → fc-btn-primary
btn-premium           → fc-btn-primary
btn-outline           → fc-btn-secondary
btn-horizon-outline   → fc-btn-secondary
btn-ghost             → fc-btn-ghost
btn-danger            → fc-btn-danger
glass-panel           → fc-surface-quiet
premium-glass         → fc-surface-elevated
slick-frosted-card    → fc-surface-quiet
step-card             → fc-surface-quiet
```

---

# 23. Banned Patterns

The following are banned. A screen fails compliance if any of these appear.

**Text opacity** (on readable text):
```txt
text-white/10  text-white/15  text-white/20  text-white/25
text-white/30  text-white/35  text-white/40  text-white/45
text-white/50
```
Use `fc-text-faint` (55%) or higher. Exception: decorative icons, placeholder text, and status indicator dots.

**Motion:**
```txt
hover:scale-*
group-hover:scale-*
animate-pulse on icons, containers, or borders
type: "spring" in Framer Motion transitions
duration > 0.2 on entrances or exits
y: > 4 in motion initial/exit
scale in motion initial/exit on containers
```

**Visual style:**
```txt
uppercase Tailwind class (except real acronyms inline)
text-transform: uppercase in CSS
shadow-[0_0_*] on containers with colored rgba (neon glow)
hover:shadow-[0_0_*] on any element
```

**Typography:**
```txt
text-[10px]  text-[11px]  text-[13px]  (use system scale)
```

**Architecture:**
```txt
One-off surface styles (custom bg + border + blur outside surface classes)
One-off button styles (custom bg + text + border not matching a button class)
Nested <main> elements
Three or more backdrop-filter layers overlapping on the Z-axis (Rule of Two — see Section 6.8)
```

**Tooling Enforcement**

Banned patterns must be enforced by automated tooling, not solely by PR review. PR review alone is insufficient — violations accumulate. Required enforcement layer:

```txt
eslint-plugin-tailwindcss:
  - `forbiddenClassNames` rule — add all banned Tailwind utility names from this section
  - Flag text-white/* below /55 on non-exempt elements
  - Flag hover:scale-*, group-hover:scale-*, and animate-pulse on non-dot elements

Stylelint:
  - Disallow `text-transform: uppercase` in component CSS
  - Disallow `animation-duration` above 200ms
  - Custom plugin to warn on `backdrop-filter` used inside a selector that is itself
    a child of a backdrop-filter surface (nested blur detection)

CI gate:
  - Linting must pass before merge
  - Banned patterns in this section are lint errors, not warnings
  - No silent suppression — eslint-disable-next-line requires an inline comment
    explaining the documented exception
```

The rule configurations live in `.eslintrc` and `.stylelintrc` at the project root. If a banned pattern must be used for a documented exception, suppress it explicitly with a required comment — `// eslint-disable-next-line tailwindcss/no-restricted-classes -- [reason]` — never silently.

---

# 24. Layout Anchors

## 24.1 Fixed Navbar Offset

The global navbar is `position: fixed` with height `64px`.

The root layout's `<main>` always has `pt-16` applied. This is the **only** place the navbar offset is applied:

```tsx
// layout.tsx
<main className="flex-1 relative z-10 pt-16" id="main-content">
```

**Do not add per-page top padding to compensate for the navbar.** Use section-level padding (`py-10`, `py-14`) for internal spacing only.

## 24.2 Secondary Fixed Bars

If a page has its own secondary fixed bar (e.g., result page tab bar at `top-16`), that bar should be positioned at `top-16` and the page content should use `pt-N` within the page container — not on the root `<main>`.

---

# 25. Compliance Checklist

A screen is compliant only if all of the following are true:

**Surface:**
```txt
[ ] Uses only canonical fc-surface-* classes for all major containers
[ ] No one-off card or panel styles
[ ] Adjacent surface tiers differ by exactly one level
[ ] Maximum of two backdrop-filter layers overlap on the Z-axis at any time (Rule of Two)
[ ] Cards inside fc-surface-overlay modals use fc-surface-solid or a non-blurred fallback
```

**Typography:**
```txt
[ ] All readable text at or above fc-text-faint (55%)
[ ] No text-white/* below /55 on readable text
[ ] No text-[10px], text-[11px], or text-[13px]
[ ] No uppercase class on labels
[ ] Eyebrows use fc-eyebrow class
```

**Buttons and Badges:**
```txt
[ ] All primary actions use fc-btn-primary
[ ] All supporting actions use fc-btn-secondary or fc-btn-ghost
[ ] All destructive actions use fc-btn-danger
[ ] No custom button styles outside the canonical classes
[ ] All badges use fc-badge-* classes
```

**Motion:**
```txt
[ ] No scale in container/card/modal entrances or exits
[ ] No hover:scale-* or group-hover:scale-*
[ ] No animate-pulse on icons or containers
[ ] No spring transitions
[ ] All durations ≤ 200ms (entrances: 160ms)
[ ] All y offsets ≤ 4px
[ ] Reduced motion respected
```

**Shadows:**
```txt
[ ] No neon glow box shadows on containers
[ ] No hover-added colored glow shadows
[ ] Depth shadows (rgba(0,0,0,*)) are allowed
```

**Color:**
```txt
[ ] Teal used only for action/active/focus
[ ] Semantic colors (red/amber/emerald) used only for meaning
[ ] No semantic radial glows as decoration
```

**Accessibility:**
```txt
[ ] Visible focus ring on all interactive elements
[ ] Touch targets ≥ 40px
[ ] Status communicated by text/icon, not color alone
[ ] Screen fully usable with sound disabled
[ ] Reduced motion respected
[ ] Text inside fc-surface-elevated or fc-surface-overlay uses fc-text-muted (68%) minimum for readable content
[ ] All evidence strings (hashes, file names, URLs) are truncated or break-all — no layout-breaking overflow
[ ] Hash display containers use overflow-hidden or overflow-x-auto, not overflow-visible
```

**Print/Export:**
```txt
[ ] Print/PDF export sets data-print-mode="true" on <html> before triggering export
[ ] All fc-surface-* classes render as white (#ffffff) with backdrop-filter: none in print mode
[ ] All fc-text-* classes render as dark readable values in print mode
[ ] Teal accent converts to #0f766e (high-contrast printable) in print mode
[ ] No glass borders, glows, or blur artifacts visible in exported PDF
```

**Layout:**
```txt
[ ] Root <main> has pt-16 (no per-page navbar compensation)
[ ] No nested <main> elements
[ ] No py-32 or larger section padding on app pages
```

---

# 26. Verification Gates

Before considering a UI pass complete:

## 26.1 Visual Consistency

```txt
All cards share the same glass language
All modals use fc-surface-overlay + opacity/y entrance
All buttons use canonical button classes
All major UI elements have rounded edges
Primary actions are teal pill buttons
Secondary actions are neutral glass pill buttons
```

## 26.2 Readability

```txt
No readable text below 55% opacity
No low-contrast labels
No text lost on glass backgrounds
No overly transparent panels behind important content
```

## 26.3 Interaction

```txt
Buttons have clear hover/focus/active/disabled states
Hover never moves or scales elements (except whileTap: 0.98)
Focus state is visible (teal ring)
Disabled state is obvious (opacity 0.48)
Touch targets are large enough
```

## 26.4 Motion

```txt
No decorative pulse on icons or containers
No scan beams, orbit effects
No spring entrances
No scale entrances on containers
Reduced motion works
```

## 26.5 Sound

```txt
No sound on page load
No sound on card reveal
No sound on hover or tab switch
Sound only fires for meaningful state changes
Mute toggle exists and persists
```

## 26.6 Print and PDF Export

```txt
Trigger export with data-print-mode="true" set on <html>
All glass surfaces render as white panels with black text
No backdrop-filter artifacts in the exported file
Teal accents are readable (#0f766e on white)
Verdict, evidence identity, hash, and confidence score are all visible and legible
Layout does not break or overflow on A4/Letter page width
data-print-mode attribute is removed after the export dialog closes
```

---

# 27. Final Design Rule

The product should feel like a premium forensic glass workstation.

Every screen should look like it belongs to the same system.

The final UI should be:

```txt
Glass-first
Teal-accented
Pill-shaped
Readable
Restrained
Modern
Slick
Court-grade
Consistent
```

The app must never sacrifice clarity for visual effects.

> Transparency is for depth. Teal is for action. Glass is the material. Evidence is the focus.

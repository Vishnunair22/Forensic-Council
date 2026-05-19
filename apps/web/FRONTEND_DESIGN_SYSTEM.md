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

These rules are mandatory.

## 3.1 Readability

Text must always be readable.

Never place important text directly over busy visuals without a dark glass surface behind it.

Minimum text opacity:

```txt
Primary text: 96–100%
Secondary text: 78–86%
Muted text: 62–72%
Faint text: 55% minimum
```

Text opacity below `55%` is banned for readable UI text.

## 3.2 Glass Consistency

All major UI containers must use the canonical glass surface system.

Do not create one-off card styles with random borders, shadows, and background opacity values.

## 3.3 Rounded Shape Language

The app uses soft rounded geometry.

Required shape language:

```txt
Cards: rounded-2xl or rounded-3xl
Modals: rounded-3xl
Buttons: rounded-full pill shape
Badges: rounded-full
Input fields: rounded-2xl or rounded-full depending on context
Panels/docks: rounded-2xl or rounded-3xl
```

Sharp corners are not allowed.

## 3.4 Case Rules

Forced uppercase is banned.

Allowed:

```txt
Title Case labels
Sentence case descriptions
Real acronyms: AI, PDF, API, SHA, MIME, URL
```

Banned:

```txt
text-transform: uppercase
uppercase Tailwind class
Tracking-heavy all-caps labels
Fake terminal labels
```

## 3.5 Motion

Motion must be subtle and functional.

Allowed:

```txt
Opacity fade
Tiny y movement: 4px max
Modal scale: 0.98 to 1
Short transition duration: 120–180ms
```

Banned:

```txt
Hover lift
Hover scale
Decorative pulse
Scan beams
Orbit animation
Excessive shimmer
Springy card entrances
Large sliding animations
```

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
Red: danger, destructive action, deception, severe risk
Amber: caution, uncertainty, review needed
Emerald: verified, authentic, complete
Blue: information or neutral process only if needed
```

Semantic colors must not be used as decorative glows.

---

# 4. Color System

## 4.1 Base Background

The app uses a dark forensic background.

Recommended tokens:

```css
:root {
  --fc-bg-root: #02040a;
  --fc-bg-deep: #030712;
  --fc-bg-panel: rgba(8, 13, 24, 0.72);
  --fc-bg-panel-strong: rgba(10, 16, 30, 0.86);
}
```

## 4.2 Text Tokens

```css
:root {
  --fc-text-primary: rgba(255, 255, 255, 0.98);
  --fc-text-secondary: rgba(255, 255, 255, 0.82);
  --fc-text-muted: rgba(255, 255, 255, 0.68);
  --fc-text-faint: rgba(255, 255, 255, 0.56);
}
```

Usage:

```txt
Primary: page titles, card titles, key numbers, verdicts
Secondary: normal body text, labels, descriptions
Muted: metadata, helper text
Faint: timestamps, non-critical chrome text
```

Do not use text below `rgba(255,255,255,0.55)`.

## 4.3 Teal Brand Accent

Teal is the main product action color.

```css
:root {
  --fc-teal-950: #052f35;
  --fc-teal-900: #073f46;
  --fc-teal-800: #07545c;
  --fc-teal-700: #0f766e;
  --fc-teal-600: #0f9f9a;
  --fc-teal-500: #14b8a6;
  --fc-teal-400: #2dd4bf;
  --fc-teal-300: #5eead4;

  --fc-teal-soft: rgba(20, 184, 166, 0.12);
  --fc-teal-border: rgba(94, 234, 212, 0.42);
  --fc-teal-glow: rgba(45, 212, 191, 0.18);
}
```

## 4.4 Semantic Colors

```css
:root {
  --fc-danger: #ef4444;
  --fc-danger-soft: rgba(239, 68, 68, 0.10);
  --fc-danger-border: rgba(248, 113, 113, 0.34);

  --fc-warning: #f59e0b;
  --fc-warning-soft: rgba(245, 158, 11, 0.10);
  --fc-warning-border: rgba(251, 191, 36, 0.34);

  --fc-success: #10b981;
  --fc-success-soft: rgba(16, 185, 129, 0.10);
  --fc-success-border: rgba(52, 211, 153, 0.34);
}
```

---

# 5. Typography System

## 5.1 Font Behavior

Typography should feel clean, precise, and readable.

Use strong hierarchy, not decorative effects.

## 5.2 Text Classes

```css
.fc-text-primary {
  color: var(--fc-text-primary);
}

.fc-text-secondary {
  color: var(--fc-text-secondary);
}

.fc-text-muted {
  color: var(--fc-text-muted);
}

.fc-text-faint {
  color: var(--fc-text-faint);
}
```

## 5.3 Eyebrow Labels

Eyebrows are allowed, but they must not be forced uppercase.

```css
.fc-eyebrow {
  color: var(--fc-text-muted);
  font-size: 0.75rem;
  line-height: 1rem;
  font-weight: 600;
  letter-spacing: 0.04em;
}
```

Banned:

```css
text-transform: uppercase;
```

## 5.4 Headings

Recommended hierarchy:

```txt
Page title: text-4xl to text-6xl
Section title: text-2xl to text-3xl
Card title: text-lg to text-xl
Body: text-sm to text-base
Metadata: text-xs to text-sm
```

Avoid excessive arbitrary text sizes like:

```txt
text-[10px]
text-[11px]
text-[13px]
md:text-[80px]
```

---

# 6. Surface System

All cards, panels, modals, upload zones, docks, and agent containers must use canonical surface classes.

## 6.1 Base Glass Surface

```css
.fc-surface {
  position: relative;
  border-radius: 1.5rem;
  border: 1px solid rgba(255, 255, 255, 0.13);
  background:
    linear-gradient(
      180deg,
      rgba(255, 255, 255, 0.075),
      rgba(255, 255, 255, 0.035)
    ),
    rgba(8, 13, 24, 0.70);
  backdrop-filter: blur(22px) saturate(135%);
  -webkit-backdrop-filter: blur(22px) saturate(135%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.12),
    0 18px 44px rgba(0, 0, 0, 0.28);
}
```

## 6.2 Quiet Surface

Use for normal cards.

```css
.fc-surface-quiet {
  border-radius: 1.5rem;
  border: 1px solid rgba(255, 255, 255, 0.11);
  background:
    linear-gradient(
      180deg,
      rgba(255, 255, 255, 0.060),
      rgba(255, 255, 255, 0.030)
    ),
    rgba(8, 13, 24, 0.64);
  backdrop-filter: blur(18px) saturate(125%);
  -webkit-backdrop-filter: blur(18px) saturate(125%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.09),
    0 12px 30px rgba(0, 0, 0, 0.22);
}
```

## 6.3 Elevated Surface

Use for important panels, result cards, agent groups, and upload containers.

```css
.fc-surface-elevated {
  border-radius: 1.75rem;
  border: 1px solid rgba(255, 255, 255, 0.15);
  background:
    linear-gradient(
      180deg,
      rgba(255, 255, 255, 0.085),
      rgba(255, 255, 255, 0.040)
    ),
    rgba(8, 13, 24, 0.76);
  backdrop-filter: blur(24px) saturate(145%);
  -webkit-backdrop-filter: blur(24px) saturate(145%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.14),
    inset 0 -1px 0 rgba(255, 255, 255, 0.045),
    0 22px 56px rgba(0, 0, 0, 0.34);
}
```

## 6.4 Overlay Surface

Use for modals, command panels, and blocking overlays.

```css
.fc-surface-overlay {
  border-radius: 2rem;
  border: 1px solid rgba(255, 255, 255, 0.18);
  background:
    linear-gradient(
      180deg,
      rgba(255, 255, 255, 0.105),
      rgba(255, 255, 255, 0.050)
    ),
    rgba(5, 10, 20, 0.88);
  backdrop-filter: blur(30px) saturate(155%);
  -webkit-backdrop-filter: blur(30px) saturate(155%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.18),
    inset 0 -1px 0 rgba(255, 255, 255, 0.06),
    0 30px 80px rgba(0, 0, 0, 0.48);
}
```

## 6.5 Light Reflection Rule

Glass panels may include a subtle top highlight.

Allowed:

```css
.fc-glass-highlight::before {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
  background:
    linear-gradient(
      180deg,
      rgba(255, 255, 255, 0.12),
      rgba(255, 255, 255, 0.00) 42%
    );
}
```

Reflection must be subtle. It must not make text harder to read.

---

# 7. Button System

Buttons must be pill-shaped.

The app uses four button types:

```txt
Primary
Secondary
Ghost
Danger
```

## 7.1 Primary Button

Primary buttons use deep teal frosted glass.

Use for:

```txt
Begin Analysis
Upload Evidence
Continue
Start Review
Confirm
Generate Report
View Result
Proceed
```

Primary button behavior:

```txt
Default: deep teal glass pill
Hover: more transparent teal glass with brighter border
Active: darker pressed teal
Disabled: muted transparent glass
```

CSS:

```css
.fc-btn-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;

  min-height: 44px;
  padding: 0 22px;
  border-radius: 999px;

  background:
    linear-gradient(
      180deg,
      rgba(20, 184, 166, 0.24),
      rgba(7, 84, 92, 0.42)
    );

  color: rgba(240, 253, 250, 0.96);
  border: 1px solid rgba(94, 234, 212, 0.46);

  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.16),
    inset 0 -1px 0 rgba(45, 212, 191, 0.12),
    0 14px 36px rgba(0, 0, 0, 0.34),
    0 0 28px rgba(45, 212, 191, 0.14);

  font-size: 0.875rem;
  font-weight: 700;
  letter-spacing: 0.01em;

  transition:
    background-color 160ms ease,
    border-color 160ms ease,
    color 160ms ease,
    box-shadow 160ms ease;
}

.fc-btn-primary:hover {
  background:
    linear-gradient(
      180deg,
      rgba(20, 184, 166, 0.12),
      rgba(7, 84, 92, 0.22)
    );

  color: rgba(255, 255, 255, 0.98);
  border-color: rgba(94, 234, 212, 0.72);

  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.18),
    0 12px 32px rgba(0, 0, 0, 0.30),
    0 0 34px rgba(45, 212, 191, 0.20);
}

.fc-btn-primary:active {
  background:
    linear-gradient(
      180deg,
      rgba(15, 118, 110, 0.22),
      rgba(5, 47, 53, 0.42)
    );
  border-color: rgba(94, 234, 212, 0.52);
}

.fc-btn-primary:disabled {
  cursor: not-allowed;
  opacity: 0.48;
  box-shadow: none;
}
```

## 7.2 Secondary Button

Secondary buttons are neutral glass pills with teal only on hover/focus.

Use for:

```txt
Back
Cancel
View Details
Download
Open Timeline
Switch Tab
Copy
Secondary navigation actions
```

CSS:

```css
.fc-btn-secondary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;

  min-height: 40px;
  padding: 0 18px;
  border-radius: 999px;

  background:
    linear-gradient(
      180deg,
      rgba(255, 255, 255, 0.075),
      rgba(255, 255, 255, 0.035)
    );

  color: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(255, 255, 255, 0.16);

  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.10),
    0 10px 26px rgba(0, 0, 0, 0.20);

  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);

  font-size: 0.875rem;
  font-weight: 650;

  transition:
    background-color 160ms ease,
    border-color 160ms ease,
    color 160ms ease,
    box-shadow 160ms ease;
}

.fc-btn-secondary:hover {
  background:
    linear-gradient(
      180deg,
      rgba(20, 184, 166, 0.12),
      rgba(15, 118, 110, 0.075)
    );

  color: rgba(240, 253, 250, 0.96);
  border-color: rgba(94, 234, 212, 0.38);

  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.13),
    0 10px 26px rgba(0, 0, 0, 0.22);
}

.fc-btn-secondary:disabled {
  cursor: not-allowed;
  opacity: 0.48;
}
```

## 7.3 Ghost Button

Ghost buttons are for low-priority actions.

Use for:

```txt
Dismiss
Learn More
Expand
Collapse
Minor filters
Inline actions
Utility actions
```

CSS:

```css
.fc-btn-ghost {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;

  min-height: 38px;
  padding: 0 14px;
  border-radius: 999px;

  background: transparent;
  color: rgba(255, 255, 255, 0.68);
  border: 1px solid transparent;

  font-size: 0.875rem;
  font-weight: 600;

  transition:
    background-color 160ms ease,
    border-color 160ms ease,
    color 160ms ease;
}

.fc-btn-ghost:hover {
  background: rgba(20, 184, 166, 0.07);
  color: rgba(240, 253, 250, 0.96);
  border-color: rgba(94, 234, 212, 0.20);
}
```

## 7.4 Danger Button

Danger buttons are restrained red glass.

Use for:

```txt
Delete
Remove Evidence
Clear Session
Reject
Reset
Destructive confirmation
```

CSS:

```css
.fc-btn-danger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;

  min-height: 40px;
  padding: 0 18px;
  border-radius: 999px;

  background: rgba(239, 68, 68, 0.08);
  color: rgba(254, 202, 202, 0.94);
  border: 1px solid rgba(248, 113, 113, 0.28);

  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.08),
    0 10px 26px rgba(0, 0, 0, 0.20);

  font-size: 0.875rem;
  font-weight: 650;

  transition:
    background-color 160ms ease,
    border-color 160ms ease,
    color 160ms ease;
}

.fc-btn-danger:hover {
  background: rgba(239, 68, 68, 0.14);
  color: rgba(255, 235, 235, 0.98);
  border-color: rgba(248, 113, 113, 0.48);
}
```

## 7.5 Button Mapping

```txt
Primary = teal command
Secondary = neutral glass support
Ghost = quiet utility
Danger = destructive action
```

Examples:

| Action             | Button Type                                    |
| ------------------ | ---------------------------------------------- |
| Begin Analysis     | Primary                                        |
| Upload Evidence    | Primary                                        |
| Continue           | Primary                                        |
| Generate Report    | Primary                                        |
| Confirm Checkpoint | Primary                                        |
| Back               | Secondary                                      |
| Cancel             | Secondary                                      |
| View Details       | Secondary                                      |
| Download Report    | Secondary or Primary depending on page context |
| Copy Link          | Ghost                                          |
| Dismiss            | Ghost                                          |
| Expand Details     | Ghost                                          |
| Remove Evidence    | Danger                                         |
| Clear Session      | Danger                                         |

---

# 8. Badge and Status System

Badges must be rounded pills.

## 8.1 Neutral Badge

```css
.fc-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;

  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;

  background: rgba(255, 255, 255, 0.065);
  color: rgba(255, 255, 255, 0.74);
  border: 1px solid rgba(255, 255, 255, 0.12);

  font-size: 0.75rem;
  font-weight: 650;
}
```

## 8.2 Active Badge

```css
.fc-badge-active {
  background: rgba(20, 184, 166, 0.11);
  color: rgba(204, 251, 241, 0.96);
  border-color: rgba(94, 234, 212, 0.34);
}
```

## 8.3 Danger Badge

```css
.fc-badge-danger {
  background: rgba(239, 68, 68, 0.10);
  color: rgba(254, 202, 202, 0.96);
  border-color: rgba(248, 113, 113, 0.34);
}
```

## 8.4 Warning Badge

```css
.fc-badge-warning {
  background: rgba(245, 158, 11, 0.10);
  color: rgba(253, 230, 138, 0.96);
  border-color: rgba(251, 191, 36, 0.34);
}
```

## 8.5 Success Badge

```css
.fc-badge-success {
  background: rgba(16, 185, 129, 0.10);
  color: rgba(187, 247, 208, 0.96);
  border-color: rgba(52, 211, 153, 0.34);
}
```

---

# 9. Modals

All modals must use the overlay glass surface.

Modal requirements:

```txt
Use fc-surface-overlay
rounded-3xl or 2rem radius
Clear title
Readable body text
Primary action on the right
Secondary/cancel action on the left
No excessive glow
No low-contrast text
No forced uppercase
```

Modal backdrop:

```css
.fc-modal-backdrop {
  background:
    radial-gradient(
      circle at top,
      rgba(20, 184, 166, 0.08),
      transparent 34%
    ),
    rgba(0, 0, 0, 0.58);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}
```

Modal motion:

```txt
Opacity 0 to 1
Scale 0.98 to 1
Duration 140–160ms
No bounce
No spring
```

---

# 10. Agent Cards

Agent cards must look like modern frosted glass panels.

Each agent card should include:

```txt
Agent name
Short role
Current status
Confidence/progress if available
Expandable details only when needed
```

Agent card rules:

```txt
Use fc-surface-quiet or fc-surface-elevated
Use rounded-2xl or rounded-3xl
Use teal only for active/running state
Use semantic colors only for actual state
Avoid decorative glowing borders
Avoid terminal-style uppercase labels
Avoid too many nested boxes
```

Active agent state:

```css
.fc-agent-active {
  border-color: rgba(94, 234, 212, 0.38);
  background:
    linear-gradient(
      180deg,
      rgba(20, 184, 166, 0.08),
      rgba(255, 255, 255, 0.035)
    ),
    rgba(8, 13, 24, 0.72);
}
```

Completed agent state:

```css
.fc-agent-complete {
  border-color: rgba(52, 211, 153, 0.30);
}
```

Failed agent state:

```css
.fc-agent-error {
  border-color: rgba(248, 113, 113, 0.34);
}
```

---

# 11. Inputs and Upload Areas

Inputs and upload zones must also follow the glass system.

## 11.1 Input

```css
.fc-input {
  min-height: 44px;
  border-radius: 1rem;
  padding: 0 14px;

  background: rgba(255, 255, 255, 0.055);
  border: 1px solid rgba(255, 255, 255, 0.14);
  color: rgba(255, 255, 255, 0.96);

  outline: none;
  transition:
    border-color 160ms ease,
    background-color 160ms ease,
    box-shadow 160ms ease;
}

.fc-input::placeholder {
  color: rgba(255, 255, 255, 0.55);
}

.fc-input:focus {
  border-color: rgba(94, 234, 212, 0.52);
  background: rgba(20, 184, 166, 0.055);
  box-shadow: 0 0 0 3px rgba(45, 212, 191, 0.12);
}
```

## 11.2 Upload Zone

Upload zones should feel like large elevated glass panels.

```css
.fc-upload-zone {
  border-radius: 2rem;
  border: 1px dashed rgba(94, 234, 212, 0.34);
  background:
    linear-gradient(
      180deg,
      rgba(20, 184, 166, 0.08),
      rgba(255, 255, 255, 0.035)
    ),
    rgba(8, 13, 24, 0.72);
  backdrop-filter: blur(24px) saturate(145%);
  -webkit-backdrop-filter: blur(24px) saturate(145%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.12),
    0 18px 44px rgba(0, 0, 0, 0.28);
}

.fc-upload-zone:hover {
  border-color: rgba(94, 234, 212, 0.58);
  background:
    linear-gradient(
      180deg,
      rgba(20, 184, 166, 0.12),
      rgba(255, 255, 255, 0.04)
    ),
    rgba(8, 13, 24, 0.76);
}
```

---

# 12. Navigation and Docks

Navigation must be glassy but quiet.

## 12.1 Global Navbar

Rules:

```txt
Use frosted glass
Keep height consistent
Avoid heavy glow
Use readable text
Use teal only for active page or primary action
No uppercase nav labels
```

## 12.2 Action Dock

Action docks must use elevated glass and pill buttons.

Rules:

```txt
Use fc-surface-elevated
No massive shadows
No excessive blur
Primary action must be visually dominant
Secondary actions must be neutral glass
Mobile layout must preserve tap targets
```

Minimum tap target:

```txt
44px for primary actions
40px minimum for secondary actions
```

---

# 13. Result Page

The result page must be evidence-first.

Hierarchy:

```txt
1. Verdict
2. Evidence identity
3. Confidence and integrity
4. Intelligence brief
5. Key findings
6. Agent details
7. Timeline and technical metadata
```

Result page rules:

```txt
Verdict should be clear immediately
Detailed analysis should be progressive
Avoid overwhelming the user with all agent logs at once
Use glass cards but avoid too many nested glass boxes
Semantic colors must map to actual forensic meaning
```

Verdict color mapping:

```txt
Authentic / verified: emerald
Manipulated / deceptive: red
Uncertain / inconclusive: amber
Processing / active: teal
```

---

# 14. Landing Page

The landing page should feel premium, modern, and trustworthy.

Rules:

```txt
Use frosted glass sections
Use teal CTA
Avoid white primary buttons
Avoid excessive radial glows
Avoid cyber/HUD styling
No forced uppercase
Keep hero text readable
Keep background subtle
```

The landing page can be more atmospheric than the app workspace, but it must still share the same material system.

---

# 15. Evidence Upload Flow

The upload flow should feel procedural and controlled.

Rules:

```txt
Upload area must be a large glass surface
Primary action must be teal
File metadata must be readable
Errors must be clear and restrained
Progress must be visible but not chaotic
Do not play sounds for routine card reveals
Do not overload the page with agent details too early
```

---

# 16. Analysis Progress Flow

The analysis flow should feel active but not noisy.

Rules:

```txt
Show current phase first
Show agent activity second
Hide verbose logs behind disclosure
Use teal for active analysis
Use emerald only for completed checks
Use amber only for review/uncertainty
Use red only for failures or high-risk issues
```

Allowed live indicators:

```txt
Small status dot
Subtle progress bar
Readable status text
```

Banned live indicators:

```txt
Large pulsing glows
Scan beams
Orbit effects
Constant shimmer
Excessive animated borders
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
Page load
Card reveal
Hover
Tab switch
Routine animation
Decorative ambience without user control
```

Required:

```txt
Global mute/sound toggle
Sound setting persistence
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

```txt
Page reveal: opacity + y 4px
Card reveal: opacity only or y 4px
Modal reveal: opacity + scale 0.98
Progress: subtle linear movement
Hover: color, border, background, shadow only
```

## 18.3 Banned Motion

```txt
hover:-translate-y
hover:scale-*
animate-pulse for decoration
animate-spin except true loading
scan beam effects
orbit effects
large parallax
spring bounce
```

## 18.4 Reduced Motion

All motion must respect reduced motion.

```css
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
    scroll-behavior: auto !important;
  }
}
```

---

# 19. Accessibility Rules

Accessibility is mandatory.

## 19.1 Contrast

```txt
Text must stay readable on glass
No important text below 55% opacity
No text directly over busy backgrounds
Interactive labels must be clear
```

## 19.2 Focus

All interactive elements must have visible focus.

```css
.fc-focus-ring:focus-visible {
  outline: none;
  box-shadow:
    0 0 0 3px rgba(45, 212, 191, 0.22),
    0 0 0 1px rgba(94, 234, 212, 0.58);
}
```

## 19.3 Touch Targets

```txt
Primary buttons: 44px minimum height
Secondary buttons: 40px minimum height
Icon buttons: 40px minimum square
```

## 19.4 Color Independence

Do not rely on color alone.

Every status must include at least one of:

```txt
Text label
Icon
Shape
Position
Accessible label
```

---

# 20. Component Inventory

The app should be built from these canonical primitives:

```txt
AppShell
Surface
Button
Badge
StatusPill
SectionHeader
MetricCard
AgentCard
ProgressIndicator
DisclosurePanel
Modal
Toast
Input
UploadZone
ActionDock
Tabs
```

Do not create one-off visual systems for individual pages.

---

# 21. Banned Patterns

The following are banned unless explicitly justified:

```txt
Forced uppercase
text-white/20
text-white/25
text-white/30
text-white/35
text-white/40
text-white/45
text-white/50
opacity below 55% on readable text
hover:-translate-y
hover:scale-*
decorative animate-pulse
scan beam animation
orbit animation
large neon glows
semantic radial glows
random card styles
random button styles
sharp corners
white primary CTA buttons
blue/purple SaaS CTA buttons
terminal-style labels
excessive tracking
```

---

# 22. Tailwind Usage Rules

Avoid arbitrary values unless necessary.

Discouraged:

```txt
text-[10px]
text-[11px]
text-[13px]
tracking-[0.3em]
gap-[5px]
blur-[120px]
shadow-[0_0_*]
bg-white/[0.02]
```

Preferred:

```txt
text-xs
text-sm
text-base
tracking-normal
tracking-wide
gap-1
gap-2
gap-3
rounded-2xl
rounded-3xl
```

Arbitrary values are allowed only for:

```txt
Highly specific visual tuning
One-off layout constraints
Documented exceptions
```

---

# 23. Implementation Classes

At minimum, the frontend should expose these classes:

```txt
fc-text-primary
fc-text-secondary
fc-text-muted
fc-text-faint

fc-surface
fc-surface-quiet
fc-surface-elevated
fc-surface-overlay
fc-glass-highlight

fc-btn-primary
fc-btn-secondary
fc-btn-ghost
fc-btn-danger

fc-badge
fc-badge-active
fc-badge-danger
fc-badge-warning
fc-badge-success

fc-input
fc-upload-zone
fc-focus-ring
fc-transition
```

---

# 24. Migration Checklist

A screen is compliant only if:

```txt
It uses canonical surface classes
It uses canonical button classes
It uses canonical badge/status classes
It uses approved text opacity levels
It has no forced uppercase
It has no hover lift
It has no hover scale
It has no decorative pulse
It has no scan/orbit effects
It uses teal only for action/active/focus states
It uses semantic colors only for semantic meaning
It remains readable with glass enabled
It remains usable with sound disabled
It respects reduced motion
It has visible keyboard focus
```

---

# 25. Verification Gates

Before considering a UI pass complete, verify:

## 25.1 Visual Consistency

```txt
All cards share the same glass language
All modals share the same overlay style
All buttons use the canonical button system
All major UI elements have rounded edges
Primary actions are teal pill buttons
Secondary actions are neutral glass pill buttons
```

## 25.2 Readability

```txt
No readable text below 55% opacity
No low-contrast metadata
No text lost on glass backgrounds
No overly transparent panels behind important content
```

## 25.3 Interaction

```txt
Buttons have clear hover/focus/active states
Hover does not move or scale elements
Focus state is visible
Disabled state is obvious
Touch targets are large enough
```

## 25.4 Motion

```txt
No decorative pulse
No scan beams
No orbit effects
No springy entrances
Reduced motion works
```

## 25.5 Sound

```txt
No sound on page load
No sound on card reveal
No sound on hover
Sound only fires for meaningful state changes
Mute toggle exists and persists
```

---

# 26. Final Design Rule

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

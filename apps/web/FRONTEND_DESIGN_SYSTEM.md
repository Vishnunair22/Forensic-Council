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
- glassy but highly readable
- calm under pressure

The app must NOT feel like:
- a crypto dashboard
- a hacker terminal
- a sci-fi HUD
- a gaming interface
- a generic SaaS admin panel

The core visual language is: **Precision Frosted Glass**

Glass is used for depth, hierarchy, and cohesion, never for mere decoration. **Readability always wins over transparency.**

---

## 2. Automated Enforcement (The CI/CD Gate)

This design system is enforced mechanically via **ESLint** (`eslint.config.mjs`). Human PR reviews are insufficient to prevent UI drift. The `lint` script runs `eslint src --max-warnings 0`, so every rule below — though registered at `warn` severity — fails CI on any violation.

### 2.1 ESLint Strict Utility Constraints
The live rules are in [`eslint.config.mjs`](./eslint.config.mjs) under the `no-restricted-syntax` block; they lint `className` Literal values in JSX. They physically prevent code that breaks the aesthetic or accessibility guidelines. The set currently enforced:

- Scale transforms (`hover:scale-*`, `group-hover:scale-*`, `active:scale-*`) — banned.
- Inline `backdrop-blur-*` — banned (use `fc-surface-*`).
- `bg-black/X` washes — banned (use surface tokens).
- `text-white/X` opacity classes — banned (use `fc-text-*`).
- Micro font sizes `text-[10px|11px|13px]` — banned (use the `fc-eyebrow`/`text-xs`/`text-sm` scale).
- Colored neon `textShadow`/`boxShadow` (non-`rgba(0,0,0,X)`) — banned.

The illustrative form below shows the intent of these selectors:

```javascript
// eslint.config.mjs - Design System Enforcement
"no-restricted-syntax": [
  "error",
  {
    // Block micro-typography
    "selector": "Literal[value=/\\btext-\\[(10px|11px|13px)\\]\\b/]",
    "message": "[Design System]: Arbitrary micro-text is banned. Use text-xs (12px) or text-sm (14px)."
  },
  {
    // Block low-contrast text traps
    "selector": "Literal[value=/(?<!fc-)text-white\\/(10|15|20|25|30|35|40|45|50)\\b/]",
    "message": "[Design System]: Text opacity below 55% is banned. Use fc-text-faint (55%) or fc-text-muted (68%)."
  },
  {
    // Block animation soup (scale/spring)
    "selector": "Literal[value=/\\b(hover:scale-|group-hover:scale-|duration-(?!150|200)\\d+)\\b/]",
    "message": "[Design System]: Scale animations on hover and non-canonical durations are banned. Use fc-transition."
  },
  {
    // Block inline glass material hacking
    "selector": "Literal[value=/\\bbackdrop-blur-(?!none)\\b/]",
    "message": "[Design System]: Inline backdrop-blur is banned to prevent Z-axis overlap violations. Use predefined fc-surface-* components."
  }
]
```

### 2.2 Component Encapsulation
Do not use raw utility classes to build common elements. You must use the React components (`<GlassPanel variant="quiet">`, `<Badge variant="danger">`) to ensure global CSS updates apply everywhere instantly.

---

## 3. Accessibility & Typography System

### 3.1 The Glass Contrast Trap
Text rendered at 55% opacity (`fc-text-faint`) passes WCAG on a solid black background. However, when placed inside a frosted glass card (`fc-surface-elevated`), the blur dynamically pulls in lighter colors from the background, destroying the contrast ratio.

**Rule:** Text rendered inside ANY glass surface (`fc-surface-quiet`, `fc-surface-elevated`, `fc-surface-overlay`) MUST use `fc-text-muted` (68%) as the readable minimum. `fc-text-faint` is reserved strictly for non-readable decorative chrome or text outside of glass panels.

### 3.2 Canonical Text Classes
Do not use raw `text-white/X` combinations. Use these defined variables:

```
fc-text-primary   → 98% (Page titles, verdicts, key metrics)
fc-text-secondary → 82% (Standard body text, form labels)
fc-text-muted     → 68% (Metadata, helper text, minimum for glass interiors)
fc-text-faint     → 55% (Timestamps on dark bg, non-critical chrome ONLY)
fc-text-danger    → Semantic red for inline error messages only
```

### 3.3 Base Typography Scale
The app utilizes Inter for UI elements and JetBrains Mono for forensic data.
Micro-typography is explicitly banned.

```
Page title:      text-3xl to text-5xl
Card title:      text-lg to text-xl
Body:            text-sm to text-base (NEVER text-xs for body text)
Metadata:        text-xs
```

### 3.4 Line Height and Width
Dense forensic prose requires breathing room.

Paragraphs must use `leading-relaxed` (1.625).

Prose containers must be restricted to `max-w-[68ch]` for optimal eye-tracking.

**Uppercase is reserved for micro-labels only.** It is permitted *exclusively* on
≤12px mono/eyebrow kickers and the `.fc-label` primitive (data-adjacent section
titles, column headers, status chips). It is **banned** on body copy, headings,
buttons, and any label ≥14px — those use Title Case. This keeps the
court-grade tone and avoids the "shouty HUD" look.

---

## 4. The Material System: Rule of Two

`backdrop-filter` forces a GPU compositing layer. Overlapping blurs degrade framerate and look muddy.

**The Rule of Two:** A maximum of two `backdrop-filter` surfaces may overlap on the Z-axis at any time.

### 4.1 Canonical Surfaces
Always use the lowest tier surface possible.

- `fc-surface-solid` (Level 0 - No Blur): Backgrounds, tooltips, popovers. (Tooltips MUST be solid because they can appear over modals).
- `fc-surface-quiet` (Level 1): Subtle glass for list items, standard agent cards.
- `fc-surface` (Level 1): Standard frosted glass for primary feature cards.
- `fc-surface-elevated` (Level 1): Prominent glass for critical result cards or action docks.
- `fc-surface-overlay` (Level 2): Maximum frost, strictly reserved for Modals.

**Note:** If a component (like an input or card) is placed inside an `fc-surface-overlay` modal, it MUST use `fc-surface-solid` or a transparent background. You cannot put a quiet glass card inside an overlay modal.

---

## 5. Color System & Branding

Registry Blue (#3b82f6) is the primary action identity. It should be used for CTAs, active states, and focus rings. It should not be used as a decorative wash everywhere.

**Semantic Colors** must only represent meaning:

- Emerald (Success): Verified, authentic, complete.
- Amber (Warning): Caution, uncertainty, review needed.
- Red (Danger): Destructive actions, deception, severe risk.

**No Neon Glows:** Box shadows using colored hex codes on container elements are banned. Depth shadows must use `rgba(0,0,0,X)`.

---

## 6. Motion & Transitions

Motion must be functional, professional, and rapid.

**Allowed:**
- Opacity fades (0 → 1)
- Subtle Y-axis shifts (y: 4px → 0)
- Standard interaction duration: 160ms ease-out
- Max duration (Accordion/Progress): 200ms
- `animate-pulse` is strictly limited to `w-1.5` status indicator dots.

**Banned:**
- `hover:scale-*` or any scale/spring entrances. Elements do not bounce in a court-grade tool.
- Scan beams, orbit effects, or constant shimmering.
- Durations exceeding 200ms.

---

## 7. Component Blueprints

### 7.1 Buttons
Buttons are pill-shaped (`rounded-full`).

- `fc-btn-primary`: Registry blue glass. Main actions (Begin Analysis, Continue).
- `fc-btn-secondary`: Neutral white glass. Supporting actions (Back, View Details).
- `fc-btn-danger`: Red tinted glass. Destructive actions (Delete, Reset).
- `fc-btn-ghost`: Transparent. Utility actions (Dismiss, Copy).

### 7.2 Badges
Pill-shaped `text-xs`.

- Neutral (`fc-badge`)
- Active/Blue (`fc-badge-active`)
- Danger/Red (`fc-badge-danger`)
- Success/Emerald (`fc-badge-success`)

### 7.3 Data Tables
Must be wrapped in `fc-surface-quiet`.

- Monospace columns (hashes, IDs) must use `font-mono`.
- Numeric columns must use `tabular-nums` alignment.
- No zebra striping.

---

## 8. Court-Grade Data Handling

### 8.1 Unbounded Evidence Strings
Evidence strings (malicious file names, hashes) are adversarial inputs. They must never break the layout.

- **File Names:** Must strictly use `truncate max-w-full`.
- **Hashes/MIME:** Must use `break-all` or `truncate` with the full value provided in a `title` attribute for hover.

### 8.2 Print Mode (PDF Export)
Frosted glass and dark themes fail in PDF/print engines. This is handled globally
in `globals.css` and triggers in **two** ways: the browser print path (`@media
print`, i.e. Ctrl+P) and an explicit `data-print-mode="true"` attribute on the
root `html` (for programmatic export without the print dialog).

When active:
- All `fc-surface-*` (and `fc-upload-zone`) drop their `backdrop-filter` and become `#ffffff` with a 1px `#c7ccd6` border.
- The canonical text tiers (`fc-text-primary/secondary/muted/faint`) invert to dark ink.
- The hero gradient resolves to solid dark; registry blue darkens to `#1d4ed8` for high-contrast white paper.
- Glass highlights, noise/glow chrome, and `nav` / `[data-print-hide="true"]` elements are suppressed.

---

## 9. Compliance Checklist for PRs

Before merging any UI code, verify:

- [ ] No ESLint warnings regarding Tailwind classes (`npm run lint` is clean — `--max-warnings 0`).
- [ ] All `text-white/*` utilities have been replaced with `fc-text-*` variants.
- [ ] Any text inside a glass container uses `fc-text-muted` (68%) minimum.
- [ ] No `hover:scale-*` animations exist.
- [ ] No inline `backdrop-blur-*` classes are used outside of canonical surface definitions.
- [ ] No `z-[999]` arbitrary z-indexes are used (use `z-nav`, `z-modal`, `z-tooltip`).
- [ ] Tooltips use `fc-surface-solid`.
- [ ] Responsive layouts maintain `text-sm` for body copy at the smallest breakpoint.

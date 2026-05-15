# Forensic Council — Design System

**Status:** v1.7.0 audit baseline (Phase 3.0). This document is the source
of truth for every subsequent UI refinement phase. A token or class that
does not appear here is not part of the design system and must not be
introduced into new code without first updating this doc.

**Accessibility floor:** WCAG 2.1 Level AA on a `#02040A` background.
Aesthetic refinement never overrides a11y. When a glass or low-contrast
choice would push body text below 4.5:1 contrast, the text wins.

---

## 1. Typography

### 1.1 Current state [FACT]

The codebase declares three font families in `globals.css`:

```css
--font-sans:    var(--font-geist), system-ui, sans-serif;
--font-heading: var(--font-heading-family), var(--font-geist), sans-serif;
--font-mono:    var(--font-mono-family), ui-monospace, monospace;
```

`--font-geist`, `--font-heading-family`, and `--font-mono-family` are
**never defined** anywhere in the codebase. `apps/web/src/app/layout.tsx`
does not import `next/font/google` or `next/font/local`. No font files are
shipped in `apps/web/public`.

Result: `font-sans`, `font-heading`, and the typed `font-family` for any
class falls back to `system-ui` / `ui-monospace`. The three intended
typefaces render as one (system default) plus a monospace stack.

### 1.2 Font-size usage [FACT]

Counts of `text-[Npx]` and `text-{size}` across all `.tsx` files in
`apps/web/src/`:

| Class          | Count | Notes |
| -------------- | ----- | ----- |
| `text-[10px]`  | 106   | Heaviest single size. Used for monospace label rows. |
| `text-[9px]`   | 40    | At or below readability floor. |
| `text-xs` (12px) | 39  |       |
| `text-sm` (14px) | 32  |       |
| `text-[11px]`  | 21    |       |
| `text-4xl`     | 10    |       |
| `text-3xl`     | 9     |       |
| `text-base` (16px) | 7 |       |
| `text-[13px]`  | 7     |       |
| `text-xl`      | 6     |       |
| `text-[8px]`   | 6     | Below readability floor. |
| `text-[12px]`  | 6     | Duplicates `text-xs`. |
| `text-2xl`     | 6     |       |
| `text-lg`      | 5     |       |
| `text-[17px]`  | 3     |       |
| `text-5xl`     | 3     |       |
| `text-[44px]`  | 2     |       |
| `text-[22px]`  | 2     |       |
| `text-[15px]`  | 2     |       |
| `text-[68px]`  | 1     |       |
| `text-[28px]`  | 1     |       |
| `text-6xl`     | 1     |       |

### 1.3 Tracking (letter-spacing) usage [FACT]

| Class                | Count |
| -------------------- | ----- |
| `tracking-wide`      | 52    |
| `tracking-tight`     | 24    |
| `tracking-widest`    | 23    |
| `tracking-[0.2em]`   | 14    |
| `tracking-tighter`   | 12    |
| `tracking-[0.18em]`  | 8     |
| `tracking-[0.3em]`   | 7     |
| `tracking-wider`     | 6     |
| `tracking-[0.28em]`  | 4     |
| `tracking-[0.16em]`  | 4     |
| `tracking-[0.22em]`  | 3     |
| `tracking-[0.14em]`  | 3     |
| `tracking-[0.26em]`  | 1     |
| `tracking-[0.25em]`  | 1     |
| `tracking-[0.1em]`   | 1     |
| `tracking-[0.15em]`  | 1     |
| `tracking-[0.08em]`  | 1     |

### 1.4 Issues

- **No real heading typeface.** `font-heading` resolves to the same family
  as `font-sans` because `--font-heading-family` is undefined. The visual
  difference between headings and body relies entirely on size and weight.
- **`text-[9px]` and `text-[8px]`** are used in 46 places. These render at
  roughly 9–10 px after browser DPI rounding and are at the edge of
  legibility. WCAG doesn't set a hard pixel floor, but anything below
  12 px combined with a low-opacity color routinely fails AA in practice
  because anti-aliasing reduces perceived contrast.
- **`text-[10px]` (106 uses)** is the dominant "small label" size, but
  many of those uses pair it with `text-white/35` or `text-white/40`,
  which on `#02040A` yields a 3.0–3.4:1 ratio. Below AA for normal text.
- **`text-[12px]` and `text-xs`** are duplicates. Same 21 uses of
  `text-[11px]` should be either consolidated to `text-xs` or kept only
  where the 1-px difference is structurally required.

### 1.5 Proposed canonical token set

A single fluid type scale, all named (no `text-[Npx]` arbitraries except
where called out). All sizes assume system-ui or future Geist Sans.

| Token           | Size    | Use                                            |
| --------------- | ------- | ---------------------------------------------- |
| `fc-text-xs`    | 12px    | Captions, badges, status pills. Minimum size. |
| `fc-text-sm`    | 14px    | Secondary body, table cells, labels.          |
| `fc-text-base`  | 16px    | Body. Default.                                |
| `fc-text-lg`    | 18px    | Lead paragraph, prominent body.               |
| `fc-text-xl`    | 20px    | Subsection heading.                           |
| `fc-text-2xl`   | 24px    | Card title, section subheading.               |
| `fc-text-3xl`   | 30px    | Page subtitle.                                |
| `fc-text-4xl`   | 36px    | Page title.                                   |
| `fc-text-5xl`   | 48px    | Hero subhead.                                 |
| `fc-text-hero`  | clamp(40px, 6vw, 68px) | Landing-page hero only.            |

**Eyebrow / mono-label pattern.** The codebase has a recurring pattern of
small uppercase-tracked monospace labels (e.g. "System_Overview",
"Forensic Protocol Active", "Investigator Intervention"). These are
visually distinct. Replace `text-[10px] font-mono uppercase tracking-[0.X]`
ad-hoc styles with one component class:

| Token              | Size  | Tracking | Use                                          |
| ------------------ | ----- | -------- | -------------------------------------------- |
| `fc-eyebrow`       | 11px  | 0.22em   | The single "label above title" pattern.      |
| `fc-eyebrow-strong`| 12px  | 0.18em   | When eyebrow is the sole identifier.          |

**Banned:** `text-[8px]`, `text-[9px]`, any new `text-[Npx]` use that
duplicates an existing named token.

### 1.6 Font loading proposal

Phase 3.1 will introduce `next/font/google` imports in
`apps/web/src/app/layout.tsx` for:
- **Geist Sans** (variable) → `--font-geist` (used by `font-sans` + `font-heading`)
- **Geist Mono** (variable) → `--font-mono-family` (used by `font-mono`)

Until a distinct heading face is chosen, `--font-heading-family` should be
removed from `globals.css` and `font-heading` should be redefined to use
the same Geist Sans family with a heavier weight (`font-weight: 700`,
which is already enforced by the `h1–h6` rule). The visual distinction
between body and heading remains size + weight; this is intentional.

---

## 2. Color

### 2.1 Surface tokens (already canonical) [FACT]

`globals.css` `@theme` block defines:

| Token              | Value     |
| ------------------ | --------- |
| `--color-background` | `#02040A` |
| `--color-foreground` | `#EDF2F8` |
| `--color-surface-0`  | `#010307` |
| `--color-surface-1`  | `#060A14` |
| `--color-surface-2`  | `#0A1020` |
| `--color-surface-3`  | `#0F172D` |
| `--color-surface-4`  | `#141D35` |

These are the canonical surface stack. **Keep as-is.**

### 2.2 Brand + semantic colors (already canonical) [FACT]

| Token             | Value     | RGB                |
| ----------------- | --------- | ------------------ |
| `--color-primary` | `#4F8EF7` | `79, 142, 247`     |
| `--color-primary-soft` | `#A5C8FF` |                |
| `--color-accent`  | `#6BA3F5` |                    |
| `--color-success` | `#2DD4A0` | `45, 212, 160`     |
| `--color-warning` | `#E9A23B` | `233, 162, 59`     |
| `--color-danger`  | `#EF4469` | `239, 68, 105`     |

**Keep as-is.** These are well-defined.

### 2.3 Text-opacity drift [FACT]

23 distinct `text-white/N` values in use:

| Class | Count | Contrast vs #02040A (approx) | WCAG AA normal? | WCAG AA large? |
| ----- | ----- | ---------------------------- | --------------- | -------------- |
| `text-white/90` | 7  | 16.5:1 | ✓ | ✓ |
| `text-white/85` | 2  | 15.4:1 | ✓ | ✓ |
| `text-white/80` | 12 | 14.2:1 | ✓ | ✓ |
| `text-white/75` | 2  | 12.9:1 | ✓ | ✓ |
| `text-white/70` | 8  | 11.7:1 | ✓ | ✓ |
| `text-white/65` | 1  | 10.4:1 | ✓ | ✓ |
| `text-white/62` | 1  | 9.7:1  | ✓ | ✓ |
| `text-white/60` | 19 | 9.1:1  | ✓ | ✓ |
| `text-white/55` | 5  | 8.0:1  | ✓ | ✓ |
| `text-white/52` | 1  | 7.4:1  | ✓ | ✓ |
| `text-white/50` | 14 | 6.8:1  | ✓ | ✓ |
| `text-white/48` | 2  | 6.4:1  | ✓ | ✓ |
| `text-white/45` | 3  | 5.7:1  | ✓ | ✓ |
| `text-white/40` | 41 | 4.7:1  | ≈ borderline   | ✓ |
| `text-white/35` | 17 | 3.9:1  | ✗ | ✓ |
| `text-white/30` | 22 | 3.2:1  | ✗ | ≈ borderline   |
| `text-white/25` | 10 | 2.6:1  | ✗ | ✗ |
| `text-white/22` | 1  | 2.3:1  | ✗ | ✗ |
| `text-white/20` | 35 | 2.1:1  | ✗ | ✗ |
| `text-white/18` | 2  | 1.9:1  | ✗ | ✗ |
| `text-white/15` | 3  | 1.6:1  | ✗ | ✗ |
| `text-white/10` | 9  | 1.4:1  | ✗ | ✗ — decorative only |
| `text-white/5`  | 1  | 1.2:1  | ✗ | ✗ — decorative only |

Note: contrast ratios assume `#EDF2F8` (the `--color-foreground` constant)
mixed against `#02040A`. Approximations only — actual ratios depend on
glass-blur overlays underneath. The point: **86 uses of text below `/40`
are presumptively failing WCAG AA for normal body text**, and many of the
41 `text-white/40` uses are at 10–11 px which makes them likely to fail
in practice.

### 2.4 Parallel muted-text systems [FACT]

`text-slate-*`, `text-foreground/N`, and inline `style={{color: "..."}}`
introduce three more parallel ways to express muted text. Counts:

- `text-foreground/*`: 8 uses across 6 distinct opacities.
- `text-slate-*`: 10 uses across 8 distinct variants
  (`slate-200/65`, `slate-300/50`, `slate-300/55`, `slate-300/60`,
  `slate-300/75`, `slate-400`, `slate-500`, `slate-600`).

### 2.5 Semantic color drift [FACT]

The codebase uses multiple Tailwind palette shades for what should be one
semantic color:

| Semantic role | Variants in use | Canonical proposal |
| ------------- | --------------- | ------------------ |
| Danger / error | `text-rose-400` (8), `text-red-400` (5), `text-red-500`, `text-red-600`, `text-red-700`, `text-rose-300` (2), `text-rose-500` | `var(--color-danger)` only |
| Warning       | `text-amber-400` (8), `text-amber-500` (3), `text-amber-300` (2), `text-amber-600` (2), `text-amber-700`, `text-amber-200/60`, `text-amber-400/{60,70,80}` | `var(--color-warning)` only |
| Success       | `text-emerald-400` (3), `text-emerald-500`, `text-emerald-700`, `text-emerald-400/40`, `text-emerald-400/70`, `text-teal-400` | `var(--color-success)` only |
| Info / brand  | `text-blue-400` (2), `text-blue-500`, `text-violet-400` (3), `text-violet-400/50`, `text-violet-400/70` | `var(--color-primary)` only |

`text-amber-700` (`#B45309`) on `#02040A` is ≈ **3.1:1 contrast — fails AA
for normal text**.

### 2.6 Inline color drift [FACT]

139 distinct inline `rgba()` / hex values appear in `style={{}}` props.
The top-20 list (counts ≥ 3):

| Value                          | Count |
| ------------------------------ | ----- |
| `rgba(255,255,255,0.04)`       | 11    |
| `rgba(165,200,255,0.07)`       | 10    |
| `rgba(0,0,0,0.4)`              | 9     |
| `rgba(255,255,255,0.03)`       | 8     |
| `#A7FFD2`                       | 8     |
| `#00FFFF`                       | 7     |
| `#020617`                       | 6     |
| `rgba(79,142,247,0.06)`         | 5     |
| `rgba(165,200,255,0.08)`        | 5     |
| `#F59E0B`                       | 5     |
| `rgba(79,142,247,0.8)`          | 4     |
| `rgba(79,142,247,0.18)`         | 4     |
| `rgba(79,142,247,0.12)`         | 4     |
| `rgba(79,142,247,0.07)`         | 4     |
| `#F43F5E`                       | 4     |
| `#93C5FD`                       | 4     |
| `rgba(255,255,255,0.05)`        | 4     |
| `rgba(0,0,0,0.5)`               | 4     |
| `rgba(79,142,247,0.10)`         | 3     |
| `rgba(6,10,20,0.85)`            | 3     |
| `rgba(5,9,18,0.92)`             | 3     |
| `rgba(5,9,18,0.9)`              | 3     |
| `rgba(255,255,255,0.06)`        | 3     |
| `rgba(165,200,255,0.10)`        | 3     |

Note `#020617` is **not** the same as `--color-background` (`#02040A`).
Two near-blacks shipping in production.

### 2.7 Canonical color rules (proposed)

1. **Body text uses one of these classes only:**
   - `fc-text-primary`   → `rgba(237, 242, 248, 1.0)`  ≈ 18:1
   - `fc-text-secondary` → `rgba(237, 242, 248, 0.78)` ≈ 13:1
   - `fc-text-muted`     → `rgba(237, 242, 248, 0.62)` ≈ 9.3:1 (AA normal)
   - `fc-text-faint`     → `rgba(237, 242, 248, 0.55)` ≈ 7.5:1 (AA normal, body-large guaranteed)

   The existing `text-muted-readable` (`0.68`), `text-muted-secondary`
   (`0.56`), `text-muted-decorative` (`0.35`) already follow this model.
   The new tokens map cleanly:
   - `text-muted-readable` → keep, rename to `fc-text-muted` (0.62 floor)
   - `text-muted-secondary` → keep, rename to `fc-text-faint` (0.55 floor)
   - `text-muted-decorative` (`0.35`) → **delete**. It is below AA. Any
     use must become `fc-text-faint` (raised contrast) OR move to a
     dedicated `fc-text-decorative` token that is ONLY allowed on
     non-text elements (icon strokes, divider lines, etc).

2. **Banned for text:** `text-white/N` where N < 55 anywhere in body
   text, AND any N < 40 even for large/decorative text outside of
   explicitly aria-hidden icons or rules.

3. **Banned for text:** every `text-slate-*` variant. Convert to one of
   the four `fc-text-*` tokens.

4. **Banned for text:** every numeric Tailwind color shade (`text-red-X`,
   `text-amber-X`, `text-emerald-X`, etc). Use semantic helpers backed
   by the CSS variables:
   - `fc-text-danger`  → `var(--color-danger)`  → `#EF4469` ≈ 5.6:1 (AA normal)
   - `fc-text-warning` → `#F0B14B` (lifted from `#E9A23B` to clear AA) ≈ 5.8:1
   - `fc-text-success` → `var(--color-success)` ≈ 9.4:1
   - `fc-text-primary-accent` → `var(--color-primary)` ≈ 5.8:1

   Warning color **must be lifted** because `#E9A23B` on `#02040A` is
   exactly 4.42:1, fails AA. Proposed replacement `#F0B14B` clears 4.5:1.

5. **Inline `style={{color: ...}}` is banned for text** after Phase 3.1.
   Inline color is only permitted for SVG fills, gradient stops, and
   pseudo-element backgrounds where Tailwind classes don't apply.

---

## 3. Glass surfaces

### 3.1 Current classes [FACT]

`globals.css` defines four named glass / surface classes:

| Class             | Background                                                  | Border alpha | Backdrop blur | Use today |
| ----------------- | ----------------------------------------------------------- | ------------ | ------------- | --------- |
| `glass-panel`     | `var(--glass-bg)` = `rgba(79,142,247,0.035)`                | 0.09         | 20px          | Section containers (Home page) |
| `premium-glass`   | identical to `glass-panel`                                  | 0.09         | 20px          | Used 1×, alias |
| `horizon-card`    | `rgba(6,10,20,0.9)`                                         | 0.09         | none          | Card sublevel |
| `premium-card`    | identical to `horizon-card`                                 | 0.09         | none          | Alias |
| `fc-surface-crisp`| layered linear-gradient + `rgba(6,10,20,0.88)`              | 0.10         | none          | Pill nav, focal cards |
| `step-card`       | `rgba(255,255,255,0.022)`                                   | 0.05         | none          | Step lists inside containers |

### 3.2 Issues

- **`glass-panel` and `premium-glass` are duplicates** (same CSS rule).
- **`horizon-card` and `premium-card` are duplicates.**
- The very-low backdrop alpha (`rgba(79,142,247,0.035)`) means the
  "glass" is nearly invisible. The user has explicitly asked for "glass
  with solid contrast" — this means we keep the blur for depth perception
  but the background must be opaque enough that text on top reads
  cleanly. `rgba(6,10,20,0.88)` on `horizon-card` is the right pattern.

### 3.3 Canonical glass system (proposed)

Three named surfaces. All other glass/card classes alias to or replace
these.

| Token                | Background                                                                                       | Border                       | Blur | Use |
| -------------------- | ------------------------------------------------------------------------------------------------ | ---------------------------- | ---- | --- |
| `fc-surface-quiet`   | `rgba(6,10,20,0.92)`                                                                              | `rgba(165,200,255,0.08)`     | 0    | Inert cards, list rows. **No blur — solid contrast for text-heavy content.** |
| `fc-surface-elevated`| `linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.012)), rgba(6,10,20,0.92)`     | `rgba(165,200,255,0.12)`     | 0    | Default container. Visually "glass" via the layered top highlight, but reads opaque. |
| `fc-surface-overlay` | `rgba(2,4,10,0.96)`                                                                                | `rgba(165,200,255,0.15)`     | 24px | Modals + full-viewport overlays. Backdrop blur HERE only, because there's no text underneath that needs to read through. |

**Migration map:**
- `glass-panel`, `premium-glass`     → `fc-surface-elevated`
- `horizon-card`, `premium-card`     → `fc-surface-quiet`
- `fc-surface-crisp`                  → keep as-is (used as pill-nav background, already correct)
- `step-card`                          → keep as-is

### 3.4 Backdrop-blur rules

- Backdrop blur is allowed ONLY on `fc-surface-overlay` (modals, error
  modals, the LoadingOverlay portal, ArbiterDeliberationOverlay,
  ForensicProgressOverlay).
- All other surfaces — sections, cards, list rows — are **opaque** by
  alpha. The "glass" affordance comes from the layered highlight + border,
  not from a backdrop filter. This guarantees text contrast is
  predictable.

---

## 4. Border + radius

### 4.1 Radius usage [FACT]

| Class | Count |
| --- | --- |
| `rounded-full` | 97 |
| `rounded-2xl` | 52 |
| `rounded-xl` | 46 |
| `rounded-lg` | 11 |
| `rounded-3xl` | 7 |
| `rounded-md` | 7 |
| `rounded-sm` | 1 |
| `rounded-[2.5rem]` | 1 |
| `rounded-[1.5rem]` | 1 |
| `rounded-[1.25rem]` | 1 |

### 4.2 Canonical radii

Already defined in `globals.css` `@theme`:

| Variable     | Value | Tailwind class | Use |
| ------------ | ----- | -------------- | --- |
| `--radius-sm`  | 8px   | `rounded-lg`   | Buttons inside cards, inline controls |
| `--radius-md`  | 12px  | `rounded-xl`   | Default card |
| `--radius-lg`  | 16px  | `rounded-2xl`  | Containers |
| `--radius-xl`  | 20px  | n/a            | Modal corners |
| `--radius-2xl` | 26px  | `rounded-3xl`  | Hero panels |
| `--radius-full`| 9999  | `rounded-full` | Pills, avatars |

**Banned:** the three `rounded-[Xrem]` arbitraries — they're 1-px-off
`rounded-3xl`. Replace with `rounded-3xl` everywhere.

---

## 5. Borders

### 5.1 Current state [FACT]

Three border-color tokens are defined in `@theme`:
- `--color-border-subtle` = `rgba(140,160,200,0.07)`
- `--color-border-muted`  = `rgba(140,160,200,0.11)`
- `--color-border-strong` = `rgba(140,160,200,0.20)`

Inline `border-white/N` and `border-[rgba(...)]` are used widely in
parallel.

### 5.2 Canonical borders

Three tokens above are correct. All inline `border-white/N` should map to
one of:
- `border-border-subtle` → very faint divider
- `border-border-muted`  → default card/section border
- `border-border-strong` → emphasis / focus state border

---

## 6. Motion

### 6.1 Current state [FACT]

Tailwind `duration-N` (in CSS milliseconds):

| Class | Count |
| --- | --- |
| `duration-300` | 15 |
| `duration-500` | 10 |
| `duration-700` | 6 |
| `duration-200` | 5 |
| `duration-400` | 2 |
| `duration-150` | 2 |
| `duration-1000` | 2 |

Framer-motion `duration` (in seconds, top 12):

| Value | Count |
| --- | --- |
| `0.6` | 8 |
| `0.4` | 5 |
| `0.2` | 5 |
| `0.3` | 4 |
| `0.14` | 4 |
| `2`   | 3 |
| `1.5` | 3 |
| `1.4` | 3 |
| `0.22" | 3 |
| `0.12` | 3 |
| `4`   | 2 |
| `3`   | 2 |

### 6.2 Easing [FACT]

Two named easings already defined in `@theme`:
- `--ease-out`    = `cubic-bezier(0.16, 1, 0.3, 1)`
- `--ease-spring` = `cubic-bezier(0.34, 1.56, 0.64, 1)`
- `--ease-in-out` = `cubic-bezier(0.4, 0, 0.2, 1)`

### 6.3 Canonical motion tokens (proposed)

Three transition durations cover 95% of real cases:

| Token            | Duration | Use |
| ---------------- | -------- | --- |
| `fc-motion-fast` | 140ms    | Hover micro-feedback, overlay fade-in. |
| `fc-motion-base` | 240ms    | Default for any state change (color, position, opacity). |
| `fc-motion-slow` | 420ms    | Page-level transitions, large card mount/unmount. |
| `fc-motion-ambient` | 1.6s + | Looping ambient animations (breathing glows, ECG-like waves). NOT for user-driven state changes. |

Three easings cover everything:
- `--ease-out` for entrances and most state changes
- `--ease-in-out` for ambient loops
- `--ease-spring` reserved for buttons and other deliberate "bounce" UI

Anything outside these tokens needs a written justification.

### 6.4 Reduced motion

`globals.css` line 3–10 already correctly disables animation and smooth
scroll for `prefers-reduced-motion`. **Keep.** All Phase 3.x changes
must respect `useReducedMotion()` from framer-motion before applying
any non-trivial animation.

---

## 7. Focus states

`globals.css` already defines a global focus ring at lines 470–479:

```css
:where(a, button, input, textarea, select, [tabindex]:not([tabindex="-1"])):focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 3px;
  box-shadow: 0 0 0 4px rgba(var(--color-primary-rgb), 0.22);
  border-radius: 4px;
}
```

This is correct. **Keep.** All custom focus rings in components
(`.fc-focus-ring` etc.) must defer to this global rule. Inline
`outline: none` is banned unless paired with a replacement focus
indicator.

---

## 8. Layout density

### 8.1 Container max-widths

The codebase uses inconsistent max-widths: `max-w-md`, `max-w-2xl`,
`max-w-3xl`, `max-w-5xl`, `max-w-7xl`. **Keep all** — they are
intentional per-section.

### 8.2 Touch targets [a11y FACT]

WCAG 2.5.5 (AAA) recommends 44×44px minimum touch target. AA (2.5.8)
recommends 24×24px. Action icons and reset buttons (e.g. navbar Reset
button at `px-3 py-1.5`) compute to ~30×24px — clears AA but not AAA.

**Canonical rule:** primary interactive controls must clear 44×44px.
Secondary controls (small badge buttons, close icons) may use 28×28px
minimum. Below 28×28 is banned for any tap target.

---

## 9. Inventory of files that will change in Phase 3.1+

For traceability, the following files contain the drift documented above
and will be touched (in order) across Phase 3.1 → 3.7+:

| File | Sub-phase | Reason |
| --- | --- | --- |
| `apps/web/src/app/globals.css`                                | 3.1 | All token definitions. |
| `apps/web/src/app/layout.tsx`                                 | 3.1 | next/font import. |
| `apps/web/src/components/ui/LandingBackground.tsx`            | 3.2 | Inline rgba colors. |
| `apps/web/src/components/pages/HomeClient.tsx`                | 3.2 | Hero typography + eyebrow. |
| `apps/web/src/components/ui/HeroAuthActions.tsx`              | 3.2 | CTA button. |
| `apps/web/src/components/ui/HowWorksSection.tsx`              | 3.2 | Section typography. |
| `apps/web/src/components/ui/AgentsSection.tsx`                | 3.2 | Section typography. |
| `apps/web/src/components/ui/GlassPanel.tsx`                   | 3.2 | Class consolidation. |
| `apps/web/src/components/ui/GlobalNavbar.tsx`                 | 3.3 | Pill nav, touch target. |
| `apps/web/src/components/ui/GlobalFooter.tsx`                 | 3.3 | Small-text minimum. |
| `apps/web/src/components/ui/BrandLogo.tsx`                    | 3.3 | text-[8px]. |
| `apps/web/src/components/ui/Toaster.tsx`                      | 3.3 | Toast colors. |
| `apps/web/src/components/evidence/UploadModal.tsx`            | 3.4 | text-[8px], inline colors. |
| `apps/web/src/components/evidence/UploadSuccessModal.tsx`     | 3.4 |       |
| `apps/web/src/components/ui/LoadingOverlay.tsx`               | 3.4 |       |
| `apps/web/src/components/ui/ForensicErrorModal.tsx`           | 3.4 |       |
| `apps/web/src/components/ui/ForensicProgressOverlay.tsx`      | 3.4 |       |
| `apps/web/src/components/ui/dialog.tsx`                       | 3.4 |       |
| `apps/web/src/components/evidence/AgentProgressDisplay.tsx`   | 3.5a |      |
| `apps/web/src/components/evidence/AgentStatusCard.tsx`        | 3.5a | text-[8px]. |
| `apps/web/src/components/evidence/AgentStatusSummary.tsx`     | 3.5a |       |
| `apps/web/src/components/evidence/AgentProgressSkeleton.tsx`  | 3.5a |       |
| `apps/web/src/components/evidence/ArbiterCard.tsx`            | 3.5b |       |
| `apps/web/src/components/evidence/ArbiterDeliberationOverlay.tsx` | 3.5b |   |
| `apps/web/src/components/evidence/ForensicTimeline.tsx`       | 3.5b |       |
| `apps/web/src/components/evidence/HITLCheckpointModal.tsx`    | 3.5b |       |
| `apps/web/src/components/evidence/QuotaMeter.tsx`             | 3.5b |       |
| `apps/web/src/components/evidence/ErrorDisplay.tsx`           | 3.5b |       |
| `apps/web/src/components/result/ResultLayout.tsx`             | 3.6a |       |
| `apps/web/src/components/result/ResultHeader.tsx`             | 3.6a | text-[9px]. |
| `apps/web/src/components/result/ResultStateView.tsx`          | 3.6a |       |
| `apps/web/src/components/result/VerdictGauge.tsx`             | 3.6a | text-[8px]. |
| `apps/web/src/components/result/ArcGauge.tsx`                 | 3.6a |       |
| `apps/web/src/components/result/IntelligenceBrief.tsx`        | 3.6a |       |
| `apps/web/src/components/result/EvidenceThumbnail.tsx`        | 3.6a |       |
| `apps/web/src/components/result/AgentAnalysisTab.tsx`         | 3.6b |       |
| `apps/web/src/components/ui/AgentFindingCard.tsx`             | 3.6b | text-[9px]. |
| `apps/web/src/components/result/AgentFindingSubComponents.tsx`| 3.6b | text-[8px], text-[9px]. |
| `apps/web/src/components/result/TimelineTab.tsx`              | 3.6b |       |
| `apps/web/src/components/result/HistoryPanel.tsx`             | 3.6c | text-[9px]. |
| `apps/web/src/components/result/DeepModelTelemetry.tsx`       | 3.6c |       |
| `apps/web/src/components/result/DegradationBanner.tsx`        | 3.6c | text-[9px]. |
| `apps/web/src/components/result/ActionDock.tsx`               | 3.6c |       |
| `apps/web/src/components/result/ReportFooter.tsx`             | 3.6c |       |
| `apps/web/src/components/ui/AgentIcon.tsx`                    | 3.6c |       |
| `apps/web/src/components/ui/AnimatedNumber.tsx`               | 3.6c |       |
| `apps/web/src/components/ui/Badge.tsx`                        | 3.6c |       |
| `apps/web/src/components/pages/SessionExpiredClient.tsx`      | 3.7  | text-[8px]. |
| `apps/web/src/app/error.tsx`                                   | 3.7  |       |
| `apps/web/src/app/global-error.tsx`                            | 3.7  |       |
| `apps/web/src/app/not-found.tsx`                               | 3.7  |       |
| `apps/web/src/app/evidence/error.tsx`                          | 3.7  |       |
| `apps/web/src/app/result/error.tsx`                            | 3.7  |       |

**3.8 (final pass)** sweeps any residual drift identified during 3.2–3.7.

---

## 10. Rules for adding new tokens

After this audit lands, new colors / sizes / motion durations require:
1. A line added to the relevant section of this document.
2. The new token added to `globals.css` `@theme` or as a utility class.
3. The token used by name — no raw `text-[Npx]`, no inline `rgba()`
   for text or borders.

If a one-off value is genuinely needed (e.g. a hero-specific gradient
stop), document the exception in this file under the relevant section.

---

## 11. Compliance check matrix

Each Phase 3.x verification gate must include this check:

- [ ] No new `text-white/N` for N < 55 introduced in changed files.
- [ ] No new `text-slate-*` introduced.
- [ ] No new `text-{color}-{shade}` introduced — only semantic helpers.
- [ ] No new `text-[Npx]` introduced — only named tokens.
- [ ] All changed inline `style={{color: ...}}` removed or justified.
- [ ] Touch targets in changed files ≥ 28×28 px.
- [ ] `useReducedMotion()` respected on any new motion.
- [ ] Visual diff (manual screenshot) reviewed by operator.

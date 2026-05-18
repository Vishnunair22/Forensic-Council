# Forensic Council: Frontend Design System

This document serves as the absolute source of truth for the Forensic Council frontend (`apps/web`). To maintain an enterprise-grade, cohesive aesthetic and prevent "UI drift," every new component, page, and styling update MUST adhere to these strict rules.

## 1. Design Philosophy: "Premium Precision"
The Forensic Council app is a mission-critical forensic tool, not a consumer toy or a Web3 dashboard.
* **The Aesthetic:** "High-Contrast Glass." It strikes a balance between a premium, modern feel (subtle glassmorphism) and a highly readable, data-dense enterprise environment.
* **The Golden Rule:** UI chrome (borders, backgrounds, blurs) should be practically invisible. The forensic data and typography must be the loudest elements on the screen.

---

## 2. Color Palette & Theme
We enforce a deep, cool dark mode that reduces eye strain while allowing strict semantic colors to pop.

* **Base Background:** Deep slate/navy (e.g., `#02040A`). Avoid pure black (`#000000`).
* **Semantic Colors ONLY:**
  * **Cyan/Blue:** Active selections, progress bars, primary actions.
  * **Emerald (Success):** "Clean" or "Authentic" statuses only.
  * **Amber (Warning):** "Inconclusive" or "Warning" statuses only.
  * **Rose/Red (Danger):** "Tampered," "Anomaly," or "Error" statuses only.
* **BANNED:** Using semantic colors (Red, Amber, Emerald) as decorative background gradients or glows. If a user sees a red pixel, it must indicate an anomaly or error.

---

## 3. Glass Panel Anatomy (The Containers)
We use glassmorphism sparingly and purposefully to establish surface elevation without muddying the contrast.

* **ALLOWED:**
  * Dark, highly transparent backgrounds (e.g., `rgba(10, 15, 25, 0.6)`).
  * Strict, performant blurs (`backdrop-filter: blur(16px)`).
  * A single, crisp 1px border at low opacity (e.g., `rgba(255, 255, 255, 0.12)`).
* **BANNED:**
  * Glowing box-shadows (`box-shadow` used for luminous colors).
  * Complex, multi-stop internal background gradients.
  * Screen-blend lighting effects.
  * Nested Glass: Never place a blurred glass container inside another blurred glass container.

---

## 4. Typography & Data Display
Data readability is our highest priority. No more squinting at faded text.

* **Opacity Floor:** Text opacity must never drop below 55% (`text-white/55`).
* **Hierarchy:**
  * Primary data/headings: `font-black text-white/95`.
  * Secondary data/body: `font-bold text-white/70`.
  * We rely on font-weight and size to establish hierarchy, not extreme fading.
* **Title Case over ALL CAPS:** The app uses Title Case for labels and headings. ALL CAPS is BANNED because it reduces reading speed and feels aggressive.
* **Eyebrows:** Metadata labels (e.g., "Confidence") must use the Eyebrow pattern: small size (`text-[10px]`), Title Case, heavy weight (`font-black`), and wide tracking (`tracking-widest`). Do not use uppercase.

---

## 5. Layout & Spacing: The Anti-Box Rule
The UI must let data breathe. Avoid visual clutter caused by over-boxing elements.

* **BANNED: "Box-in-a-Box":** If a parent container has a border and a background, its children must separate themselves using whitespace (padding/margins), not additional internal borders and backgrounds.
* **Data Chips:** Condense metadata into tight, horizontal inline chips rather than large, empty grid squares.

---

## 6. Scale, Spacing & Element Placement
A slick, modern application feels predictable. This is achieved through strict mathematical rhythm and cognitive hierarchy.

* **The 4px/8px Grid Rhythm:** All padding, margins, and gaps must strictly follow Tailwind's 4px spacing scale (e.g., `gap-2`, `p-4`, `space-y-8`). BANNED: Arbitrary pixel spacing like `mt-[17px]`. 
* **Progressive Disclosure:** Do not overwhelm the user. Place critical information (Verdicts, Anomaly Counts, Primary CTAs) at the top or top-left. Verbose data (raw JSON logs, 10+ metric chips, deep analysis text) MUST be hidden behind a "Show Details" accordion or toggle. The UI should look deceptively simple until the user asks for depth.
* **Maximum Line Width (Readability):** Paragraphs of text (like Arbiter Narratives or Intelligence Briefs) must never stretch infinitely on wide monitors. Constrain text blocks using `max-w-3xl` or `max-w-prose` (roughly 60–75 characters wide) so the user's eye doesn't lose its place.
* **Font Size Floor:** Standard body text in data views should be 14px (`text-sm`). 12px (`text-xs`) is reserved for secondary timestamps or sub-labels. Anything smaller than 12px is BANNED unless it is using the strict `fc-eyebrow` Title Case pattern.

---

## 7. Responsiveness & Device Scaling
Enterprise data density must elegantly adapt to smaller screens without breaking the layout or causing horizontal overflow on the main body.

* **Mobile-First Data Degradation:** Complex data structures (like dense tables or 4-column grids) must gracefully convert into stacked cards on mobile (`grid-cols-1`). 
* **Hiding Non-Critical Chrome:** On screens smaller than `md`, aggressive pruning of secondary metadata is encouraged (e.g., hiding a verbose timestamp but keeping the status badge using `hidden md:flex`).
* **Touch Target Minimums:** Even if a button looks compact visually, its clickable area MUST be at least `44x44px` on touch devices to prevent misclicks. Use padding or pseudo-elements to expand the hit area.
* **Horizontal Scrolling for Matrices:** If a specific piece of data (like a raw JSON payload, a code block, or a strict forensic matrix) cannot be stacked, it MUST be wrapped in a horizontally scrollable container (`overflow-x-auto custom-scrollbar`) to prevent it from stretching the entire viewport.

---

## 8. Button & Interaction Hierarchy
Interactions should feel snappy, mechanical, and grounded.

* **Primary Action Button (CTA):** Solid, high-contrast (e.g., `bg-white text-black` or solid brand blue). Hover state should dim slightly (`opacity-90`) or gain a sharp outline.
* **Secondary/Outline Buttons:** Transparent background, `1px` subtle border, `text-white/70`. Hover fills the background subtly (`white/5`), brightens the border (`white/30`), and turns text pure white.
* **BANNED (Floaty Animations):** Hover states must NOT use `transform: translateY(-2px)`. Elements must not float away when hovered; they are anchored to the UI.

---

## 9. Animation Standards
Animations exist to smooth state transitions, not to entertain.

* **ALLOWED:** Quick opacity crossfades (`< 200ms`) and instantaneous color shifts.
* **BANNED:** Cinematic, decorative animations (e.g., `fc-scan-beam`, `fc-orbit`, continuous pulsing glows). Page loads can use a tight staggered fade-in (`y: 5px` slide), but it must be incredibly fast.

---

## 10. Strict Accessibility (A11y)
Enterprise-grade applications cannot compromise on accessibility.

* **Contrast Minimums:** Text against dark backgrounds must meet WCAG 2.1 AA standards (4.5:1 for standard text, 3:1 for large text).
* **Color Independence:** Color must never be the *only* way information is conveyed. A "Danger" state requires an explicit icon (e.g., Alert Triangle) and label ("Anomaly"), in addition to the red color.
* **Focus States:** `outline: none` is BANNED unless paired with a custom, highly visible focus ring (e.g., `focus-visible:ring-2 focus-visible:ring-primary`).
* **Semantic HTML:** Clickable actions must be `<button>`. Navigation must be `<a>`. Avoid `div` soup with `onClick` handlers. Use ARIA attributes (`aria-expanded`, `aria-hidden`) appropriately.
* **Reduced Motion:** Wrap animations in `@media (prefers-reduced-motion: reduce)` to disable or fall back to crossfades for users with motion sensitivity.
* **Screen Reader Context:** Use `.sr-only` to provide context for icon-only buttons (e.g., `<span className="sr-only">Close Modal</span>`).

---

## 11. Auditory Feedback (Sound Design)
Audio enhances the premium feel but must be strictly regulated to avoid user fatigue.

* **Purpose-Driven:** Sounds trigger ONLY on meaningful state changes (e.g., "Analysis Complete," "Critical Anomaly," "Error").
* **BANNED:** Routine hover sounds, typing sounds, or standard click/navigation audio.
* **Acoustic Tone:** Sounds must be subtle, organic, and mechanical.
  * *Success/Ready:* Soft resonant bell or clean digital tick.
  * *Warning:* Low-frequency muffled thud or distinct double-tone.
  * *Error:* Dry, sharp mechanical click.
  * No sci-fi lasers or retro arcade beeps.
* **A11y & Control:** Sound must never be the *sole* indicator of an event. A global, easily accessible "Mute" toggle must be provided.

import type { Variants } from "framer-motion";

// Motion primitives — Design System §6: functional, rapid, no spring/bounce,
// no scale entrances, max duration 200ms. Allowed: opacity fades + subtle Y.

export const FADE_IN: Variants = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
};

export const FADE_IN_UP: Variants = {
  initial: { opacity: 0, y: 4 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: 4 },
};

// Canonical interaction tween — 160ms ease-out.
export const TRANSITION_FAST = { duration: 0.16, ease: "easeOut" } as const;

// Max-duration reveal tween (accordion / progress / modal enter) — 200ms.
export const TRANSITION_ENTER = { duration: 0.2, ease: [0.16, 1, 0.3, 1] } as const;

import type { Variants } from "framer-motion";

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

export const FADE_IN_SCALE: Variants = {
  initial: { opacity: 0, scale: 0.95, filter: "blur(4px)" },
  animate: { opacity: 1, scale: 1, filter: "blur(0px)" },
  exit: { opacity: 0, scale: 1.05, filter: "blur(4px)" },
};

export const SPRING_STIFF = { type: "spring" as const, stiffness: 300, damping: 20 };

export const SPRING_GENTLE = { type: "spring" as const, stiffness: 200, damping: 25 };

export const TRANSITION_FAST = { duration: 0.16, ease: "easeOut" } as const;

export const TRANSITION_SMOOTH = { duration: 0.4, ease: [0.16, 1, 0.3, 1] } as const;

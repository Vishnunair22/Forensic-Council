import { Variants } from "framer-motion";

/**
 * Standardized Animation Variants for Forensic Council Redesign
 */

export const FADE_IN: Variants = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -10 }
};

export const STAGGER_CONTAINER: Variants = {
  initial: { opacity: 0 },
  animate: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1
    }
  }
};

export const SCALE_IN: Variants = {
  initial: { opacity: 0, scale: 0.9 },
  animate: {
    opacity: 1,
    scale: 1,
    transition: { type: "spring", damping: 20 }
  }
};

export const SLIDE_UP: Variants = {
  initial: { opacity: 0, y: 20 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, ease: [0.16, 1, 0.3, 1] }
  }
};

export const CARD_REVEAL: Variants = {
  initial: { opacity: 0, x: -20, filter: "blur(10px)" },
  animate: {
    opacity: 1,
    x: 0,
    filter: "blur(0px)",
    transition: { duration: 0.6, ease: "easeOut" }
  }
};

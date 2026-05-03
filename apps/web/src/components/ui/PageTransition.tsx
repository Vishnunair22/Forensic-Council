"use client";

import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { usePathname } from "next/navigation";

interface PageTransitionProps {
  children: React.ReactNode;
  className?: string;
  mode?: "wait" | "popLayout";
}

const DEFAULT_VARIANTS = {
  initial: { opacity: 0, scale: 0.995, y: 8 },
  animate: { opacity: 1, scale: 1, y: 0 },
  exit: { opacity: 0, scale: 0.995, y: -8 },
};

const DISABLED_VARIANTS = {
  initial: { opacity: 1 },
  animate: { opacity: 1 },
  exit: { opacity: 1 },
};

/**
 * Standard page transition for high-fidelity forensic screens.
 * Optimized for smoothness and minimal layout jitter.
 * Respects prefers-reduced-motion for accessibility.
 */
export function PageTransition({
  children,
  className = "",
  mode = "popLayout"
}: PageTransitionProps) {
  const pathname = usePathname();
  const reducedMotion = useReducedMotion();
  const variants = reducedMotion ? DISABLED_VARIANTS : DEFAULT_VARIANTS;
  const transition = reducedMotion
    ? { duration: 0 }
    : {
        duration: 0.45,
        ease: [0.16, 1, 0.3, 1],
        opacity: { duration: 0.3 }
      };

  return (
    <AnimatePresence mode={mode}>
      <motion.div
        key={pathname}
        className={className}
        initial="initial"
        animate="animate"
        exit="exit"
        variants={variants}
        transition={transition}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}

export function StaggerIn({
  children,
  className = "",
  delay = 0,
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
}) {
  return (
    <motion.div
      className={className}
      initial="hidden"
      animate="visible"
      variants={{
        hidden: {},
        visible: {
          transition: { staggerChildren: 0.05, delayChildren: delay },
        },
      }}
    >
      {children}
    </motion.div>
  );
}

export function StaggerChild({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <motion.div
      className={className}
      variants={{
        hidden: { opacity: 0, y: 12, scale: 0.98 },
        visible: {
          opacity: 1,
          y: 0,
          scale: 1,
          transition: {
            duration: 0.4,
            ease: [0.22, 1, 0.36, 1]
          },
        },
      }}
    >
      {children}
    </motion.div>
  );
}

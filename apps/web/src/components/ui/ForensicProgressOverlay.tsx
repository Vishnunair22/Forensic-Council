"use client";

import { useState, useEffect } from "react";
import { motion, useReducedMotion } from "framer-motion";

interface ForensicProgressOverlayProps {
  title: string;
  liveText: string;
  telemetryLabel: string;
  showElapsed: boolean;
}

export function ForensicProgressOverlay({
  title,
  liveText,
  telemetryLabel,
  showElapsed,
}: ForensicProgressOverlayProps) {
  const [elapsed, setElapsed] = useState(0);
  const prefersReducedMotion = useReducedMotion();

  useEffect(() => {
    const interval = setInterval(() => setElapsed((prev) => prev + 1), 1000);
    return () => clearInterval(interval);
  }, []);

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  return (
    <motion.div
      aria-busy="true"
      className="fixed inset-0 z-[10000] flex flex-col items-center justify-center px-6 selection:bg-transparent bg-[#02040A]/90 backdrop-blur-[32px]"
      initial={prefersReducedMotion ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={prefersReducedMotion ? {} : { opacity: 0, transition: { duration: 0.16, ease: "easeOut" } }}
      transition={{ duration: 0.16, ease: "easeOut" }}
    >
      <div className="relative z-10 w-full max-w-xl mx-auto border-l-2 border-[var(--color-primary)]/40 pl-8 md:pl-12 py-4">
        {/* Status indicator */}
        <div className="flex items-center gap-4 mb-10">
          <div className="relative w-8 h-8 flex items-center justify-center border border-[var(--color-primary)]/30 rounded-sm bg-[var(--color-primary)]/5">
            <motion.div
              animate={{ opacity: [1, 0.3, 1] }}
              transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
              className="w-3 h-3 bg-[var(--color-primary)]"
            />
          </div>
          <span className="fc-eyebrow fc-text-faint">
            System Active
          </span>
        </div>

        {/* Title and live text */}
        <div className="mb-12 space-y-5">
          <motion.h1
            initial={prefersReducedMotion ? false : { x: -8, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            transition={{ duration: 0.16, ease: "easeOut" }}
            className="text-3xl md:text-4xl font-heading font-black text-white tracking-tight"
          >
            {title}
          </motion.h1>
          <div className="flex items-center gap-4">
            <motion.div
              className="w-1.5 h-1.5 bg-white/55 rounded-full"
              animate={prefersReducedMotion ? {} : { opacity: [0.65, 1, 0.65] }}
              transition={prefersReducedMotion ? {} : { duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
            />
            <p
              id="forensic-live-text"
              className="text-xs md:text-sm font-mono font-medium text-white/60 tracking-wide"
              role="status"
              aria-live="polite"
              aria-atomic="true"
            >
              {liveText}
            </p>
          </div>
        </div>

        {/* Progress bar */}
        <div className="w-full max-w-md">
          <div className="flex items-center justify-between mb-4 fc-eyebrow fc-text-faint">
            <span>{telemetryLabel}</span>
            {showElapsed && (
              <span className="text-[var(--color-primary)]">{formatTime(elapsed)}</span>
            )}
          </div>
          <div className="h-px w-full bg-white/10 relative overflow-hidden">
            <motion.div
              className="absolute inset-y-0 left-0 bg-[var(--color-primary)] shadow-[0_0_15px_var(--color-primary)]"
              initial={{ width: "0%" }}
              animate={prefersReducedMotion ? {} : { width: ["0%", "18%", "18%", "45%", "45%", "82%", "82%", "100%", "100%"] }}
              transition={prefersReducedMotion ? {} : { duration: 3.5, times: [0, 0.15, 0.25, 0.4, 0.55, 0.75, 0.85, 0.95, 1], repeat: Infinity, ease: "linear" }}
            />
          </div>
        </div>
      </div>
    </motion.div>
  );
}

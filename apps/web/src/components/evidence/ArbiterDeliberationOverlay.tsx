"use client";

import React from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ShieldCheck } from "lucide-react";

interface ArbiterDeliberationOverlayProps {
  isVisible: boolean;
  liveText?: string;
}

/**
 * ArbiterDeliberationOverlay
 *
 * Full-viewport overlay that appears immediately when `isVisible` becomes true,
 * preventing the blank-screen flash that occurred before ForensicProgressOverlay
 * had time to mount. Uses `initial={false}` on AnimatePresence so the first-frame
 * background is immediately painted — no 0→1 opacity gap.
 */
export function ArbiterDeliberationOverlay({
  isVisible,
  liveText,
}: ArbiterDeliberationOverlayProps) {
  const prefersReducedMotion = useReducedMotion();

  const cleanLiveText = React.useMemo(() => {
    if (!liveText) return "";
    return liveText
      .replace(/Speculative synthesis complete\.?\s*/gi, "Council evidence weights are ready. ")
      .replace(/Initial analysis complete\. Awaiting analyst decision\.?/gi, "Final report synthesis requested. Waiting for the Council Arbiter to start.")
      .replace(/Deep analysis complete\. Awaiting analyst request for arbiter synthesis\.?/gi, "Deep findings are ready. Starting final report synthesis.")
      .replace(/\.\.\./g, ".")
      .replace(/…/g, ".")
      .trim();
  }, [liveText]);

  const [elapsed, setElapsed] = React.useState(0);
  React.useEffect(() => {
    if (!isVisible) { setElapsed(0); return; }
    const id = setInterval(() => setElapsed((p) => p + 1), 1000);
    return () => clearInterval(id);
  }, [isVisible]);

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    return `${m}:${(s % 60).toString().padStart(2, "0")}`;
  };

  return (
    <AnimatePresence initial={false}>
      {isVisible && (
        <motion.div
          key="arbiter-overlay"
          aria-busy="true"
          aria-label="Consensus Synthesis in progress"
          className="fixed inset-0 z-[10000] flex flex-col items-center justify-center px-6 bg-[#02040A]/95 backdrop-blur-[32px]"
          initial={prefersReducedMotion ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={prefersReducedMotion ? {} : { opacity: 0, transition: { duration: 0.16 } }}
          transition={{ duration: 0.16, ease: "easeOut" }}
        >
          <div className="relative z-10 w-full max-w-xl mx-auto border-l-2 border-[var(--color-success)]/40 pl-8 md:pl-12 py-4">
            {/* Status indicator */}
            <div className="flex items-center gap-4 mb-10">
              <div className="relative w-8 h-8 flex items-center justify-center border border-[var(--color-success)]/30 rounded-md bg-[var(--color-success)]/5">
                <motion.div
                  animate={prefersReducedMotion ? {} : { opacity: [1, 0.3, 1] }}
                  transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
                  className="w-3 h-3 rounded-full bg-[var(--color-success)]"
                />
              </div>
              <span className="fc-badge fc-badge-success">
                Arbiter Active
              </span>
            </div>

            {/* Title */}
            <div className="mb-12 space-y-5">
              <div className="flex items-center gap-3">
                <ShieldCheck className="w-7 h-7 text-[var(--color-success)]/70 shrink-0" />
                <motion.h1
                  initial={prefersReducedMotion ? false : { x: -8, opacity: 0 }}
                  animate={{ x: 0, opacity: 1 }}
                  transition={{ duration: 0.16, ease: "easeOut" }}
                  className="text-3xl md:text-4xl font-heading font-black text-white tracking-tight"
                >
                  Consensus Synthesis
                </motion.h1>
              </div>
              <div className="flex items-center gap-4">
                <div className="w-1.5 h-1.5 bg-[var(--color-success)]/50 rounded-full animate-pulse" />
                <p
                  id="arbiter-live-text"
                  className="text-xs md:text-sm font-mono font-medium text-white/60 tracking-wide"
                  role="status"
                  aria-live="polite"
                  aria-atomic="true"
                >
                  {cleanLiveText || "Compiling agent findings into the final report."}
                </p>
              </div>
            </div>

            {/* Progress bar */}
            <div className="w-full max-w-md">
              <div className="flex items-center justify-between mb-4 text-xs font-mono font-bold tracking-wide fc-text-secondary">
                <span>Council Arbiter</span>
                <span className="text-[var(--color-success)]">{formatTime(elapsed)}</span>
              </div>
              <div className="h-px w-full bg-white/10 relative overflow-hidden">
                <motion.div
                  className="absolute inset-y-0 left-0 bg-[var(--color-success)] shadow-[0_0_15px_var(--color-success)]"
                  initial={{ width: "0%" }}
                  animate={prefersReducedMotion ? {} : {
                    width: ["0%", "18%", "18%", "45%", "45%", "82%", "82%", "100%", "100%"],
                  }}
                  transition={prefersReducedMotion ? {} : {
                    duration: 3.5,
                    times: [0, 0.15, 0.25, 0.4, 0.55, 0.75, 0.85, 0.95, 1],
                    repeat: Infinity,
                    ease: "linear",
                  }}
                />
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

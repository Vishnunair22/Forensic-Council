"use client";

import React, { useEffect, useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { Scale, ShieldCheck, Zap } from "lucide-react";

interface ArbiterDeliberationOverlayProps {
  isVisible: boolean;
  liveText?: string;
}

export function ArbiterDeliberationOverlay({
  isVisible,
  liveText,
}: ArbiterDeliberationOverlayProps) {
  const [isPageVisible, setIsPageVisible] = useState(true);
  const prefersReducedMotion = useReducedMotion();

  // Pause animations when the tab is backgrounded to save CPU
  useEffect(() => {
    const handleVisibilityChange = () => {
      setIsPageVisible(!document.hidden);
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => document.removeEventListener("visibilitychange", handleVisibilityChange);
  }, []);
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

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          role="dialog"
          aria-modal="true"
          aria-labelledby="arbiter-overlay-title"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[100] flex items-center justify-center p-6"
          style={{ background: "rgba(1,2,8,0.92)", backdropFilter: "blur(28px)", WebkitBackdropFilter: "blur(28px)" }}
        >
          <div className="relative w-full max-w-lg">
            {/* Background Glow */}
            <div className="absolute inset-0 bg-[var(--color-primary)]/10 blur-[120px] rounded-full" />

            <div className="relative z-10 w-full max-w-lg rounded-2xl p-10 flex flex-col items-center text-center" style={{ background: "rgba(5,9,18,0.98)", border: "1px solid rgba(165,200,255,0.10)", boxShadow: "0 40px 100px rgba(0,0,0,0.8), inset 0 1px 0 rgba(255,255,255,0.04)" }}>
              {/* Animated Scales */}
              <div className="relative w-32 h-32 mb-10">
                <motion.div
                  animate={
                    isPageVisible && !prefersReducedMotion
                      ? { rotate: [0, -5, 5, 0] }
                      : {}
                  }
                  transition={
                    prefersReducedMotion
                      ? {}
                      : { duration: 4, repeat: Infinity, ease: "easeInOut" }
                  }
                  className="absolute inset-0 flex items-center justify-center text-[var(--color-primary)]"
                >
                  <Scale className="w-24 h-24 stroke-[1.5]" />
                </motion.div>

                <motion.div
                  animate={
                    isPageVisible && !prefersReducedMotion
                      ? { scale: [1, 1.2, 1], opacity: [0.3, 0.6, 0.3] }
                      : {}
                  }
                  transition={
                    prefersReducedMotion
                      ? {}
                      : { duration: 2, repeat: Infinity, ease: "easeInOut" }
                  }
                  className="absolute inset-0 flex items-center justify-center"
                >
                  <div className="w-32 h-32 rounded-full border border-[var(--color-primary)]/20" />
                </motion.div>
              </div>

              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
              >
                <h2 id="arbiter-overlay-title" className="text-3xl font-heading font-bold text-white mb-4 tracking-tight">
                  Arbiter Deliberation
                </h2>
                
                <div className="flex items-center justify-center gap-3 mb-8">
                  <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-[var(--color-primary)]/10 border border-[var(--color-primary)]/20">
                    <ShieldCheck className="w-3 h-3 text-[var(--color-primary)]" />
                    <span className="text-[10px] font-mono font-bold text-[var(--color-primary)] uppercase tracking-wider">
                      Council_Verified
                    </span>
                  </div>
                  <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-white/5 border border-white/10">
                    <Zap className="w-3 h-3 text-white/40" />
                    <span className="text-[10px] font-mono font-bold text-white/40 uppercase tracking-wider">
                      Synthesis_Active
                    </span>
                  </div>
                </div>

                <div className="space-y-4">
                  <p className="text-white/60 text-sm leading-relaxed max-w-sm mx-auto">
                    The Council Arbiter is synthesizing per-agent findings into the signed result report.
                  </p>
                  
<div className="h-6 flex items-center justify-center" aria-live="polite" aria-atomic="true">
                      <motion.p
                        key={cleanLiveText}
                        initial={{ opacity: 0, y: 5 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="text-[11px] font-mono font-bold text-[var(--color-primary)] tracking-[0.08em]"
                      >
                        {cleanLiveText || "Compiling agent findings into the final report."}
                      </motion.p>
                    </div>
                </div>
              </motion.div>
            </div>
          </div>

          {/* Indeterminate Progress Bar (Bottom) */}
          <div className="absolute bottom-0 left-0 right-0 h-1 bg-white/5 overflow-hidden">
            <motion.div
              animate={
                !prefersReducedMotion
                  ? { x: ["-100%", "200%"] }
                  : {}
              }
              transition={
                prefersReducedMotion
                  ? {}
                  : { duration: 2.2, repeat: Infinity, ease: "easeInOut" }
              }
              className="absolute top-0 bottom-0 w-1/3 bg-[var(--color-primary)] rounded-full shadow-[0_0_20px_rgba(var(--color-primary-rgb),0.5)]"
            />
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

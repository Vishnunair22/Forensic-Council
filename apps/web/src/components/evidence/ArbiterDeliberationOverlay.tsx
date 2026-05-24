"use client";

import React from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ShieldCheck } from "lucide-react";

interface ArbiterDeliberationOverlayProps {
  isVisible: boolean;
  liveText?: string;
}

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

  const [dynamicText, setDynamicText] = React.useState(cleanLiveText || "Compiling agent findings into the final report.");

  React.useEffect(() => {
    if (cleanLiveText && cleanLiveText.length > 5 && !cleanLiveText.toLowerCase().includes("waiting for the council")) {
       setDynamicText(cleanLiveText);
       return;
    }

    const arbiterPhases = [
      "Reviewing forensic agent telemetry...",
      "Evaluating confidence intervals...",
      "Cross-referencing anomaly signatures...",
      "Synthesizing executive summary...",
      "Drafting final Council verdict...",
      "Finalizing cryptographic signature..."
    ];

    let phaseIndex = 0;
    setDynamicText(arbiterPhases[0]);

    const textInterval = setInterval(() => {
      phaseIndex = (phaseIndex + 1) % arbiterPhases.length;
      setDynamicText(arbiterPhases[phaseIndex]);
    }, 4000);

    return () => clearInterval(textInterval);
  }, [cleanLiveText]);

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
          className="fixed inset-x-0 top-16 bottom-0 z-overlay flex flex-col items-center justify-center px-6 select-none bg-background/90 backdrop-blur-2xl"
          initial={prefersReducedMotion ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={prefersReducedMotion ? {} : { opacity: 0, transition: { duration: 0.16, ease: "easeIn" } }}
          transition={{ duration: 0.16, ease: "easeOut" }}
        >
          <div className="relative z-10 w-full max-w-xl mx-auto border-l-2 border-success/40 pl-8 md:pl-12 py-4">

            {/* Status indicator — same structure as LoadingOverlay, success tokens */}
            <div className="flex items-center gap-4 mb-10">
              <div className="relative w-8 h-8 flex items-center justify-center border border-success/30 rounded-2xl bg-success/5">
                <ShieldCheck className="w-4 h-4 text-success" aria-hidden="true" />
              </div>
              <span className="fc-eyebrow fc-text-muted">
                Council Arbiter
              </span>
            </div>

            {/* Title and live text — same structure as LoadingOverlay */}
            <div className="mb-12 space-y-5">
              <motion.h1
                initial={prefersReducedMotion ? false : { opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.16, ease: "easeOut" }}
                className="text-3xl lg:text-4xl xl:text-5xl font-heading font-black fc-text-primary text-hero-gradient tracking-tight leading-none whitespace-nowrap"
              >
                Consensus Synthesis
              </motion.h1>
              <div className="flex items-center gap-4">
                <motion.div
                  className="w-1.5 h-1.5 bg-white/55 rounded-full"
                  animate={prefersReducedMotion ? {} : { opacity: [0.65, 1, 0.65] }}
                  transition={prefersReducedMotion ? {} : { duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
                />
                <motion.p
                  id="arbiter-live-text"
                  className="text-xs md:text-sm font-mono fc-text-muted"
                  role="status"
                  aria-live="polite"
                  aria-atomic="true"
                  key={dynamicText}
                  initial={prefersReducedMotion ? false : { opacity: 0.4, y: 2 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  {dynamicText}
                </motion.p>
              </div>
            </div>

            {/* Progress bar — same h-1.5 track as LoadingOverlay; success fill + elapsed timer */}
            <div className="w-full max-w-md" aria-hidden="true">
              <div className="flex items-center justify-between mb-4 fc-eyebrow fc-text-muted">
                <span>Council Synthesis</span>
                <span className="text-success font-mono tabular-nums">{formatTime(elapsed)}</span>
              </div>
              <div className="h-1.5 w-full bg-white/10 rounded-full relative overflow-hidden">
                <motion.div
                  className="absolute inset-y-0 left-0 bg-success rounded-full"
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

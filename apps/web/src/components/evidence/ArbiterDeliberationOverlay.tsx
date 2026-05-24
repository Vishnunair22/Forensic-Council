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
          className="fixed inset-0 z-overlay flex flex-col items-center justify-center px-6 select-none bg-black/80 backdrop-blur-3xl overflow-hidden"
          initial={prefersReducedMotion ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={prefersReducedMotion ? {} : { opacity: 0, transition: { duration: 0.3, ease: "easeIn" } }}
        >
          {/* --- Atmospheric Backgrounds --- */}
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_0%,rgba(0,0,0,0.8)_100%)] pointer-events-none z-0" />
          <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAiIGhlaWdodD0iMjAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGNpcmNsZSBjeD0iMSIgY3k9IjEiIHI9IjEiIGZpbGw9InJnYmEoMjU1LDI1NSwyNTUsMC4wNSkiLz48L3N2Zz4=')] [mask-image:linear-gradient(to_bottom,white,transparent)] opacity-40 z-0" />

          <div className="relative z-10 w-full max-w-2xl mx-auto p-10 bg-white/[0.02] border border-success/20 rounded-3xl shadow-[0_0_50px_rgba(var(--color-success-rgb),0.1)]">

            <div className="flex items-center gap-4 mb-8">
              <div className="relative w-10 h-10 flex items-center justify-center border border-success/40 rounded-xl bg-success/10 shadow-[0_0_15px_rgba(var(--color-success-rgb),0.4)]">
                <ShieldCheck className="w-5 h-5 text-success" aria-hidden="true" />
              </div>
              <span className="text-sm font-mono uppercase tracking-widest text-success/80">
                Council Arbiter Online
              </span>
            </div>

            <div className="mb-12 space-y-4">
              <motion.h1
                initial={prefersReducedMotion ? false : { opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.4, ease: "easeOut" }}
                className="text-3xl md:text-5xl font-heading font-black text-white tracking-tight"
              >
                Consensus Synthesis
              </motion.h1>

              <div className="flex items-start gap-3 h-12">
                <span className="text-success font-mono mt-0.5">&gt;</span>
                <motion.p
                  id="arbiter-live-text"
                  className="text-sm md:text-base font-mono text-success drop-shadow-[0_0_8px_rgba(var(--color-success-rgb),0.5)] leading-relaxed"
                  role="status"
                  key={dynamicText}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.2 }}
                >
                  {dynamicText}
                  <motion.span
                    animate={{ opacity: [1, 0] }}
                    transition={{ duration: 0.4, repeat: Infinity, repeatType: "reverse" }}
                    className="inline-block w-2 h-4 bg-success align-middle ml-1"
                  />
                </motion.p>
              </div>
            </div>

            {/* Cryptographic Progress Track */}
            <div className="w-full" aria-hidden="true">
              <div className="flex items-center justify-between mb-3 text-xs font-mono text-success/60 uppercase tracking-widest">
                <span>Encryption Status</span>
                <span className="tabular-nums">T+{formatTime(elapsed)}</span>
              </div>
              <div className="h-2 w-full bg-black/50 border border-success/20 rounded-full relative overflow-hidden">
                <motion.div
                  className="absolute inset-y-0 left-0 bg-success rounded-full"
                  style={{ boxShadow: "0 0 10px rgba(var(--color-success-rgb), 0.8)" }}
                  initial={{ width: "0%" }}
                  animate={prefersReducedMotion ? {} : {
                    width: ["0%", "25%", "35%", "65%", "70%", "90%", "95%", "100%"],
                  }}
                  transition={prefersReducedMotion ? {} : {
                    duration: 4,
                    times: [0, 0.15, 0.25, 0.4, 0.55, 0.75, 0.85, 1],
                    repeat: Infinity,
                    ease: "easeInOut",
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

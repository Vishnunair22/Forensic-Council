"use client";

import React from "react";
import { motion, AnimatePresence } from "framer-motion";

interface ArbiterDeliberationOverlayProps {
  isVisible: boolean;
  liveText?: string;
}

export function ArbiterDeliberationOverlay({
  isVisible,
  liveText,
}: ArbiterDeliberationOverlayProps) {
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
        // A-H-1: this overlay contains no interactive elements — it is purely
        // a status surface while the Arbiter synthesizes. role="alertdialog"
        // with the live region inside conveys the right semantics without
        // implying a focus trap obligation that wasn't being met.
        <motion.div
          role="alertdialog"
          aria-labelledby="arbiter-overlay-title"
          aria-describedby="arbiter-overlay-live"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[10000] flex flex-col items-center justify-center px-5 select-none bg-black text-center"
        >
          <h2 id="arbiter-overlay-title" className="text-4xl md:text-5xl font-black text-white uppercase tracking-tight mb-4">
            Council Arbiter Synthesizing
          </h2>
          
          <div id="arbiter-overlay-live" aria-live="polite" aria-atomic="true" className="h-8 flex items-center justify-center">
            <motion.p
              key={cleanLiveText}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-sm md:text-base font-bold text-white/50 tracking-widest uppercase"
            >
              {cleanLiveText || "Compiling agent findings into the final report."}
            </motion.p>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

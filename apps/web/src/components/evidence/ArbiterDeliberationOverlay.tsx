"use client";

import React from "react";
import { AnimatePresence } from "framer-motion";
import { ForensicProgressOverlay } from "@/components/ui/ForensicProgressOverlay";

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
        <ForensicProgressOverlay
          title="Consensus Synthesis"
          liveText={cleanLiveText || "Compiling agent findings into the final report."}
          telemetryLabel="Council Arbiter"
          showElapsed
        />
      )}
    </AnimatePresence>
  );
}

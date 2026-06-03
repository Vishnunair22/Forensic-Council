"use client";

import React, { useEffect } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { ResultLayout } from "@/components/result/ResultLayout";

export function DynamicResultClient({ sessionId }: { sessionId: string }) {
  const prefersReducedMotion = useReducedMotion();
  useEffect(() => {
    document.body.style.overflow = "";
    // The report-reveal sound is fired by useResult at the exact moment the
    // report content becomes visible — not here on mount, where it would play
    // during the loading overlay before any content exists.
  }, []);

  return (
    // No opacity/transform on this wrapper: an opacity<1 or transformed ancestor
    // re-scopes the ForensicProgressOverlay's `position: fixed` to this element
    // (instead of the viewport) and would hide the overlay during the entrance,
    // leaving the page blank until the fade completed. The reveal is provided by
    // the flash sweep below (a sibling) and the report's own staggered variants.
    <div className="relative">
      {!prefersReducedMotion && (
        <motion.div
          className="absolute inset-0 bg-white/10 z-50 pointer-events-none"
          initial={{ opacity: 1 }}
          animate={{ opacity: 0 }}
          transition={{ duration: 0.8, ease: "circOut" }}
        />
      )}
      <ResultLayout initialSessionId={sessionId} />
    </div>
  );
}

"use client";

import React from "react";
import { AlertTriangle } from "lucide-react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";

interface DegradationBannerProps {
  flags: string[];
}

export function DegradationBanner({ flags }: DegradationBannerProps) {
  const prefersReduced = useReducedMotion();
  if (!flags || flags.length === 0) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={prefersReduced ? false : { opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.16, ease: "easeOut" }}
        className="border border-warning/20 rounded-2xl overflow-hidden fc-surface-quiet"
      >
        <div className="px-5 py-3.5 border-b border-warning/10 flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5 text-warning shrink-0" aria-hidden="true" />
          <span className="fc-eyebrow text-warning">
            Analysis Degradation Notice
          </span>
          <span className="fc-eyebrow text-warning/60 ml-auto">
            {flags.length} flag{flags.length !== 1 ? "s" : ""}
          </span>
        </div>
        <div className="px-5 py-4 space-y-2.5">
          {flags.map((flag, i) => (
            <div
              key={i}
              className="flex items-start gap-2.5 text-xs leading-relaxed"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-warning/60 mt-1.5 shrink-0" aria-hidden="true" />
              <span className="fc-text-muted">{flag}</span>
            </div>
          ))}
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

"use client";

import React from "react";
import { AlertTriangle } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface DegradationBannerProps {
  flags: string[];
}

export function DegradationBanner({ flags }: DegradationBannerProps) {
  if (!flags || flags.length === 0) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        className="rounded-2xl overflow-hidden border border-warning/20 bg-transparent"
      >
        <div className="px-5 py-3.5 border-b border-warning/10 bg-transparent flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5 text-warning" />
          <span className="text-[10px] font-bold tracking-wide text-warning">
            Analysis Degradation Notice
          </span>
          <span className="fc-eyebrow text-warning ml-auto">
            {flags.length} FLAG{flags.length !== 1 ? "S" : ""}
          </span>
        </div>
        <div className="p-4 space-y-2">
          {flags.map((flag, i) => (
            <div
              key={i}
              className="flex items-start gap-3 text-xs text-warning leading-relaxed"
            >
              <span className="text-xs font-mono font-bold text-warning mt-0.5 shrink-0">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span>{flag}</span>
            </div>
          ))}
          <p className="text-xs font-mono fc-text-faint pt-2 border-t border-warning/5">
            Findings may reflect reduced analytical capacity. Consider this when interpreting results for court submission.
          </p>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

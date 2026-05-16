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
        className="rounded-2xl overflow-hidden border border-warning/20 bg-warning/[0.03]"
      >
        <div className="px-5 py-3.5 border-b border-warning/10 bg-warning/[0.05] flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5 text-warning" />
          <span className="text-[10px] font-bold tracking-wide text-warning/80">
            Analysis Degradation Notice
          </span>
          <span className="text-[10px] font-mono font-black text-warning/50 tracking-wide ml-auto">
            {flags.length} FLAG{flags.length !== 1 ? "S" : ""}
          </span>
        </div>
        <div className="p-4 space-y-2">
          {flags.map((flag, i) => (
            <div
              key={i}
              className="flex items-start gap-3 text-[11px] text-warning/70 leading-relaxed"
            >
              <span className="text-[9px] font-mono font-bold text-warning/40 mt-0.5 shrink-0">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span>{flag}</span>
            </div>
          ))}
          <p className="text-[9px] font-bold tracking-wide text-warning/40 pt-2 border-t border-warning/5">
            Findings may reflect reduced analytical capacity. Consider this when interpreting results for court submission.
          </p>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

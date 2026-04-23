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
        className="rounded-2xl overflow-hidden border border-amber-500/20 bg-amber-500/[0.03]"
      >
        <div className="px-5 py-3.5 border-b border-amber-500/10 bg-amber-500/[0.05] flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
          <span className="text-[10px] font-bold tracking-wide text-amber-400/80">
            Analysis Degradation Notice
          </span>
          <span className="text-[10px] font-mono font-black text-amber-500/50 tracking-wide ml-auto">
            {flags.length} FLAG{flags.length !== 1 ? "S" : ""}
          </span>
        </div>
        <div className="p-4 space-y-2">
          {flags.map((flag, i) => (
            <div
              key={i}
              className="flex items-start gap-3 text-[11px] text-amber-200/60 leading-relaxed"
            >
              <span className="text-[9px] font-mono font-bold text-amber-500/40 mt-0.5 shrink-0">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span>{flag}</span>
            </div>
          ))}
          <p className="text-[9px] font-bold tracking-wide text-amber-500/30 pt-2 border-t border-amber-500/5">
            Findings may reflect reduced analytical capacity. Consider this when interpreting results for court submission.
          </p>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

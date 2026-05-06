"use client";

import React from "react";
import { Hash, AlertCircle, CheckCircle2, Quote, Minus } from "lucide-react";
import { motion } from "framer-motion";
import { clsx } from "clsx";

interface IntelligenceBriefProps {
  verdictSentence?: string;
  keyFindings?: string[];
  isDeepPhase?: boolean;
}

export function IntelligenceBrief({ verdictSentence, keyFindings = [], isDeepPhase = false }: IntelligenceBriefProps) {
  if (!verdictSentence && keyFindings.length === 0) return null;

  return (
    <div className="w-full max-w-7xl mx-auto space-y-8">

      {/* --- Executive Verdict Quote --- */}
      {verdictSentence && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-surface-1 border border-white/5 rounded-2xl shadow-[0_4px_24px_rgba(0,0,0,0.5),0_1px_0_rgba(255,255,255,0.04)_inset] relative overflow-hidden"
        >
          <div className="p-8 md:p-10 relative">
            <Quote className="absolute -top-6 -right-6 w-40 h-40 text-white/[0.015] pointer-events-none" />

            <div className="flex items-center gap-3 mb-6">
              <Hash className="w-4 h-4 text-[var(--color-success-light)]" />
              <span className="text-[10px] font-mono font-bold text-white/20 uppercase tracking-[0.4em]">
                EXECUTIVE_SUMMARY // ANALYST_VERDICT
              </span>
              <div className="ml-auto">
                <span className={clsx(
                  "text-[9px] font-mono font-bold px-3 py-1 rounded-full border uppercase tracking-widest",
                  isDeepPhase
                    ? "text-[var(--color-success-light)] border-[var(--color-success-light)]/20 bg-[var(--color-success-light)]/5"
                    : "text-white/20 border-white/10 bg-white/[0.02]"
                )}>
                  {isDeepPhase ? "Deep_Analysis" : "Initial_Scan"}
                </span>
              </div>
            </div>

            <p className="text-xl sm:text-2xl font-medium text-white/80 leading-relaxed italic font-sans relative z-10 tracking-tight">
              &ldquo;{verdictSentence}&rdquo;
            </p>

            <div className="mt-8 flex items-center gap-3 text-[9px] font-mono text-white/10 uppercase tracking-widest">
              <span className="w-2 h-2 rounded-full bg-[var(--color-success-light)]/20" />
              <span>Authenticated_Forensic_Analytic_Bridge</span>
            </div>
          </div>
        </motion.div>
      )}

      {/* --- Key Findings --- */}
      {keyFindings.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center gap-4 px-1">
            <span className="text-[10px] font-mono font-bold text-white/20 uppercase tracking-[0.4em]">Key_Findings</span>
            <div className="h-px flex-1 bg-white/5" />
            <span className="text-[9px] font-mono text-white/15">{keyFindings.length} Signal{keyFindings.length !== 1 ? "s" : ""}</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {keyFindings.map((finding, i) => {
              if (typeof finding !== "string") return null;
              const lower = finding.toLowerCase();
              const isDanger = /detected|found|confirmed|splicing|manipulation|tampered|ai-generated|synthetic|fabricat/.test(lower);
              const isWarning = /inconsistency|anomaly|suspicious|potential|warning/.test(lower);
              const severity = isDanger ? "danger" : isWarning ? "warning" : "info";

              return (
                <motion.div
                  key={`finding-${i}`}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.04 }}
                  className="bg-surface-1 border border-white/5 rounded-xl shadow-[0_4px_24px_rgba(0,0,0,0.4),0_1px_0_rgba(255,255,255,0.03)_inset] p-5 flex items-start gap-4 hover:bg-surface-2 transition-all group"
                >
                  <div className={clsx(
                    "w-9 h-9 shrink-0 rounded-xl flex items-center justify-center border transition-all duration-500 mt-0.5",
                    severity === "danger"
                      ? "bg-red-500/10 border-red-500/20 text-red-400 group-hover:scale-110"
                      : severity === "warning"
                        ? "bg-amber-500/10 border-amber-500/20 text-amber-400 group-hover:scale-110"
                        : "bg-primary/10 border-primary/20 text-primary group-hover:scale-110"
                  )}>
                    {severity === "info"
                      ? <CheckCircle2 className="w-4 h-4" />
                      : severity === "warning"
                        ? <Minus className="w-4 h-4" />
                        : <AlertCircle className="w-4 h-4" />
                    }
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-[9px] font-mono font-bold text-white/10 mb-1.5 uppercase tracking-widest">
                      Finding_{i.toString().padStart(2, "0")}
                    </div>
                    <p className="text-[13px] text-white/55 leading-relaxed font-medium">{finding}</p>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

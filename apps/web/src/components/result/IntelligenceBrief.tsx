"use client";

import React from "react";
import { Hash, AlertCircle, Quote } from "lucide-react";
import { motion } from "framer-motion";
import { clsx } from "clsx";

interface IntelligenceBriefProps {
  verdictSentence?: string;
  keyFindings?: string[];
  isDeepPhase?: boolean;
}

/**
 * IntelligenceBrief: Redesigned with the Horizon HUD aesthetic.
 */
export function IntelligenceBrief({ verdictSentence, keyFindings = [], isDeepPhase = false }: IntelligenceBriefProps) {
  if (!verdictSentence && keyFindings.length === 0) return null;

  return (
    <div className="w-full max-w-7xl mx-auto space-y-16">

      {/* --- Executive Briefing Sentence --- */}
      {verdictSentence && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-[#070A12] border border-white/8 rounded-2xl shadow-[0_4px_24px_rgba(0,0,0,0.5),0_1px_0_rgba(255,255,255,0.04)_inset] relative overflow-hidden"
        >
          <div className="p-8 md:p-12 relative overflow-hidden">
            <Quote className="absolute -top-4 -right-4 w-48 h-48 text-white/[0.01] pointer-events-none" />

            <div className="flex items-center gap-4 mb-10">
               <Hash className="w-5 h-5 text-[var(--color-success-light)]" />
               <span className="text-[10px] font-mono font-bold text-white/20 uppercase tracking-[0.4em]">
                 EXECUTIVE_SUMMARY // ANALYST_VERDICT
               </span>
            </div>

            <p className="text-2xl sm:text-3xl font-medium text-white leading-relaxed italic font-sans text-balance relative z-10 tracking-tight">
              &ldquo;{verdictSentence}&rdquo;
            </p>

            <div className="mt-12 flex items-center gap-3 text-[10px] font-mono text-white/10 uppercase tracking-widest">
               <span className="w-2 h-2 rounded-full bg-[var(--color-success-light)]/20" />
               <span>Authenticated_Forensic_Analytic_Bridge</span>
            </div>
          </div>
        </motion.div>
      )}

      {/* --- Key Findings Bento --- */}
      {keyFindings.length > 0 && (
        <div className="space-y-8">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-6">
               <span className="text-[10px] font-mono font-bold text-white/20 uppercase tracking-[0.4em]">Key_Findings</span>
               <div className="h-px w-32 bg-white/5" />
            </div>
            <span className={clsx(
              "text-[10px] font-mono font-bold px-4 py-1.5 rounded-full border uppercase tracking-widest",
              isDeepPhase ? "text-[var(--color-success-light)] border-[var(--color-success-light)]/20 bg-[var(--color-success-light)]/5" : "text-white/20 border-white/10 bg-white/5"
            )}>
              {isDeepPhase ? "Deep_Analysis_Node" : "Initial_Scan_Node"}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {keyFindings.map((finding, i) => {
              const lower = finding.toLowerCase();
              const isDanger = /detected|found|confirmed|splicing|manipulation|tampered|ai-generated|synthetic/.test(lower);
              const isWarning = /inconsistency|anomaly|suspicious|potential/.test(lower);
              
              const severity = isDanger ? "danger" : isWarning ? "warning" : "info";
              
              return (
                <motion.div
                  key={`finding-${i}`}
                  initial={{ opacity: 0, scale: 0.98 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: i * 0.05 }}
                  className="bg-[#070A12] border border-white/8 rounded-2xl shadow-[0_4px_24px_rgba(0,0,0,0.5),0_1px_0_rgba(255,255,255,0.04)_inset] p-8 flex items-start gap-6 hover:bg-white/[0.02] transition-all group"
                >
                  <div className={clsx(
                    "w-12 h-12 shrink-0 rounded-2xl flex items-center justify-center shadow-2xl transition-all duration-500",
                    severity === "danger" ? "bg-red-500/10 border border-red-500/20 text-red-400 group-hover:scale-110" :
                    severity === "warning" ? "bg-amber-500/10 border border-amber-500/20 text-amber-400 group-hover:scale-110" :
                    "bg-primary/10 border border-primary/20 text-primary group-hover:scale-110"
                  )}>
                    {severity === "danger" ? <AlertCircle className="w-5 h-5" /> :
                     severity === "warning" ? <AlertCircle className="w-5 h-5" /> :
                     <CheckCircle2 className="w-5 h-5" />}
                  </div>
                  <div className="flex-1">
                     <div className="text-[10px] font-mono font-bold text-white/10 mb-3 uppercase tracking-widest">Finding_Log_{i.toString().padStart(2, '0')}</div>
                     <p className="text-base text-white/50 leading-relaxed font-medium">
                       {finding}
                     </p>
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

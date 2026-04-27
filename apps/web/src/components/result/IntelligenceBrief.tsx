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
          className="glass-panel p-1 relative rounded-[2.5rem] border-white/5"
        >
          <div className="bg-[#020203]/40 rounded-[inherit] p-12 relative overflow-hidden">
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
            {keyFindings.map((finding, i) => (
              <motion.div
                key={`finding-${i}`}
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: i * 0.05 }}
                className="glass-panel p-8 flex items-start gap-6 hover:bg-white/[0.02] transition-all border-white/5"
              >
                <div className="w-12 h-12 shrink-0 rounded-2xl bg-[var(--color-success-light)]/5 border border-[var(--color-success-light)]/10 flex items-center justify-center shadow-2xl">
                  <AlertCircle className="w-5 h-5 text-[var(--color-success-light)]/40" />
                </div>
                <div className="flex-1">
                   <div className="text-[10px] font-mono font-bold text-white/10 mb-3 uppercase tracking-widest">Finding_Log_{i.toString().padStart(2, '0')}</div>
                   <p className="text-base text-white/50 leading-relaxed font-medium">
                     {finding}
                   </p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}


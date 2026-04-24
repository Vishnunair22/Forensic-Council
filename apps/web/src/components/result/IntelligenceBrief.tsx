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
    <div className="w-full max-w-5xl mx-auto space-y-12">
      
      {/* --- Executive Briefing Sentence --- */}
      {verdictSentence && (
        <motion.div 
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="horizon-card p-1 relative rounded-3xl"
        >
          <div className="bg-[#020617] rounded-[inherit] p-10 relative overflow-hidden">
            <Quote className="absolute -top-4 -right-4 w-32 h-32 text-white/[0.02] pointer-events-none" />
            
            <div className="flex items-center gap-3 mb-8">
               <Hash className="w-4 h-4 text-primary" />
               <span className="text-[10px] font-mono font-bold text-white/30 uppercase tracking-[0.3em]">
                 EXECUTIVE_SUMMARY // ANALYST_VERDICT
               </span>
            </div>
            
            <p className="text-xl sm:text-2xl font-medium text-white/80 leading-relaxed italic font-sans text-balance relative z-10">
              &ldquo;{verdictSentence}&rdquo;
            </p>

            <div className="mt-8 flex items-center gap-2 text-[9px] font-mono text-white/10 uppercase tracking-widest">
               <span className="w-1.5 h-1.5 rounded-full bg-primary/40" />
               <span>Authenticated_Forensic_Analytic_Bridge</span>
            </div>
          </div>
        </motion.div>
      )}

      {/* --- Key Findings Bento --- */}
      {keyFindings.length > 0 && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
               <span className="text-[10px] font-mono font-bold text-white/30 uppercase tracking-[0.3em]">Key_Findings</span>
               <div className="h-px w-24 bg-white/5" />
            </div>
            <span className={clsx(
              "text-[9px] font-mono font-bold px-3 py-1 rounded border uppercase tracking-widest",
              isDeepPhase ? "text-primary border-primary/20 bg-primary/5" : "text-white/40 border-white/10 bg-white/5"
            )}>
              {isDeepPhase ? "Deep_Analysis_Node" : "Initial_Scan_Node"}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {keyFindings.map((finding, i) => (
              <motion.div
                key={`finding-${i}`}
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: i * 0.05 }}
                className="horizon-card p-6 flex items-start gap-4 hover:bg-white/[0.02] transition-colors"
              >
                <div className="w-10 h-10 shrink-0 rounded-lg bg-primary/5 border border-primary/10 flex items-center justify-center">
                  <AlertCircle className="w-4 h-4 text-primary/40" />
                </div>
                <div className="flex-1">
                   <div className="text-[9px] font-mono font-bold text-white/10 mb-2 uppercase">Finding_Log_{i.toString().padStart(2, '0')}</div>
                   <p className="text-sm text-white/60 leading-relaxed font-medium">
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

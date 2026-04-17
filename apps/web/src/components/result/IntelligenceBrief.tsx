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

export function IntelligenceBrief({ verdictSentence, keyFindings = [], isDeepPhase = false }: IntelligenceBriefProps) {
  if (!verdictSentence && keyFindings.length === 0) return null;

  return (
    <div className="w-full max-w-4xl mx-auto space-y-8 py-8 animate-in fade-in slide-in-from-top-4 duration-700">
      {/* Executive Verdict Sentence */}
      {verdictSentence && (
        <motion.div 
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="relative px-8 py-10 rounded-3xl bg-white/[0.01] border border-white/5 overflow-hidden group hover:bg-white/[0.02] transition-colors"
        >
          <div className="absolute top-0 left-0 w-1 h-full bg-cyan-500/20" />
          <Quote className="absolute top-6 right-8 w-12 h-12 text-white/[0.02] pointer-events-none" />
          
          <div className="flex items-center gap-3 mb-4 text-white/20">
            <Hash className="w-4 h-4" />
            <span className="text-[10px] font-bold tracking-[0.3em]">Executive Briefing</span>
          </div>
          
          <p className="text-xl sm:text-2xl font-medium text-white/70 leading-relaxed italic text-balance">
            &ldquo;{verdictSentence}&rdquo;
          </p>
        </motion.div>
      )}

      {/* Structured Key Findings */}
      {keyFindings.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <span className="text-[10px] font-bold tracking-widest text-white/20">KEY FINDINGS</span>
            <span className={clsx(
              "text-[9px] font-bold px-2 py-0.5 rounded-full tracking-widest",
              isDeepPhase
                ? "bg-violet-500/10 border border-violet-500/20 text-violet-400"
                : "bg-cyan-500/10 border border-cyan-500/20 text-cyan-400"
            )}>
              {isDeepPhase ? "Deep Analysis" : "Initial Scan"}
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {keyFindings.map((finding, i) => (
            <motion.div
              key={`finding-${i}-${finding.slice(0, 20)}`}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: i * 0.1 }}
              className="flex items-start gap-4 p-5 rounded-2xl bg-white/[0.01] border border-white/5 hover:border-white/10 transition-colors group"
            >
              <AlertCircle className="w-5 h-5 text-cyan-400/30 shrink-0 mt-0.5 group-hover:text-cyan-400/60 transition-colors" />
              <p className="text-[14px] text-white/50 leading-relaxed font-medium">
                {finding}
              </p>
            </motion.div>
          ))}
          </div>
        </div>
      )}
    </div>
  );
}

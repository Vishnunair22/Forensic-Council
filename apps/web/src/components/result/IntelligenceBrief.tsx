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
          className="relative px-8 py-10 rounded-3xl premium-glass border-border-subtle overflow-hidden group hover:bg-surface-3 transition-colors shadow-2xl"
        >
          <div className="absolute top-0 left-0 w-1.5 h-full bg-primary/20" />
          <Quote className="absolute top-6 right-8 w-16 h-16 text-primary/5 pointer-events-none" />
          
          <div className="flex items-center gap-3 mb-6 text-white/20">
            <Hash className="w-4 h-4 text-primary/40" />
            <span className="text-xs font-bold tracking-wide text-white/60">Executive Briefing</span>
          </div>
          
          <p className="text-xl sm:text-2xl font-medium text-white/80 leading-relaxed italic text-balance font-sans">
            &ldquo;{verdictSentence}&rdquo;
          </p>
        </motion.div>
      )}

      {/* Structured Key Findings */}
      {keyFindings.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center gap-4">
            <span className="text-xs font-bold tracking-wide text-white/40">Key Findings</span>
            <span className={clsx(
              "text-[11px] font-bold px-3 py-1 rounded-full tracking-wide",
              isDeepPhase
                ? "bg-accent/10 border border-accent/20 text-accent shadow-[0_0_15px_rgba(139,92,246,0.1)]"
                : "bg-primary/10 border border-primary/20 text-primary shadow-[0_0_15px_rgba(34,211,238,0.1)]"
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
              className="flex items-start gap-4 p-6 rounded-2xl premium-card group shadow-lg"
            >
              <AlertCircle className="w-5 h-5 text-primary/30 shrink-0 mt-0.5 group-hover:text-primary transition-colors" />
              <p className="text-[14px] text-white/60 leading-relaxed font-medium">
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

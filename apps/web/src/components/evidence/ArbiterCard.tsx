"use client";

import React from "react";
import { motion } from "framer-motion";
import { Scale, Sparkles, Loader2, CheckCircle2, Zap, BrainCircuit, Activity } from "lucide-react";
import { clsx } from "clsx";

interface ArbiterCardProps {
  status: string | null;
  thinking: string | null;
  phase: "initial" | "deep";
  allAgentsDone: boolean;
}

export function ArbiterCard({ status, thinking, phase, allAgentsDone }: ArbiterCardProps) {
  const isPreWarming = status === "pre_warming" || (allAgentsDone && !status);
  const isPreWarmComplete = status === "pre_warm_complete";
  const isSynthesizing = status === "synthesizing" || status === "deliberating";
  const isReady = status === "ready" || status === "complete";

  const getStatusDisplay = () => {
    if (isReady) return { label: "Consensus Ready", icon: CheckCircle2, color: "text-emerald-400", bg: "bg-emerald-500/20", border: "border-emerald-500/30" };
    if (isSynthesizing) return { label: "Synthesizing", icon: BrainCircuit, color: "text-blue-400", bg: "bg-blue-500/20", border: "border-blue-500/30" };
    if (isPreWarmComplete) return { label: "State Cached", icon: CheckCircle2, color: "text-emerald-400/70", bg: "bg-emerald-500/10", border: "border-emerald-500/20" };
    if (isPreWarming) return { label: "Pre-warming", icon: Zap, color: "text-amber-400", bg: "bg-amber-500/10", border: "border-amber-500/20" };
    return { label: "Standing By", icon: Activity, color: "text-white/20", bg: "bg-white/5", border: "border-white/10" };
  };

  const display = getStatusDisplay();
  const Icon = display.icon;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95, y: 10 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      className="relative group h-full"
    >
      {/* Premium Glow Effect */}
      <div className={clsx(
        "absolute -inset-0.5 rounded-2xl blur opacity-10 transition duration-1000 animate-pulse",
        isReady ? "bg-emerald-500" : isSynthesizing ? "bg-blue-500" : "bg-primary"
      )} />
      
      <div className="relative h-full bg-[#070A12] border border-white/8 rounded-2xl overflow-hidden shadow-[0_8px_32px_rgba(0,0,0,0.4),_0_1px_0_rgba(255,255,255,0.05)_inset] flex flex-col">
        {/* Header Section */}
        <div className="px-5 py-4 border-b border-white/5 bg-white/[0.02] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={clsx(
              "w-10 h-10 rounded-xl border flex items-center justify-center transition-colors duration-500",
              display.bg, display.border
            )}>
              <Scale className={clsx("w-5 h-5", display.color)} />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white tracking-tight">Council Arbiter</h3>
              <p className="text-[9px] font-mono text-white/30 uppercase tracking-widest font-bold">
                {phase === "deep" ? "Phase_2_Synthesis" : "Phase_1_Synthesis"}
              </p>
            </div>
          </div>
          
          <div className={clsx(
            "px-2 py-1 rounded-md border flex items-center gap-1.5 transition-all duration-500",
            display.bg, display.border
          )}>
            <Icon className={clsx("w-3 h-3", display.color, (isPreWarming || isSynthesizing) && "animate-pulse")} />
            <span className={clsx("text-[9px] font-bold uppercase tracking-tighter", display.color)}>
              {display.label}
            </span>
          </div>
        </div>

        {/* Content Section */}
        <div className="p-5 flex flex-col flex-1 justify-between gap-6">
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono text-white/30 uppercase tracking-widest">Synthesis_Engine</span>
                <span className="text-[10px] font-mono text-white/50">
                  {isReady ? "COMPLETED" : isSynthesizing ? "COMPUTING" : "LATENCY_OPTIMISED"}
                </span>
              </div>
              <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
                <motion.div 
                  className={clsx(
                    "h-full shadow-[0_0_10px_rgba(var(--color-primary-rgb),0.4)]",
                    isReady ? "bg-emerald-500" : "bg-gradient-to-r from-[var(--color-primary)] to-blue-400"
                  )}
                  initial={{ width: "0%" }}
                  animate={{ 
                    width: isReady ? "100%" : isPreWarmComplete ? "85%" : isPreWarming ? "40%" : isSynthesizing ? "65%" : "0%" 
                  }}
                  transition={{ duration: 1.5, ease: "circOut" }}
                />
              </div>
            </div>

            <div className="bg-white/[0.03] rounded-xl p-4 border border-white/5 flex flex-col gap-3 min-h-[80px]">
              <div className="flex items-start gap-3">
                {isReady ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                ) : isPreWarming || isSynthesizing ? (
                  <Loader2 className="w-4 h-4 text-[var(--color-primary)] animate-spin shrink-0 mt-0.5" />
                ) : (
                  <Activity className="w-4 h-4 text-white/20 shrink-0 mt-0.5" />
                )}
                <div className="flex flex-col gap-1">
                  <p className="text-xs text-white/80 leading-relaxed font-medium">
                    {thinking || (isPreWarming ? "Speculative synthesis running to reduce report latency..." : "Awaiting final agent corroborations...")}
                  </p>
                  {isPreWarming && (
                    <p className="text-[10px] text-white/40 italic">
                      Background pre-warm active.
                    </p>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Activity Visualizer */}
          <div className="flex items-center gap-1.5 h-4 px-1">
            {[...Array(12)].map((_, i) => (
              <motion.div
                key={i}
                className={clsx(
                  "w-1 rounded-full transition-colors duration-500",
                  isReady ? "bg-emerald-500/40" : "bg-[var(--color-primary)]/30"
                )}
                animate={{
                  height: isReady ? 4 : [4, 12, 4],
                  opacity: isReady ? 0.2 : [0.3, 0.6, 0.3]
                }}
                transition={{
                  duration: 1.5,
                  repeat: Infinity,
                  delay: i * 0.1,
                  ease: "easeInOut"
                }}
              />
            ))}
            <span className="ml-auto text-[9px] font-mono text-white/20 uppercase">Arbiter_Pulse</span>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

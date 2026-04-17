"use client";

import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle2, Upload, Wifi, Zap } from "lucide-react";
import { clsx } from "clsx";

export interface LoadingOverlayProps {
  liveText?: string;
  dispatchedCount?: number;
  totalAgents?: number;
}

const PHASES = [
  {
    id: "upload",
    Icon: Upload,
    label: "Uploading Evidence",
    detail: "Encrypted transfer to secure forensic pipeline",
    keywords: ["upload", "uploading", "secure pipeline"],
  },
  {
    id: "connect",
    Icon: Wifi,
    label: "Establishing Stream",
    detail: "Connecting to real-time analysis channel",
    keywords: ["connect", "stream", "pipeline", "initializ"],
  },
  {
    id: "dispatch",
    Icon: Zap,
    label: "Dispatching Agents",
    detail: "Initialising specialist forensic units",
    keywords: ["dispatch", "agent", "ready"],
  },
] as const;

function getPhaseIndex(text: string): number {
  const t = text.toLowerCase();
  if (t.includes("agent") || t.includes("dispatch")) return 2;
  if (t.includes("connect") || t.includes("stream")) return 1;
  return 0;
}

export function LoadingOverlay({ liveText, dispatchedCount = 0, totalAgents = 6 }: LoadingOverlayProps) {
  void totalAgents;
  const currentPhase = getPhaseIndex(liveText || "");
  const effectivePhase = dispatchedCount > 0 ? 2 : currentPhase;

  return (
    <motion.div
      className="fixed inset-0 z-[300] flex flex-col items-center justify-center px-6 selection:bg-transparent"
      style={{
        background: "rgba(0, 0, 0, 0.9)",
      }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: 0.5, ease: "easeInOut" } }}
      transition={{ duration: 0.2 }}
    >
      <div className="relative z-10 flex flex-col items-center w-full max-w-sm">
        {/* Telemetry Header */}
        <motion.div
          initial={{ y: 10, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          className="flex items-center gap-2.5 mb-8"
        >
          <div className="w-1.5 h-1.5 rounded-full bg-cyan-500 animate-pulse shadow-[0_0_8px_rgba(6,182,212,0.4)]" />
          <span className="text-[10px] font-bold tracking-widest text-cyan-500/40">
            Forensic Protocol 2026
          </span>
        </motion.div>

        {/* Title Area */}
        <div className="text-center mb-12">
            <motion.h1
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.1 }}
            className="text-4xl font-bold tracking-tight text-white mb-2 font-heading"
            >
            Initializing <span className="text-cyan-400">Stream</span>
            </motion.h1>
            <motion.div 
                initial={{ scaleX: 0 }}
                animate={{ scaleX: 1 }}
                transition={{ delay: 0.3, duration: 0.8 }}
                className="h-[1px] w-32 mx-auto bg-gradient-to-r from-transparent via-cyan-500/40 to-transparent" 
            />
        </div>

        {/* Phase Timeline */}
        <div className="w-full flex flex-col gap-3">
          {PHASES.map((phase, idx) => {
            const isDone = idx < effectivePhase;
            const isActive = idx === effectivePhase;
            const isPending = idx > effectivePhase;
            const { Icon } = phase;

            return (
              <motion.div
                key={phase.id}
                initial={{ x: -10, opacity: 0 }}
                animate={{ x: 0, opacity: 1 }}
                transition={{ delay: 0.2 + idx * 0.1 }}
                className={clsx(
                  "flex items-center gap-4 px-5 py-4 rounded-2xl border transition-all duration-500",
                  isActive && "bg-cyan-500/[0.05] border-cyan-500/20 shadow-[0_0_20px_rgba(6,182,212,0.1)]",
                  isDone && "bg-emerald-500/[0.03] border-emerald-500/10 opacity-60",
                  isPending && "bg-white/[0.01] border-white/5 opacity-20"
                )}
              >
                <div className={clsx(
                    "w-10 h-10 rounded-xl flex items-center justify-center shrink-0 border transition-all duration-500",
                    isActive && "bg-cyan-500/20 border-cyan-500/40 text-cyan-400",
                    isDone && "bg-emerald-500/10 border-emerald-500/30 text-emerald-400",
                    isPending && "bg-white/5 border-white/5 text-white/10"
                )}>
                  <AnimatePresence mode="wait">
                    {isDone ? (
                      <motion.div key="done" initial={{ scale: 0 }} animate={{ scale: 1 }}>
                        <CheckCircle2 className="w-4 h-4" />
                      </motion.div>
                    ) : (
                      <motion.div key="icon" initial={{ scale: 0.8 }} animate={{ scale: 1 }}>
                        <Icon className={clsx("w-4 h-4", isActive && "animate-pulse")} />
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={clsx(
                        "text-[11px] font-bold tracking-tight",
                        isActive ? "text-white" : "text-white/40"
                    )}>{phase.label}</span>
                    {isActive && (
                        <div className="flex gap-1">
                            {[0, 1, 2].map(i => (
                                <motion.div 
                                    key={i} 
                                    className="w-1 h-1 bg-cyan-500 rounded-full" 
                                    animate={{ opacity: [0.2, 1, 0.2] }} 
                                    transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }} 
                                />
                            ))}
                        </div>
                    )}
                  </div>
                  <p className="text-[10px] font-medium text-white/20 mt-0.5 tracking-tight">{phase.detail}</p>
                </div>
              </motion.div>
            );
          })}
        </div>

        {/* Live Status */}
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.5 }}
          className="mt-10 text-[11px] font-mono font-bold tracking-widest text-cyan-500/30 text-center px-4"
        >
          {liveText || "Initializing Workspace..."}
        </motion.p>
      </div>
    </motion.div>
  );
}

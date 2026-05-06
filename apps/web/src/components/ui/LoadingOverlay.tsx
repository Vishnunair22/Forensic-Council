"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle2, Loader2, Upload, Wifi, Zap } from "lucide-react";
import { clsx } from "clsx";

export interface LoadingOverlayProps {
  liveText?: string;
  dispatchedCount?: number;
  totalAgents?: number;
  title?: string;
  subtitle?: string;
  variant?: "full" | "minimal";
  exitDuration?: number;
}

const PHASES = [
  {
    id: "upload",
    Icon: Upload,
    label: "Securing Evidence",
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
    detail: "Initializing specialist forensic units",
    keywords: ["dispatch", "agent", "ready"],
  },
] as const;

function getPhaseIndex(text: string): number {
  const t = text.toLowerCase();
  if (t.includes("agent") || t.includes("dispatch")) return 2;
  if (t.includes("connect") || t.includes("stream")) return 1;
  return 0;
}

function sanitizeLiveText(text: string): string {
  return text.replace(/^(PIPELINE|UPLOAD|AUTH|SYSTEM|CORE|AGENT):/i, "").trim();
}

export function LoadingOverlay({
  liveText,
  dispatchedCount = 0,
  totalAgents = 6,
  title = "Preparing Analysis",
  subtitle = "Forensic Protocol 2026",
  variant = "full",
  exitDuration = 0.4,
}: LoadingOverlayProps) {
  const [revealedUpTo, setRevealedUpTo] = useState(0);
  const currentPhase = getPhaseIndex(liveText || "");
  const effectivePhase = dispatchedCount > 0 ? 2 : currentPhase;
  
  const progress = Math.min(
    92,
    Math.max(18, Math.round(((effectivePhase + 1) / PHASES.length) * 72) + dispatchedCount * 4),
  );

  useEffect(() => {
    setRevealedUpTo(prev => Math.max(prev, effectivePhase));
  }, [effectivePhase]);

  const sanitizedText = sanitizeLiveText(liveText || "");

  if (variant === "minimal") {
    const phase = PHASES[effectivePhase];
    const PhaseIcon = phase.Icon;

    return (
      <motion.div
        className="fixed inset-0 z-[10000] flex items-end justify-center pb-16 px-6"
        style={{ background: "rgba(5,7,13,0.85)", backdropFilter: "blur(24px)", WebkitBackdropFilter: "blur(24px)" }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0, transition: { duration: exitDuration } }}
        transition={{ duration: 0.2, ease: "easeOut" }}
      >
        {/* Horizontal Phase Card */}
        <motion.div
          initial={{ opacity: 0, y: 24, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1], delay: 0.05 }}
          className="w-full max-w-md"
        >
          <div className="bg-[#070A12] border border-white/10 rounded-2xl shadow-[0_24px_64px_rgba(0,0,0,0.7)] overflow-hidden">
            {/* Progress bar — top edge */}
            <div className="h-[2px] w-full bg-white/5">
              <motion.div
                className="h-full bg-primary rounded-full"
                animate={{ width: `${progress}%` }}
                transition={{ duration: 0.6, ease: "easeOut" }}
              />
            </div>

            {/* Card Body */}
            <div className="flex items-center gap-5 px-6 py-5">
              {/* Icon */}
              <div className="shrink-0 w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center relative">
                <AnimatePresence mode="wait">
                  <motion.div
                    key={effectivePhase}
                    initial={{ opacity: 0, scale: 0.6, rotate: -15 }}
                    animate={{ opacity: 1, scale: 1, rotate: 0 }}
                    exit={{ opacity: 0, scale: 1.2, rotate: 15 }}
                    transition={{ type: "spring", damping: 18, stiffness: 300 }}
                  >
                    <PhaseIcon className="w-5 h-5 text-primary" />
                  </motion.div>
                </AnimatePresence>
                <motion.div
                  className="absolute inset-0 rounded-xl border border-primary/30"
                  animate={{ opacity: [0.3, 0.7, 0.3] }}
                  transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                />
              </div>

              {/* Text */}
              <div className="flex-1 min-w-0">
                <AnimatePresence mode="wait">
                  <motion.p
                    key={`label-${effectivePhase}`}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.22, ease: "easeOut" }}
                    className="text-sm font-bold text-white tracking-tight"
                  >
                    {phase.label}
                  </motion.p>
                </AnimatePresence>
                <AnimatePresence mode="wait">
                  <motion.p
                    key={sanitizedText || phase.detail}
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    transition={{ duration: 0.2, ease: "easeOut", delay: 0.05 }}
                    className="text-xs font-mono text-white/40 mt-0.5 truncate"
                    role="status"
                    aria-live="polite"
                  >
                    {sanitizedText || phase.detail}
                  </motion.p>
                </AnimatePresence>
              </div>

              {/* Phase pip indicators */}
              <div className="shrink-0 flex flex-col gap-1.5 items-center">
                {PHASES.map((_, i) => (
                  <motion.div
                    key={i}
                    className="rounded-full bg-primary"
                    animate={{
                      width: i === effectivePhase ? 16 : 4,
                      height: 4,
                      opacity: i < effectivePhase ? 0.8 : i === effectivePhase ? 1 : 0.15,
                    }}
                    transition={{ type: "spring", damping: 22, stiffness: 280 }}
                  />
                ))}
              </div>
            </div>
          </div>
        </motion.div>
      </motion.div>
    );
  }

  return (
    <motion.div
      className="fixed inset-0 z-[10000] flex flex-col items-center justify-center px-6 selection:bg-transparent"
      style={{
        background: "rgba(0, 0, 0, 0.95)",
        backdropFilter: "blur(24px)",
        WebkitBackdropFilter: "blur(24px)",
      }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: 0.4, ease: "easeOut" } }}
      transition={{ duration: 0.12, ease: "easeOut" }}
    >
      <div className="relative z-10 flex flex-col items-center w-full max-w-md">
        {/* Telemetry Header */}
        <motion.div
          initial={{ y: 10, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          className="flex items-center gap-2.5 mb-8"
        >
          <div className="w-1.5 h-1.5 rounded-full bg-primary" />
          <span className="text-xs font-semibold tracking-wide text-white/50">
            {subtitle}
          </span>
        </motion.div>

        <div className="text-center mb-10 flex flex-col items-center">
          <Loader2 className="w-12 h-12 text-primary animate-spin mb-6" />
          <motion.h1
            initial={{ y: 12, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.05 }}
            className="text-3xl font-black tracking-tight text-white mb-3"
          >
            {title}
          </motion.h1>
          <p className="min-h-[2.5rem] text-sm font-mono font-semibold tracking-wide text-primary/70 text-center px-4" role="status" aria-live="polite">
            {sanitizedText || "Opening live investigation stream..."}
          </p>
        </div>

        <div className="w-full mb-12">
          <div className="flex items-center justify-between mb-3 text-[10px] font-mono text-white/30 uppercase tracking-widest">
            <span>Core Protocol Ingestion</span>
            <span>{Math.min(dispatchedCount, totalAgents)}/{totalAgents} Units</span>
          </div>
          <div className="h-1.5 rounded-full bg-white/5 overflow-hidden border border-white/5 p-[1px]">
            <motion.div
              className="h-full bg-primary shadow-[0_0_24px_rgba(var(--color-primary-rgb),0.6)] rounded-full"
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.4, ease: "easeOut" }}
            />
          </div>
        </div>

        {/* Phase Timeline */}
        <div className="w-full flex flex-col gap-3">
          <AnimatePresence>
            {PHASES.map((phase, idx) => {
              if (idx > revealedUpTo) return null;

              const isDone = idx < effectivePhase;
              const isActive = idx === effectivePhase;
              const { Icon } = phase;

              return (
                <motion.div
                  key={phase.id}
                  initial={{ y: 18, scale: 0.96, opacity: 0 }}
                  animate={{ y: 0, scale: 1, opacity: 1 }}
                  transition={{ 
                    type: "spring", 
                    damping: 20, 
                    stiffness: 200,
                  }}
                  className={clsx(
                    "flex items-center gap-5 px-7 py-6 rounded-[1.5rem] border transition-all duration-700",
                    isActive && "bg-primary/[0.04] border-primary/20 shadow-[0_8px_32px_rgba(0,255,65,0.06)]",
                    isDone && "bg-white/[0.01] border-white/5 opacity-40",
                  )}
                >
                  <div className={clsx(
                      "w-12 h-12 rounded-2xl flex items-center justify-center shrink-0 border transition-all duration-700",
                      isActive && "bg-primary/20 border-primary/40 text-primary shadow-[0_0_20px_rgba(var(--color-primary-rgb),0.2)]",
                      isDone && "bg-white/5 border-white/10 text-white/40",
                  )}>
                    <AnimatePresence mode="wait">
                      {isDone ? (
                        <motion.div key="done" initial={{ scale: 0 }} animate={{ scale: 1 }}>
                          <CheckCircle2 className="w-5 h-5" />
                        </motion.div>
                      ) : (
                        <motion.div key="icon" initial={{ scale: 0.8 }} animate={{ scale: 1 }}>
                          <Icon className={clsx("w-5 h-5", isActive && "animate-pulse")} />
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={clsx(
                          "text-base font-bold tracking-tight",
                          isActive ? "text-white" : "text-white/40"
                      )}>{phase.label}</span>
                    </div>
                    <AnimatePresence mode="wait">
                      <motion.p 
                        key={isActive ? sanitizedText : phase.detail}
                        initial={{ opacity: 0, y: 2 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -2 }}
                        className="text-[13px] font-medium text-white/50 mt-1 leading-snug"
                      >
                        {isActive ? (sanitizedText || phase.detail) : phase.detail}
                      </motion.p>
                    </AnimatePresence>
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      </div>
    </motion.div>
  );
}

"use client";

import React from "react";
import { motion } from "framer-motion";
import { Scale, Loader2, CheckCircle2, Zap, BrainCircuit, Activity } from "lucide-react";
import { clsx } from "clsx";
import { AnimatePresence } from "framer-motion";

const ARBITER_PHRASES = [
  "Compiling agent findings into the final report.",
  "Comparing corroborating and conflicting tool signals.",
  "Synthesizing per-agent verdicts and confidence scores.",
  "Preparing the signed council report.",
];

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

  const [phraseIndex, setPhraseIndex] = React.useState(0);

  React.useEffect(() => {
    if (!isSynthesizing) return;
    const interval = setInterval(() => {
      setPhraseIndex(prev => (prev + 1) % ARBITER_PHRASES.length);
    }, 3000);
    return () => clearInterval(interval);
  }, [isSynthesizing]);

  const cleanThinking = React.useMemo(() => {
    if (!thinking) return "";
    return thinking
      .replace(/Speculative synthesis complete\.?\s*/gi, "Council evidence weights are ready. ")
      .replace(/Initial analysis complete\. Awaiting analyst decision\.?/gi, "Council evidence weights are ready for your decision.")
      .replace(/Deep analysis complete\. Awaiting analyst request for arbiter synthesis\.?/gi, "Deep findings are ready for final report synthesis.")
      .replace(/\.\.\./g, ".")
      .replace(/…/g, ".")
      .trim();
  }, [thinking]);

  const getStatusDisplay = () => {
    if (isReady) return { label: "Consensus Ready", icon: CheckCircle2, color: "text-success", bg: "bg-success/12 border-success/40", border: "border-success/30" };
    if (isSynthesizing) return { label: "Synthesizing", icon: BrainCircuit, color: "text-[var(--color-primary)]", bg: "bg-[var(--color-primary)]/12 border-[var(--color-primary)]/40", border: "border-[var(--color-primary)]/30" };
    if (isPreWarmComplete) return { label: "Ready", icon: CheckCircle2, color: "text-success/70", bg: "bg-success/10 border-success/20", border: "border-success/20" };
    if (isPreWarming) return { label: "Preparing", icon: Zap, color: "text-warning", bg: "bg-warning/10 border-warning/20", border: "border-warning/20" };
    return { label: "Awaiting Agents", icon: Activity, color: "fc-text-faint", bg: "bg-white/[0.06] border-white/15", border: "border-white/10" };
  };

  const display = getStatusDisplay();
  
  const getDisplayText = () => {
    if (isReady) {
      return "Council report is ready. Opening the result page when the signed report is available.";
    }
    if (cleanThinking) {
      return cleanThinking;
    }
    if (isSynthesizing) {
      return ARBITER_PHRASES[phraseIndex];
    }
    if (status === "pre_warm_complete") {
      return "Pre-warm complete. Ready to synthesize.";
    }
    if (status === "pre_warming") {
      return "Speculative synthesis engine is pre-warming in the background.";
    }
    if (allAgentsDone) {
      if (phase === "deep") {
        return "Deep analysis complete. Ready for final report synthesis.";
      }
      return "Initial analysis complete. Awaiting analyst decision to proceed.";
    }
    return `Arbiter is waiting for ${phase === "deep" ? "deep" : "initial"} agent findings.`;
  };

  const displayText = getDisplayText();

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95, y: 10 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      className="relative flex flex-col overflow-hidden min-h-[520px] max-h-[860px] fc-surface-quiet h-full"
      data-testid="agent-card-arbiter"
    >
      {/* --- Card Header --- */}
      <div className="p-7 pb-5 border-b border-white/5 relative z-10 bg-transparent">
        <div className="flex items-start justify-between mb-8">
          <div className="flex items-center gap-5">
            {/* Arbiter Icon */}
            <div className="relative w-16 h-16 flex items-center justify-center bg-transparent border border-white/5 rounded-xl">
              <Scale className={clsx("w-7 h-7 relative z-10 transition-colors duration-500", display.color)} />
            </div>

            <div>
              <div className="flex items-center gap-2 mb-1.5">
                <h3 className="text-2xl font-heading font-bold text-white tracking-tight">Council Arbiter</h3>
              </div>
              <div className="flex items-center gap-2">
                <span className={clsx(
                  "fc-badge border transition-colors duration-500",
                  display.bg
                )}>
                  {display.label}
                </span>
                <span className="fc-eyebrow fc-text-faint">
                  {phase === "deep" ? "Phase 2 Synthesis" : "Phase 1 Synthesis"}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="p-7 flex flex-col flex-1 justify-between gap-6 relative z-10">
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="fc-eyebrow fc-text-faint">Synthesis Engine</span>
              <span className="fc-eyebrow fc-text-faint">
                {isReady ? "Completed" : isSynthesizing ? "Computing" : "Preparing"}
              </span>
            </div>
            <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
              <motion.div
                className={clsx(
                  "h-full shadow-[0_0_10px_rgba(var(--color-primary-rgb),0.4)]",
                  isReady ? "bg-success" : "bg-gradient-to-r from-[var(--color-primary)] to-[var(--color-primary-soft)]"
                )}
                initial={{ width: "0%" }}
                animate={{
                  width: isReady ? "100%" : isPreWarmComplete ? "85%" : isSynthesizing ? "65%" : isPreWarming ? "40%" : "5%"
                }}
                transition={{ duration: 1.5, ease: "circOut" }}
              />
            </div>
          </div>

          <div className="flex flex-col gap-3 min-h-[80px] pt-4 border-t border-white/5 mt-2">
            <div className="flex items-start gap-3">
              {isReady ? (
                <CheckCircle2 className="w-4 h-4 text-success shrink-0 mt-0.5" />
              ) : isPreWarming || isSynthesizing ? (
                <Loader2 className="w-4 h-4 text-[var(--color-primary)] animate-spin shrink-0 mt-0.5" />
              ) : (
                <Activity className="w-4 h-4 text-white/20 shrink-0 mt-0.5" />
              )}
              <div className="flex flex-col gap-1">
                <AnimatePresence mode="wait">
                  <motion.p
                    key={displayText}
                    initial={{ opacity: 0, y: 3 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -3 }}
                    transition={{ duration: 0.3 }}
                    className="text-xs text-white/80 leading-relaxed font-medium"
                  >
                    {displayText}
                  </motion.p>
                </AnimatePresence>
                {isPreWarming && (
                  <p className="text-xs fc-text-faint italic">
                    Evidence weights are being prepared in the background.
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1.5 h-4 px-1">
          {[...Array(12)].map((_, i) => (
            <motion.div
              key={i}
              className={clsx(
                "w-1 rounded-full transition-colors duration-500",
                isReady ? "bg-success/40" : "bg-[var(--color-primary)]/30"
              )}
              animate={{
                height: isReady ? 4 : [4, 10, 4],
                opacity: isReady ? 0.2 : [0.3, 0.5, 0.3]
              }}
              transition={{
                duration: 2.5,
                repeat: Infinity,
                delay: i * 0.15,
                ease: "easeInOut"
              }}
            />
          ))}
          <span className="ml-auto fc-eyebrow fc-text-faint">Arbiter Pulse</span>
        </div>
      </div>
    </motion.div>
  );
}

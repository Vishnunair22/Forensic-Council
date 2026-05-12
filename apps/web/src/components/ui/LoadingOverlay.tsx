"use client";

import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { Upload, Wifi, Zap } from "lucide-react";
import type { SoundType } from "@/hooks/useSound";

export interface LoadingOverlayProps {
  liveText?: string;
  dispatchedCount?: number;
  playSound?: (sound: SoundType) => void;
  exitDuration?: number;
}

const PHASES = [
  {
    id: "upload",
    Icon: Upload,
    label: "Encrypting Evidence",
    detail: "Transferring to secure forensic pipeline",
  },
  {
    id: "connect",
    Icon: Wifi,
    label: "Connecting to Analysis",
    detail: "Opening live investigation channel",
  },
  {
    id: "dispatch",
    Icon: Zap,
    label: "Dispatching Agents",
    detail: "Activating specialist analysis units",
  },
] as const;

function resolvePhaseIndex(text: string, dispatchedCount: number): number {
  if (dispatchedCount > 0) return 2;
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
  playSound,
  exitDuration = 0.4,
}: LoadingOverlayProps) {
  const sanitizedText = sanitizeLiveText(liveText || "");
  const targetIndex = resolvePhaseIndex(liveText || "", dispatchedCount);
  const prefersReducedMotion = useReducedMotion();

  const [phaseIndex, setPhaseIndex] = useState(targetIndex);
  useEffect(() => {
    setPhaseIndex((prev) => Math.max(prev, targetIndex));
  }, [targetIndex]);

  // Play sound on each phase advance (skip initial mount)
  const prevPhaseRef = useRef(phaseIndex);
  useEffect(() => {
    if (phaseIndex !== prevPhaseRef.current) {
      playSound?.("scan");
      prevPhaseRef.current = phaseIndex;
    }
  }, [phaseIndex, playSound]);

  const clampedPhase = Math.min(phaseIndex, PHASES.length - 1);
  const phase = PHASES[clampedPhase];
  const PhaseIcon = phase.Icon;
  const progress = Math.min(
    92,
    Math.max(12, Math.round(((clampedPhase + 1) / PHASES.length) * 72) + dispatchedCount * 3),
  );

  return createPortal(
    <motion.div
      className="fixed inset-0 z-[10000] flex flex-col items-center justify-center px-6 select-none"
      style={{
        background: "rgba(2, 6, 23, 0.97)",
        backdropFilter: "blur(32px)",
        WebkitBackdropFilter: "blur(32px)",
      }}
      initial={prefersReducedMotion ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={prefersReducedMotion ? {} : { opacity: 0, transition: { duration: exitDuration, ease: "easeIn" } }}
      transition={{ duration: 0.14, ease: "easeOut" }}
    >
      {/* Ambient glow */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden" aria-hidden="true">
        <motion.div
          className="absolute top-[42%] left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[240px] rounded-full blur-[88px]"
          style={{ background: "radial-gradient(ellipse, rgba(79,142,247,0.07) 0%, transparent 70%)" }}
          animate={prefersReducedMotion ? {} : { opacity: [0.5, 1, 0.5] }}
          transition={prefersReducedMotion ? {} : { duration: 4, repeat: Infinity, ease: "easeInOut" }}
        />
      </div>

      <div className="relative z-10 flex flex-col items-center w-full max-w-sm">
        {/* Live indicator header */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.07, duration: 0.28, ease: "easeOut" }}
          className="flex items-center gap-2.5 mb-10"
          aria-hidden="true"
        >
          <motion.div
            className="w-1.5 h-1.5 rounded-full bg-primary"
            animate={prefersReducedMotion ? {} : { scale: [1, 1.5, 1], opacity: [1, 0.35, 1] }}
            transition={prefersReducedMotion ? {} : { duration: 1.4, repeat: Infinity, ease: "easeInOut" }}
          />
          <span className="text-[10px] font-mono font-bold tracking-[0.28em] uppercase text-muted-decorative">
            Forensic Protocol Active
          </span>
          <motion.div
            className="w-1.5 h-1.5 rounded-full bg-primary"
            animate={prefersReducedMotion ? {} : { scale: [1, 1.5, 1], opacity: [0.35, 1, 0.35] }}
            transition={prefersReducedMotion ? {} : { duration: 1.4, repeat: Infinity, ease: "easeInOut", delay: 0.7 }}
          />
        </motion.div>

        {/* Horizontal gradient phase card */}
        <div className="w-full mb-5" style={{ overflow: "hidden" }}>
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={`phase-card-${clampedPhase}`}
              initial={{ opacity: 0, x: 52, scale: 0.97 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: -52, scale: 0.97 }}
              transition={{ duration: 0.38, ease: [0.16, 1, 0.3, 1] }}
            >
              <div
                className="relative rounded-2xl overflow-hidden"
                style={{
                  background: "linear-gradient(108deg, #060d1c 0%, #080f24 60%, rgba(79,142,247,0.055) 100%)",
                  border: "1px solid rgba(79,142,247,0.11)",
                  boxShadow: "0 24px 60px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.03)",
                }}
              >
                {/* Top progress strip — gradient */}
                <div className="h-[1.5px] w-full" style={{ background: "rgba(255,255,255,0.04)" }}>
                  <motion.div
                    className="h-full rounded-full"
                    style={{
                      background: "linear-gradient(90deg, rgba(79,142,247,0.7) 0%, rgba(165,200,255,0.9) 100%)",
                    }}
                    animate={{ width: `${progress}%` }}
                    transition={{ duration: 0.85, ease: [0.4, 0, 0.2, 1] }}
                  />
                </div>

                <div className="px-5 py-5 flex items-center gap-4">
                  {/* Phase icon */}
                  <div
                    className="relative shrink-0 w-11 h-11 rounded-xl flex items-center justify-center"
                    aria-hidden="true"
                    style={{
                      background: "rgba(79,142,247,0.08)",
                      border: "1px solid rgba(79,142,247,0.14)",
                    }}
                  >
                    <PhaseIcon className="w-[18px] h-[18px] text-primary relative z-10" />
                    <motion.div
                      className="absolute inset-0 rounded-xl"
                      style={{ border: "1px solid rgba(79,142,247,0.38)" }}
                      animate={prefersReducedMotion ? {} : { opacity: [0.2, 0.65, 0.2], scale: [1, 1.05, 1] }}
                      transition={prefersReducedMotion ? {} : { duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
                    />
                  </div>

                  {/* Text block */}
                  <div className="flex-1 min-w-0">
                    {/* Phase label — bold title */}
                    <div className="flex items-center gap-2 mb-[5px]">
                      <span
                        className="text-[13px] font-bold tracking-tight leading-none truncate"
                        style={{ color: "rgba(255,255,255,0.92)" }}
                      >
                        {phase.label}
                      </span>
                      <motion.div
                        className="w-[5px] h-[5px] rounded-full bg-primary shrink-0"
                        animate={{ opacity: [1, 0.12, 1] }}
                        transition={{ duration: 0.95, repeat: Infinity, ease: "easeInOut" }}
                        aria-hidden="true"
                      />
                    </div>
                    {/* Live detail — crossfades on each backend update */}
                    <AnimatePresence mode="wait">
                      <motion.p
                        key={sanitizedText || phase.detail}
                        initial={{ opacity: 0, y: 4 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }}
                        transition={{ duration: 0.2, ease: "easeOut" }}
                        className="text-[11px] font-mono leading-snug truncate"
                        style={{ color: "rgba(255,255,255,0.38)" }}
                        role="status"
                        aria-live="polite"
                      >
                        {sanitizedText || phase.detail}
                      </motion.p>
                    </AnimatePresence>
                  </div>

                  {/* Spinner */}
                  <motion.div
                    className="shrink-0 w-[18px] h-[18px] rounded-full border-[1.5px]"
                    style={{
                      borderColor: "rgba(79,142,247,0.12)",
                      borderTopColor: "rgba(79,142,247,0.72)",
                    }}
                    animate={prefersReducedMotion ? {} : { rotate: 360 }}
                    transition={prefersReducedMotion ? {} : { duration: 1.6, repeat: Infinity, ease: "linear" }}
                    aria-hidden="true"
                  />
                </div>

                {/* Right-side directional glow */}
                <div
                  className="absolute inset-y-0 right-0 w-2/5 pointer-events-none"
                  style={{
                    background: "linear-gradient(270deg, rgba(79,142,247,0.045) 0%, transparent 100%)",
                  }}
                  aria-hidden="true"
                />
              </div>
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Phase step dots */}
        <div className="flex items-center gap-[7px]" aria-hidden="true">
          {PHASES.map((p, i) => (
            <motion.div
              key={p.id}
              className={`rounded-full ${i <= clampedPhase ? "bg-primary" : "bg-white/[0.12]"}`}
              animate={{
                width: i === clampedPhase ? 22 : i < clampedPhase ? 7 : 5,
                height: 3,
                opacity: i < clampedPhase ? 0.55 : i === clampedPhase ? 1 : 0.2,
              }}
              transition={{ type: "spring", damping: 26, stiffness: 320 }}
            />
          ))}
        </div>
      </div>
    </motion.div>,
    document.body
  );
}

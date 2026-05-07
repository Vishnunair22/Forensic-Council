"use client";

import { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Upload, Wifi, Zap } from "lucide-react";

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
    label: "Encrypting Evidence",
    detail: "Transferring to secure forensic pipeline",
  },
  {
    id: "connect",
    Icon: Wifi,
    label: "Connecting to Evidence Analysis",
    detail: "Opening live investigation channel",
  },
  {
    id: "dispatch",
    Icon: Zap,
    label: "Dispatching Forensic Agents",
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
  variant = "full",
  exitDuration = 0.4,
}: LoadingOverlayProps) {
  const sanitizedText = sanitizeLiveText(liveText || "");
  const targetIndex = resolvePhaseIndex(liveText || "", dispatchedCount);

  // Phase index can only advance forward — never regress
  const [phaseIndex, setPhaseIndex] = useState(targetIndex);
  useEffect(() => {
    setPhaseIndex((prev) => Math.max(prev, targetIndex));
  }, [targetIndex]);

  const clampedPhase = Math.min(phaseIndex, PHASES.length - 1);
  const phase = PHASES[clampedPhase];
  const PhaseIcon = phase.Icon;
  const progress = Math.min(
    92,
    Math.max(12, Math.round(((clampedPhase + 1) / PHASES.length) * 72) + dispatchedCount * 3),
  );

  if (variant === "minimal") {
    return createPortal(
      <motion.div
        className="fixed inset-0 z-[10000] flex items-end justify-center pb-16 px-6"
        style={{ background: "rgba(5,7,13,0.85)", backdropFilter: "blur(24px)", WebkitBackdropFilter: "blur(24px)" }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0, transition: { duration: exitDuration } }}
        transition={{ duration: 0.2, ease: "easeOut" }}
      >
        <motion.div
          initial={{ opacity: 0, y: 24, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1], delay: 0.05 }}
          className="w-full max-w-md"
        >
          <div className="bg-[#070A12] border border-white/10 rounded-2xl shadow-[0_24px_64px_rgba(0,0,0,0.7)] overflow-hidden">
            <div className="h-[2px] w-full bg-white/5">
              <motion.div
                className="h-full bg-primary rounded-full"
                animate={{ width: `${progress}%` }}
                transition={{ duration: 0.6, ease: "easeOut" }}
              />
            </div>
            <div className="flex items-center gap-5 px-6 py-5">
              <div className="shrink-0 w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center relative">
                <AnimatePresence mode="wait">
                  <motion.div
                    key={clampedPhase}
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
              <div className="flex-1 min-w-0">
                <AnimatePresence mode="wait">
                  <motion.p
                    key={`label-${clampedPhase}`}
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
              <div className="shrink-0 flex flex-col gap-1.5 items-center">
                {PHASES.map((_, i) => (
                  <motion.div
                    key={i}
                    className={`rounded-full ${i <= clampedPhase ? "bg-primary" : "bg-white/15"}`}
                    animate={{
                      width: i === clampedPhase ? 16 : 4,
                      height: 4,
                      opacity: i < clampedPhase ? 0.8 : i === clampedPhase ? 1 : 0.15,
                    }}
                    transition={{ type: "spring", damping: 22, stiffness: 280 }}
                  />
                ))}
              </div>
            </div>
          </div>
        </motion.div>
      </motion.div>,
      document.body
    );
  }

  // ── Full variant — horizontal swapping phase cards ─────────────────────────
  return createPortal(
    <motion.div
      className="fixed inset-0 z-[10000] flex flex-col items-center justify-center px-6 select-none"
      style={{
        background: "rgba(2, 6, 23, 0.97)",
        backdropFilter: "blur(32px)",
        WebkitBackdropFilter: "blur(32px)",
      }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: exitDuration, ease: "easeIn" } }}
      transition={{ duration: 0.14, ease: "easeOut" }}
    >
      {/* Ambient glow */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <motion.div
          className="absolute top-[42%] left-1/2 -translate-x-1/2 -translate-y-1/2 w-[640px] h-[280px] rounded-full blur-[90px]"
          style={{ background: "radial-gradient(ellipse, rgba(59,130,246,0.07) 0%, transparent 70%)" }}
          animate={{ opacity: [0.6, 1, 0.6] }}
          transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
        />
      </div>

      <div className="relative z-10 flex flex-col items-center w-full max-w-[360px]">

        {/* Live indicator header */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.07, duration: 0.28, ease: "easeOut" }}
          className="flex items-center gap-2.5 mb-10"
        >
          <motion.div
            className="w-1.5 h-1.5 rounded-full bg-primary"
            animate={{ scale: [1, 1.5, 1], opacity: [1, 0.35, 1] }}
            transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut" }}
          />
          <span className="text-[10px] font-mono font-bold tracking-[0.28em] uppercase text-white/25">
            Forensic Protocol Active
          </span>
          <motion.div
            className="w-1.5 h-1.5 rounded-full bg-primary"
            animate={{ scale: [1, 1.5, 1], opacity: [0.35, 1, 0.35] }}
            transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut", delay: 0.7 }}
          />
        </motion.div>

        {/* ── Phase card — slides in/out horizontally on phase change ── */}
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
                  background: "#060914",
                  border: "1px solid rgba(255,255,255,0.06)",
                  boxShadow: "0 24px 64px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.025)",
                }}
              >
                {/* Top progress strip */}
                <div className="h-[1.5px] w-full" style={{ background: "rgba(255,255,255,0.04)" }}>
                  <motion.div
                    className="h-full bg-primary rounded-full"
                    style={{ opacity: 0.75 }}
                    animate={{ width: `${progress}%` }}
                    transition={{ duration: 0.85, ease: [0.4, 0, 0.2, 1] }}
                  />
                </div>

                <div className="px-5 py-5 flex items-center gap-4">
                  {/* Phase icon */}
                  <div
                    className="relative shrink-0 w-11 h-11 rounded-xl flex items-center justify-center"
                    style={{
                      background: "rgba(59,130,246,0.07)",
                      border: "1px solid rgba(59,130,246,0.16)",
                    }}
                  >
                    <PhaseIcon className="w-[18px] h-[18px] text-primary relative z-10" />
                    {/* Pulse ring */}
                    <motion.div
                      className="absolute inset-0 rounded-xl"
                      style={{ border: "1px solid rgba(59,130,246,0.35)" }}
                      animate={{ opacity: [0.25, 0.7, 0.25], scale: [1, 1.06, 1] }}
                      transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
                    />
                  </div>

                  {/* Text block */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-[3px]">
                      <span
                        className="text-[13px] font-bold tracking-tight leading-none truncate"
                        style={{ color: "rgba(255,255,255,0.92)" }}
                      >
                        {phase.label}
                      </span>
                      {/* Live dot */}
                      <motion.div
                        className="w-[5px] h-[5px] rounded-full bg-primary shrink-0"
                        animate={{ opacity: [1, 0.12, 1] }}
                        transition={{ duration: 0.95, repeat: Infinity, ease: "easeInOut" }}
                      />
                    </div>
                    <AnimatePresence mode="wait">
                      <motion.p
                        key={sanitizedText || phase.detail}
                        initial={{ opacity: 0, y: 3 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -3 }}
                        transition={{ duration: 0.18, ease: "easeOut" }}
                        className="text-[11px] font-mono leading-relaxed truncate"
                        style={{ color: "rgba(255,255,255,0.30)" }}
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
                      borderColor: "rgba(59,130,246,0.14)",
                      borderTopColor: "rgba(59,130,246,0.72)",
                    }}
                    animate={{ rotate: 360 }}
                    transition={{ duration: 1.6, repeat: Infinity, ease: "linear" }}
                  />
                </div>
              </div>
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Phase step dots */}
        <div className="flex items-center gap-[7px]">
          {PHASES.map((p, i) => (
            <motion.div
              key={p.id}
              className={`rounded-full ${i <= clampedPhase ? "bg-primary" : "bg-white/[0.12]"}`}
              animate={{
                width: i === clampedPhase ? 22 : i < clampedPhase ? 7 : 5,
                height: 3,
                opacity: i < clampedPhase ? 0.6 : i === clampedPhase ? 1 : 0.22,
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

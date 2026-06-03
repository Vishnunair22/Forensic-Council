"use client";

// ROLE: Result/evidence-page arbiter overlay. Visually mirrors LoadingOverlay
// (same frosted surface, primary theme, progress treatment) but keeps
// arbiter-specific copy. Driven by isVisible + liveText; owns its own
// AnimatePresence keyed on isVisible.

import React from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ARBITER_PHASES } from "@/lib/arbiterPhases";

interface ArbiterDeliberationOverlayProps {
  isVisible: boolean;
  liveText?: string;
}

// Generic placeholders that are NOT real backend step messages. While the
// incoming text is one of these (or empty) we cycle the canned phases so the
// overlay reads as "working"; the moment a real step message streams in we
// pin it verbatim and stop cycling.
const GENERIC_PLACEHOLDERS = new Set([
  "council deliberating on evidence",
  "council deliberating",
  "decrypting forensic ledger",
  "initializing investigation",
  "compiling agent findings into the final report",
]);

function isMeaningful(text: string): boolean {
  if (!text || text.length <= 5) return false;
  return !GENERIC_PLACEHOLDERS.has(text.toLowerCase().replace(/[.\s]+$/, "").trim());
}

export function ArbiterDeliberationOverlay({
  isVisible,
  liveText,
}: ArbiterDeliberationOverlayProps) {
  const prefersReducedMotion = useReducedMotion();

  // Only trim trailing ellipses/whitespace — never rewrite the backend's words.
  const cleanLiveText = React.useMemo(() => {
    if (!liveText) return "";
    return liveText.replace(/[.…]+$/g, "").replace(/\s+/g, " ").trim();
  }, [liveText]);

  // The arbiter emits real step messages sparsely (often a single one for the
  // whole deliberation), so we never want the text to freeze. Strategy:
  //  - an independent ticker cycles the canned phases continuously, and
  //  - a real backend message takes priority and "holds" for a short window
  //    when it arrives, after which cycling resumes.
  // The ticker is deps-free so frequent poll updates can never reset it.
  const [dynamicText, setDynamicText] = React.useState(
    isMeaningful(cleanLiveText) ? cleanLiveText : ARBITER_PHASES[0].replace(/\.+$/, ""),
  );
  const phaseIndexRef = React.useRef(0);
  const lastRealRef = React.useRef<{ text: string; at: number }>({ text: "", at: 0 });
  const REAL_MESSAGE_HOLD_MS = 7000;

  React.useEffect(() => {
    if (isMeaningful(cleanLiveText)) {
      lastRealRef.current = { text: cleanLiveText, at: Date.now() };
      setDynamicText(cleanLiveText);
    }
  }, [cleanLiveText]);

  React.useEffect(() => {
    const id = setInterval(() => {
      // Keep a freshly-arrived real message on screen briefly before cycling.
      if (Date.now() - lastRealRef.current.at < REAL_MESSAGE_HOLD_MS) return;
      phaseIndexRef.current = (phaseIndexRef.current + 1) % ARBITER_PHASES.length;
      setDynamicText(ARBITER_PHASES[phaseIndexRef.current].replace(/\.+$/, ""));
    }, 3500);
    return () => clearInterval(id);
  }, []);

  const [elapsed, setElapsed] = React.useState(0);
  React.useEffect(() => {
    if (!isVisible) { setElapsed(0); return; }
    const id = setInterval(() => setElapsed((p) => p + 1), 1000);
    return () => clearInterval(id);
  }, [isVisible]);

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    return `${m}:${(s % 60).toString().padStart(2, "0")}`;
  };

  return (
    <AnimatePresence initial={false}>
      {isVisible && (
        <motion.div
          key="arbiter-overlay"
          aria-busy="true"
          aria-label="Consensus synthesis in progress, please wait"
          className="fixed inset-0 z-[10000] flex flex-col items-center justify-center px-6 select-none bg-background/96 overflow-hidden"
          initial={prefersReducedMotion ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={prefersReducedMotion ? {} : { opacity: 0, transition: { duration: 0.16, ease: "easeIn" } }}
          transition={{ duration: 0.16, ease: "easeOut" }}
        >
          {/* Background grids and flares for depth (mirrors LoadingOverlay) */}
          <div className="absolute inset-0 bg-dot-grid opacity-[0.035] pointer-events-none" />
          <div
            className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] rounded-full opacity-[0.06] pointer-events-none"
            style={{
              background: "radial-gradient(circle, var(--color-primary) 0%, transparent 70%)",
              filter: "blur(80px)",
            }}
          />

          {/* Main frosted glass dialog surface */}
          <div className="relative z-10 w-full max-w-lg mx-auto fc-surface-overlay p-8 sm:p-10 md:p-12">
            {/* Subtle scan line sweep */}
            <div
              className="absolute inset-x-0 h-[1px] bg-gradient-to-r from-transparent via-primary/30 to-transparent pointer-events-none"
              style={{ top: 0, animation: "fc-marker-blink 2.5s ease-in-out infinite" }}
            />

            {/* Status indicator */}
            <div className="flex items-center gap-4 mb-8">
              <div className="relative w-9 h-9 flex items-center justify-center border border-primary/30 rounded-xl bg-primary/5">
                <motion.div
                  animate={prefersReducedMotion ? {} : { scale: [1, 1.3, 1], opacity: [0.5, 0, 0.5] }}
                  transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                  className="absolute inset-0 rounded-xl border border-primary/40"
                />
                <div className="w-2.5 h-2.5 rounded-full bg-primary animate-pulse" />
              </div>
              <span className="fc-eyebrow fc-text-muted">
                Council Arbiter
              </span>
            </div>

            {/* Title and live text */}
            <div className="mb-10 space-y-4">
              <motion.h1
                initial={prefersReducedMotion ? false : { opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.16, ease: "easeOut" }}
                className="text-3xl lg:text-4xl font-heading font-black fc-text-primary text-hero-gradient tracking-tight leading-tight"
              >
                Consensus Synthesis
              </motion.h1>
              <div className="flex items-center gap-3">
                <motion.div
                  className="w-1.5 h-1.5 bg-white/55 rounded-full flex-shrink-0"
                  animate={prefersReducedMotion ? {} : { opacity: [0.65, 1, 0.65] }}
                  transition={prefersReducedMotion ? {} : { duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
                />
                <motion.p
                  key={dynamicText}
                  className="text-xs md:text-sm font-mono fc-text-muted truncate pr-2"
                  role="status"
                  aria-live="polite"
                  aria-atomic="true"
                  initial={prefersReducedMotion ? false : { opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.2 }}
                >
                  {dynamicText}
                </motion.p>
              </div>
            </div>

            {/* Progress bar */}
            <div className="w-full" aria-hidden="true">
              <div className="flex items-center justify-between mb-3.5 fc-eyebrow fc-text-muted">
                <span>Synthesizing Verdict</span>
                <span className="tabular-nums">T+{formatTime(elapsed)}</span>
              </div>
              <div className="h-2 w-full bg-white/10 rounded-full relative overflow-hidden">
                <motion.div
                  className="absolute inset-y-0 left-0 bg-gradient-to-r from-primary/60 to-primary rounded-full flex items-center justify-end"
                  initial={{ width: "0%" }}
                  animate={prefersReducedMotion ? {} : { width: ["0%", "18%", "18%", "45%", "45%", "82%", "82%", "100%", "100%"] }}
                  transition={prefersReducedMotion ? {} : { duration: 3.5, times: [0, 0.15, 0.25, 0.4, 0.55, 0.75, 0.85, 0.95, 1], repeat: Infinity, ease: "linear" }}
                >
                  {/* Leader glow point */}
                  <div className="h-full w-2 bg-white/60 blur-[1px]" />
                </motion.div>
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

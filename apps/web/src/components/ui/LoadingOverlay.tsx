"use client";

import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { motion, useReducedMotion } from "framer-motion";
import type { SoundType } from "@/hooks/useSound";

export interface LoadingOverlayProps {
  liveText?: string;
  dispatchedCount?: number;
  playSound?: (sound: SoundType) => void;
  exitDuration?: number;
}

function sanitize(text: string): string {
  return text
    .replace(/^(PIPELINE|UPLOAD|AUTH|SYSTEM|CORE|AGENT):/i, "")
    .replace(/\.\.\.$/, "")
    .trim();
}

function toDisplayText(raw: string, dispatched: number): string {
  const t = sanitize(raw);
  if (t) return t;
  if (dispatched > 0) return "Agents dispatching";
  return "Initializing workspace";
}

export function LoadingOverlay({
  liveText,
  dispatchedCount = 0,
  playSound,
  exitDuration = 0.16,
}: LoadingOverlayProps) {
  const prefersReducedMotion = useReducedMotion();
  const raw = toDisplayText(liveText || "", dispatchedCount);

  // Debounce so rapid-fire backend messages don't strobe the card
  const [displayText, setDisplayText] = useState(raw);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setDisplayText(raw), 80);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [raw]);

  // Sound on text change (skip initial mount)
  const prevTextRef = useRef(displayText);
  useEffect(() => {
    if (displayText !== prevTextRef.current) {
      playSound?.("scan");
      prevTextRef.current = displayText;
    }
  }, [displayText, playSound]);

  // F-M-6: SSR guard so a stray server import can't crash on document access.
  if (typeof document === "undefined") return null;

  return createPortal(
    <motion.div
      aria-busy="true"
      aria-label="Analysis in progress, please wait"
      className="fixed inset-0 z-[10000] flex flex-col items-center justify-center px-6 select-none bg-background/96 backdrop-blur-3xl overflow-hidden"
      initial={prefersReducedMotion ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={
        prefersReducedMotion
          ? {}
          : { opacity: 0, transition: { duration: exitDuration, ease: "easeIn" } }
      }
      transition={{ duration: 0.16, ease: "easeOut" }}
    >
      {/* Background Grids and Flares for depth */}
      <div className="absolute inset-0 bg-dot-grid opacity-[0.035] pointer-events-none" />
      <div
        className="absolute w-[500px] h-[500px] rounded-full opacity-[0.06] pointer-events-none"
        style={{
          background: "radial-gradient(circle, var(--color-primary) 0%, transparent 70%)",
          filter: "blur(80px)",
        }}
      />

      {/* Main Frosted Glass Dialog Surface */}
      <div className="relative z-10 w-full max-w-lg mx-auto fc-surface-overlay p-8 sm:p-10 md:p-12">
        {/* Subtle scan line sweep effect */}
        <div 
          className="absolute inset-x-0 h-[1px] bg-gradient-to-r from-transparent via-primary/30 to-transparent pointer-events-none"
          style={{
            top: 0,
            animation: "fc-marker-blink 2.5s ease-in-out infinite",
          }}
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
            System Initialization
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
            Forensic Analysis
          </motion.h1>
          <div className="flex items-center gap-3">
            <motion.div
              className="w-1.5 h-1.5 bg-white/55 rounded-full flex-shrink-0"
              animate={prefersReducedMotion ? {} : { opacity: [0.65, 1, 0.65] }}
              transition={prefersReducedMotion ? {} : { duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
            />
            <p
              className="text-xs md:text-sm font-mono fc-text-muted truncate pr-2"
              role="status"
              aria-live="polite"
              aria-atomic="true"
            >
              {displayText}
            </p>
          </div>
        </div>

        {/* Progress bar */}
        <div className="w-full" aria-hidden="true">
          <div className="flex items-center justify-between mb-3.5 fc-eyebrow fc-text-muted">
            <span>Workspace Setup</span>
          </div>
          <div className="h-2 w-full bg-white/10 rounded-full relative overflow-hidden">
            <motion.div
              className="absolute inset-y-0 left-0 bg-gradient-to-r from-primary/60 to-primary rounded-full flex items-center justify-end"
              initial={{ width: "0%" }}
              animate={prefersReducedMotion ? {} : { width: ["0%", "18%", "18%", "45%", "45%", "82%", "82%", "100%", "100%"] }}
              transition={prefersReducedMotion ? {} : { duration: 3.5, times: [0, 0.15, 0.25, 0.4, 0.55, 0.75, 0.85, 0.95, 1], repeat: Infinity, ease: "linear" }}
            >
              {/* Leader Glow Point */}
              <div className="h-full w-2 bg-white/60 blur-[1px]" />
            </motion.div>
          </div>
        </div>
      </div>
    </motion.div>,
    document.body,
  );
}

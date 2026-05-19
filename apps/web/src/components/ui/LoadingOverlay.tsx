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
  exitDuration = 0.35,
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
      className="fixed inset-0 z-[10000] flex flex-col items-center justify-center px-6 select-none bg-[#02040A]"
      initial={prefersReducedMotion ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={
        prefersReducedMotion
          ? {}
          : { opacity: 0, transition: { duration: exitDuration, ease: "easeIn" } }
      }
      transition={{ duration: 0.14, ease: "easeOut" }}
    >
      <div className="relative z-10 w-full max-w-xl mx-auto border-l-2 border-[var(--color-primary)]/40 pl-8 md:pl-12 py-4">
        {/* Status indicator */}
        <div className="flex items-center gap-4 mb-10">
          <div className="relative w-8 h-8 flex items-center justify-center border border-[var(--color-primary)]/30 rounded-sm bg-[var(--color-primary)]/5">
            <motion.div
              animate={{ opacity: [1, 0.3, 1] }}
              transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
              className="w-3 h-3 bg-[var(--color-primary)]"
            />
          </div>
          <span className="fc-eyebrow fc-text-faint">
            System Initialization
          </span>
        </div>

        {/* Title and live text */}
        <div className="mb-12 space-y-5">
          <motion.h1
            key={displayText}
            initial={{ x: -10, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            transition={{ duration: 0.2 }}
            className="text-3xl md:text-4xl font-heading font-black text-white tracking-tight"
            role="status"
            aria-live="polite"
            aria-atomic="true"
          >
            {displayText}
          </motion.h1>
          <div className="flex items-center gap-4">
            <motion.div
              className="w-1.5 h-1.5 bg-white/55 rounded-full"
              animate={prefersReducedMotion ? {} : { opacity: [0.65, 1, 0.65] }}
              transition={prefersReducedMotion ? {} : { duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
            />
            <p className="text-xs md:text-sm font-mono font-medium text-white/60 tracking-wide">
              Establishing secure forensic perimeter...
            </p>
          </div>
        </div>

        {/* Progress bar */}
        <div className="w-full max-w-md">
          <div className="flex items-center justify-between mb-4 fc-eyebrow fc-text-faint">
            <span>Workspace Setup</span>
          </div>
          <div className="h-px w-full bg-white/10 relative overflow-hidden">
            <motion.div
              className="absolute inset-y-0 left-0 bg-[var(--color-primary)] shadow-[0_0_15px_var(--color-primary)]"
              initial={{ width: "0%" }}
              animate={prefersReducedMotion ? {} : { width: ["0%", "18%", "18%", "45%", "45%", "82%", "82%", "100%", "100%"] }}
              transition={prefersReducedMotion ? {} : { duration: 3.5, times: [0, 0.15, 0.25, 0.4, 0.55, 0.75, 0.85, 0.95, 1], repeat: Infinity, ease: "linear" }}
            />
          </div>
        </div>
      </div>
    </motion.div>,
    document.body,
  );
}

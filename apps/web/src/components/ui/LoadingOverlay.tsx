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
      className="fixed inset-0 z-[10000] flex items-center justify-center px-5 select-none bg-black"
      initial={prefersReducedMotion ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={
        prefersReducedMotion
          ? {}
          : { opacity: 0, transition: { duration: exitDuration, ease: "easeIn" } }
      }
      transition={{ duration: 0.14, ease: "easeOut" }}
    >
      <div
        className="text-center"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        <p className="text-4xl md:text-5xl font-bold text-white tracking-tight">
          {displayText}
        </p>
      </div>
    </motion.div>,
    document.body,
  );
}


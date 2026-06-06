"use client";

// ROLE: In-page overlay prop-driven by useInvestigation.
// Receives liveText and dispatchedCount to display analysis progress.

import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { motion, useReducedMotion } from "framer-motion";
import { sessionOnlyStorage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";
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

/** Derive a human-readable label from MIME type for the eyebrow. */
function mimeToLabel(mime: string): string {
  if (mime.startsWith("image/")) return "Image Evidence";
  if (mime.startsWith("audio/")) return "Audio Evidence";
  if (mime.startsWith("video/")) return "Video Evidence";
  if (mime === "application/pdf") return "Document Evidence";
  return "Evidence";
}

export function LoadingOverlay({
  liveText,
  dispatchedCount = 0,
  playSound,
  exitDuration = 0.22,
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

  // Read pending file meta from sessionStorage so we can show the filename
  // and file type on the overlay — gives the user confidence their file was received.
  const [fileMeta, setFileMeta] = useState<{ name: string; type: string } | null>(null);
  useEffect(() => {
    const raw = sessionOnlyStorage.getItem(STORAGE_KEYS.FC_PENDING_FILE_META, true, null);
    if (raw && typeof raw === "object") {
      const meta = raw as { name?: string; type?: string };
      if (typeof meta.name === "string" && typeof meta.type === "string") {
        setFileMeta({ name: meta.name, type: meta.type });
      }
    }
  }, []);

  const eyebrowLabel = fileMeta ? mimeToLabel(fileMeta.type) : "Analysis";
  const fileName = fileMeta?.name ?? null;

  // Play `scan` sound on meaningful status changes — throttled to once per 5s
  // to avoid firing on every rapid-fire backend message.
  const prevTextRef = useRef(displayText);
  const soundThrottleRef = useRef<number>(0);
  useEffect(() => {
    if (displayText !== prevTextRef.current) {
      const now = Date.now();
      if (now - soundThrottleRef.current > 5000) {
        playSound?.("scan");
        soundThrottleRef.current = now;
      }
      prevTextRef.current = displayText;
    }
  }, [displayText, playSound]);

  // F-M-6: SSR guard so a stray server import can't crash on document access.
  if (typeof document === "undefined") return null;

  return createPortal(
    <motion.div
      aria-busy="true"
      aria-label="Analysis in progress, please wait"
      className="fixed inset-0 z-[10000] flex flex-col items-center justify-center px-6 select-none bg-background/96 overflow-hidden"
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
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] rounded-full opacity-[0.06] pointer-events-none"
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
          <span className="fc-eyebrow fc-text-muted">{eyebrowLabel}</span>
        </div>

        {/* Title + filename */}
        <div className="mb-10 space-y-3">
          <motion.h1
            initial={prefersReducedMotion ? false : { opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="text-3xl lg:text-4xl font-heading font-extrabold fc-text-primary text-hero-gradient tracking-tight leading-tight"
          >
            Forensic Analysis
          </motion.h1>

          {/* Filename — gives the user confidence their file was received */}
          {fileName && (
            <p className="text-xs font-mono fc-text-muted truncate max-w-full" title={fileName}>
              {fileName}
            </p>
          )}

          {/* Live status text */}
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

        {/* Indeterminate progress — honest signal that work is in progress,
            not a fake percentage completion bar that loops through 100%. */}
        <div className="w-full" aria-hidden="true">
          <div className="flex items-center justify-between mb-3.5 fc-eyebrow fc-text-muted">
            <span>Workspace Setup</span>
          </div>
          <div className="h-1.5 w-full bg-white/8 rounded-full relative overflow-hidden">
            {prefersReducedMotion ? (
              /* Static bar for reduced-motion users */
              <div className="absolute inset-y-0 left-0 w-1/2 bg-primary/40 rounded-full" />
            ) : (
              /* Bouncing indeterminate bar — honest "we're working on it" signal */
              <motion.div
                className="absolute inset-y-0 bg-gradient-to-r from-primary/50 via-primary to-primary/50 rounded-full"
                style={{ width: "40%" }}
                animate={{ x: ["0%", "150%", "0%"] }}
                transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut" }}
              />
            )}
          </div>
        </div>
      </div>
    </motion.div>,
    document.body,
  );
}

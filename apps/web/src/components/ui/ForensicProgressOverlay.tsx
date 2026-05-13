"use client";

import { useState, useEffect } from "react";
import { motion, useReducedMotion } from "framer-motion";

interface ForensicProgressOverlayProps {
  title: string;
  liveText: string;
  telemetryLabel: string;
  showElapsed: boolean;
}

export function ForensicProgressOverlay({
  title,
  liveText,
  telemetryLabel,
  showElapsed,
}: ForensicProgressOverlayProps) {
  const [elapsed, setElapsed] = useState(0);
  const prefersReducedMotion = useReducedMotion();

  useEffect(() => {
    const interval = setInterval(() => setElapsed((prev) => prev + 1), 1000);
    return () => clearInterval(interval);
  }, []);

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  return (
    <motion.div
      aria-busy="true"
      className="fixed inset-0 z-[10000] flex flex-col items-center justify-center px-6 selection:bg-transparent bg-background/90 backdrop-blur-[32px]"

      initial={prefersReducedMotion ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={prefersReducedMotion ? {} : { opacity: 0, transition: { duration: 0.4, ease: "easeOut" } }}
      transition={{ duration: 0.14, ease: "easeOut" }}
    >
      <div className="relative z-10 flex flex-col items-center w-full max-w-sm">
        {/* Status pill */}
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center gap-2.5 mb-8"
        >
          <motion.div
            className="w-1.5 h-1.5 rounded-full"
            style={{ background: "var(--color-primary)" }}
            animate={prefersReducedMotion ? {} : { scale: [1, 1.5, 1], opacity: [1, 0.4, 1] }}
            transition={prefersReducedMotion ? {} : { duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
          />
          <span className="text-[10px] font-mono font-bold tracking-[0.26em] uppercase text-muted-secondary">
            Forensic Analysis
          </span>
        </motion.div>

        {/* Title and live text */}
        <div className="text-center mb-10">
          {/* Spinner */}
          <div className="relative w-12 h-12 mx-auto mb-6">
            <motion.div
              className="absolute inset-0 rounded-full"
              style={{
                border: "1.5px solid rgba(79,142,247,0.12)",
                borderTopColor: "rgba(79,142,247,0.75)",
              }}
              animate={prefersReducedMotion ? {} : { rotate: 360 }}
              transition={prefersReducedMotion ? {} : { duration: 1.4, repeat: Infinity, ease: "linear" }}
            />
            <div
              className="absolute inset-1.5 rounded-full"
              style={{ background: "rgba(79,142,247,0.06)" }}
            />
          </div>

          <motion.h1
            initial={{ y: 10, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.06 }}
            className="text-[22px] font-heading font-bold text-white/90 mb-3"
            style={{ letterSpacing: "-0.02em" }}
          >
            {title}
          </motion.h1>
          <p
            id="forensic-live-text"
            className="text-[12px] font-mono font-semibold tracking-wide text-center px-4"
            style={{ color: "rgba(79,142,247,0.65)" }}
            role="status"
            aria-live="polite"
            aria-atomic="true"
          >
            {liveText}
          </p>
        </div>

        {/* Progress bar */}
        <div className="w-full">
          <div className="flex items-center justify-between mb-2.5 text-[9px] font-mono uppercase tracking-[0.2em]" style={{ color: "rgba(255,255,255,0.22)" }}>
            <span>{telemetryLabel}</span>
            {showElapsed && (
              <span aria-hidden="true" style={{ color: "var(--color-primary)" }}>{formatTime(elapsed)}</span>
            )}
          </div>
          <div className="h-[3px] rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.06)" }}>
            <motion.div
              className="h-full rounded-full"
              style={{ background: "linear-gradient(90deg, rgba(79,142,247,0.8), rgba(165,200,255,0.95))" }}
              initial={{ width: 0 }}
              animate={prefersReducedMotion ? {} : { width: "100%" }}
              transition={prefersReducedMotion ? {} : { duration: 2.2, repeat: Infinity, ease: "easeInOut" }}
            />
          </div>
        </div>
      </div>
    </motion.div>
  );
}
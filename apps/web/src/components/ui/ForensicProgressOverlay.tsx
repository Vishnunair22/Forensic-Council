"use client";

import { useState, useEffect } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Loader2 } from "lucide-react";

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
    const interval = setInterval(() => {
      setElapsed((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  return (
    <motion.div
      className="fixed inset-0 z-[10000] flex flex-col items-center justify-center px-6 selection:bg-transparent"
      style={{
        background: "rgba(0, 0, 0, 0.85)",
        backdropFilter: "blur(24px)",
        WebkitBackdropFilter: "blur(24px)",
      }}
      initial={prefersReducedMotion ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={prefersReducedMotion ? {} : { opacity: 0, transition: { duration: 0.4, ease: "easeOut" } }}
      transition={{ duration: 0.12, ease: "easeOut" }}
    >
      <div className="relative z-10 flex flex-col items-center w-full max-w-md">
        <motion.div
          initial={{ y: 10, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          className="flex items-center gap-2.5 mb-6"
        >
          <div className="w-1.5 h-1.5 rounded-full bg-primary" />
          <span className="text-xs font-semibold tracking-wide text-white/50">
            Forensic Analysis
          </span>
        </motion.div>

        <div className="text-center mb-8">
          <Loader2 className="w-10 h-10 text-primary animate-spin mb-5 mx-auto" />
          <motion.h1
            initial={{ y: 12, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.05 }}
            className="text-2xl font-black tracking-tight text-white mb-3"
          >
            {title}
          </motion.h1>
          <p
            className="text-sm font-mono font-semibold tracking-wide text-primary/70 text-center px-4"
            role="status"
            aria-live="polite"
          >
            {liveText}
          </p>
        </div>

        <div className="w-full">
          <div className="flex items-center justify-between mb-3 text-[10px] font-mono text-white/30 uppercase tracking-widest">
            <span>{telemetryLabel}</span>
            {showElapsed && (
              <span className="text-primary">{formatTime(elapsed)}</span>
            )}
          </div>
          <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
            <motion.div
              className="h-full bg-primary rounded-full"
              initial={{ width: 0 }}
              animate={{ width: "100%" }}
              transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
            />
          </div>
        </div>
      </div>
    </motion.div>
  );
}
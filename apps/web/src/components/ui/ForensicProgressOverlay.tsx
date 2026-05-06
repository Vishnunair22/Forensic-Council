"use client";

import { useEffect, useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";

function categorize(text: string) {
  if (!text) return "system";
  const lower = text.toLowerCase();
  if (lower.includes("complete") || lower.includes("done") || lower.includes("success")) return "success";
  if (lower.includes("error") || lower.includes("fail") || lower.includes("halt")) return "error";
  if (lower.includes("scan") || lower.includes("analyz") || lower.includes("process")) return "info";
  return "system";
}

function fmtDiagnosticTime(): string {
  const d = new Date();
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`;
}

export interface ForensicProgressOverlayProps {
  title: string;
  liveText: string;
  telemetryLabel?: string;
  showElapsed?: boolean;
}

export function ForensicProgressOverlay({
  title,
  liveText,
  telemetryLabel = "Secured Transmission",
  showElapsed = true,
}: ForensicProgressOverlayProps) {
  const [elapsed, setElapsed] = useState(0);
  const [log, setLog] = useState<{ id: number; text: string; cat: string }[]>([]);
  const idRef = useRef(0);
  const lastTextRef = useRef("");

  useEffect(() => {
    if (!showElapsed) return;
    const id = setInterval(() => setElapsed((e) => e + 1), 1000);

    // Lock scroll on mount
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      clearInterval(id);
      document.body.style.overflow = originalOverflow || "unset";
    };
  }, [showElapsed]);

  useEffect(() => {
    const trimmed = liveText.replace(/[\u{1F300}-\u{1FFFF}]|[\u2600-\u27FF]/gu, "").trim();
    if (!trimmed || trimmed === lastTextRef.current) return;
    lastTextRef.current = trimmed;
    const id = ++idRef.current;
    setLog((prev) => {
      const next = [...prev, { id, text: trimmed, cat: categorize(trimmed) }];
      return next.length > 6 ? next.slice(next.length - 6) : next;
    });
  }, [liveText]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[10000] flex flex-col items-center justify-center bg-slate-950/95 backdrop-blur-3xl px-6"
    >
      {/* --- Horizon Underglow --- */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-primary/5 blur-[150px] rounded-full pointer-events-none" />

      <div className="relative z-10 flex flex-col items-center text-center w-full max-w-5xl">

        {/* --- Top Metadata --- */}
        <motion.div
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          className="flex items-center gap-4 mb-10"
        >
          <div className="w-1 h-1 rounded-full bg-primary animate-pulse shadow-[0_0_10px_#00FFFF]" />
          <span className="text-[10px] font-mono tracking-[0.3em] text-white/30 uppercase">
            {telemetryLabel}
          </span>
        </motion.div>

        {/* --- Horizon Title --- */}
        <motion.h1
          initial={{ y: 30, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          className="text-4xl md:text-6xl font-heading font-bold text-white tracking-tight mb-16"
        >
          {title}
        </motion.h1>

        {/* --- Aperture Node --- */}
        <div className="relative w-32 h-32 mb-20 flex items-center justify-center">
           <motion.div
             animate={{ rotate: 360 }}
             transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
             className="absolute inset-0 rounded-full border-2 border-primary/20 border-dashed"
           />
           <div className="w-4 h-4 bg-primary rounded-full animate-ping opacity-20" />
           <div className="w-2 h-2 bg-primary rounded-full shadow-[0_0_20px_#00FFFF]" />
        </div>

        {/* --- Forensic Log Feed --- */}
        <div className="w-full max-w-2xl min-h-[180px] flex flex-col justify-end gap-3 mb-16">
          <AnimatePresence mode="popLayout">
            {log.map((entry, idx) => {
              const isLatest = idx === log.length - 1;
              const opacity = isLatest ? 1 : 0.3 - (log.length - 1 - idx) * 0.05;

              return (
                <motion.div
                  key={entry.id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity, x: 0 }}
                  exit={{ opacity: 0, x: 10 }}
                  className={`flex items-center gap-4 p-3 rounded-lg border border-white/5 bg-white/[0.01] ${isLatest ? 'border-primary/20 bg-primary/[0.02]' : ''}`}
                >
                  <span className="text-[9px] font-mono text-white/20">[{fmtDiagnosticTime()}]</span>
                  <span className={`text-xs font-mono tracking-tight ${
                    entry.cat === 'success' ? 'text-success' :
                    entry.cat === 'error' ? 'text-danger' :
                    entry.cat === 'info' ? 'text-primary' : 'text-white/60'
                  }`}>
                    {entry.text}
                  </span>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>

        {/* --- Bottom Stats --- */}
        <div className="flex items-center gap-12 text-[10px] font-mono tracking-[0.2em] text-white/20">
          <div>ELAPSED: {elapsed}S</div>
          <div className="w-[1px] h-3 bg-white/10" />
          <div>NODE: COUNCIL_HQ</div>
          <div className="w-[1px] h-3 bg-white/10" />
          <div className="text-primary/40">SECURE_LINK_ACTIVE</div>
        </div>

      </div>
    </motion.div>
  );
}

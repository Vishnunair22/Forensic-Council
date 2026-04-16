"use client";

import { useEffect, useState, useRef, Fragment } from "react";
import { motion, AnimatePresence } from "framer-motion";

export type ForensicProgressVariant = "stream" | "council";

export interface ForensicProgressOverlayProps {
  variant: ForensicProgressVariant;
  title: string;
  liveText: string;
  telemetryLabel?: string;
  showElapsed?: boolean;
}

const variantAccent = {
  stream: { primary: "#22d3ee", gradient: "from-cyan-400 to-blue-500", glow: "rgba(34,211,238,0.15)" },
  council: { primary: "#f59e0b", gradient: "from-amber-400 to-orange-500", glow: "rgba(245,158,11,0.15)" },
};

function categorize(text: string) {
  if (!text) return "system";
  if (text.toLowerCase().includes("complete") || text.toLowerCase().includes("done")) return "success";
  if (text.toLowerCase().includes("error") || text.toLowerCase().includes("fail")) return "error";
  return "info";
}

export function ForensicProgressOverlay({
  variant,
  title,
  liveText,
  telemetryLabel = "Secured Transmission",
  showElapsed = true,
}: ForensicProgressOverlayProps) {
  const accent = variantAccent[variant];

  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!showElapsed) return;
    const id = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(id);
  }, [showElapsed]);

  const [log, setLog] = useState<{ id: number; text: string; cat: string }[]>([]);
  const idRef = useRef(0);
  const lastTextRef = useRef("");

  useEffect(() => {
    const trimmed = liveText.replace(/[\u{1F300}-\u{1FFFF}]|[\u2600-\u27FF]/gu, "").trim();
    if (!trimmed || trimmed === lastTextRef.current) return;
    lastTextRef.current = trimmed;
    const id = ++idRef.current;
    setLog((prev) => {
      const next = [...prev, { id, text: trimmed, cat: categorize(trimmed) }];
      return next.length > 5 ? next.slice(next.length - 5) : next;
    });
  }, [liveText]);

  return (
    <motion.div
      className="fixed inset-0 z-[300] flex flex-col items-center justify-center px-6 selection:bg-transparent"
      style={{
        background: "radial-gradient(circle at 50% 50%, rgba(10,14,23,0.92) 0%, rgba(2,4,10,0.99) 100%)",
        backdropFilter: "blur(40px)",
        WebkitBackdropFilter: "blur(40px)",
      }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: 0.4, ease: "easeInOut" } }}
      transition={{ duration: 0.12, ease: "easeOut" }}
    >
      {/* ── Ambient Underglow ──────────────────────────────────────────── */}
      <motion.div
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[60vw] h-[60vw] rounded-full pointer-events-none opacity-40 blur-[120px]"
        style={{ background: `radial-gradient(circle, ${accent.glow} 0%, transparent 60%)` }}
        animate={{ scale: [0.8, 1.2, 0.8], opacity: [0.2, 0.4, 0.2] }}
        transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }}
      />

      <div className="relative z-10 flex flex-col items-center text-center w-full max-w-4xl">
        
        {/* ── Minimalist Top Identifier ───────────────────────────────── */}
        <motion.div
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.05, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className="flex items-center gap-3 mb-8"
        >
          <motion.div 
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: accent.primary, boxShadow: `0 0 15px ${accent.primary}` }}
            animate={{ opacity: [1, 0.3, 1], scale: [1, 1.2, 1] }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
          />
          <span className="text-[10px] font-black uppercase tracking-[0.4em] text-white/40">
            {telemetryLabel}
          </span>
        </motion.div>

        {/* ── Huge Cinematic Title ────────────────────────────────────── */}
        <motion.h1
          initial={{ y: 30, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.08, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className={`text-4xl sm:text-5xl md:text-6xl font-black uppercase tracking-[0.15em] leading-tight text-transparent bg-clip-text bg-gradient-to-br ${accent.gradient} drop-shadow-2xl`}
        >
          {title}
        </motion.h1>

        {/* ── Sleek Sweeping Loading Line ─────────────────────────────── */}
        <motion.div
          initial={{ scaleX: 0, opacity: 0 }}
          animate={{ scaleX: 1, opacity: 1 }}
          transition={{ delay: 0.15, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          className="w-48 sm:w-80 h-[1px] bg-white/10 mt-10 mb-12 relative overflow-hidden flex-shrink-0"
        >
          <motion.div
            className="absolute top-0 bottom-0 left-0 w-1/3"
            style={{ 
              background: `linear-gradient(90deg, transparent, ${accent.primary}, transparent)`,
              boxShadow: `0 0 10px ${accent.primary}`
            }}
            animate={{ x: ["-100%", "300%"] }}
            transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
          />
        </motion.div>

        {/* ── Centered Fading Telemetry Feed ──────────────────────────── */}
        <div className="h-[140px] flex flex-col justify-end items-center gap-3 w-full">
          <AnimatePresence mode="popLayout">
            {log.length === 0 ? (
              <motion.div
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="text-xs font-mono tracking-widest text-white/20 uppercase"
              >
                Awaiting Neural Sink...
              </motion.div>
            ) : (
              log.map((entry, idx) => {
                const isLatest = idx === log.length - 1;
                const ageRatio = (log.length - 1 - idx) / Math.max(log.length - 1, 1);
                const opacity = isLatest ? 1 : Math.max(0, 0.6 - ageRatio * 0.5);
                const scale = isLatest ? 1 : Math.max(0.85, 0.95 - ageRatio * 0.1);

                return (
                  <motion.div
                    key={entry.id}
                    initial={{ opacity: 0, y: 20, scale: 0.95 }}
                    animate={{ opacity, y: 0, scale }}
                    exit={{ opacity: 0, scale: 0.9, transition: { duration: 0.2 } }}
                    transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                    className="flex flex-col items-center"
                  >
                    <span 
                      className={`text-[11px] sm:text-[13px] font-mono leading-relaxed max-w-xl text-center px-6 ${
                        isLatest ? "text-white/90 drop-shadow-md font-bold" : "text-white/40 font-medium"
                      }`}
                    >
                      {entry.text}
                    </span>
                  </motion.div>
                );
              })
            )}
          </AnimatePresence>
        </div>

        {/* ── Bottom Fixed Elapsed Time ───────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.25, duration: 0.6 }}
          className="absolute bottom-8 left-1/2 -translate-x-1/2"
        >
          {showElapsed && (
             <span className="text-[10px] font-mono font-black uppercase tracking-[0.3em] text-white/30">
               ELAPSED // {elapsed}S
             </span>
          )}
        </motion.div>

      </div>
    </motion.div>
  );
}

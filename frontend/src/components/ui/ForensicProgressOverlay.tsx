"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Activity, Radio } from "lucide-react";

export type ForensicProgressVariant = "stream" | "council";

export interface ForensicProgressOverlayProps {
  variant: ForensicProgressVariant;
  title: string;
  /** Primary line — backend / pipeline status (updated live). */
  liveText: string;
  /** Short label above the live feed, e.g. “Live telemetry”. */
  telemetryLabel?: string;
  /** Show elapsed seconds in the footer strip. */
  showElapsed?: boolean;
}

const variantAccent: Record<
  ForensicProgressVariant,
  { primary: string; glow: string; ring: string; label: string }
> = {
  stream: {
    primary: "#22d3ee",
    glow: "rgba(34,211,238,0.12)",
    ring: "rgba(34,211,238,0.25)",
    label: "text-cyan-400/50",
  },
  council: {
    primary: "#f59e0b",
    glow: "rgba(245,158,11,0.14)",
    ring: "rgba(245,158,11,0.3)",
    label: "text-amber-400/50",
  },
};

/**
 * Full-screen glass overlay for analysis stream connect and council / arbiter phases.
 * Designed to show one authoritative live line from the backend (WS or poll).
 */
export function ForensicProgressOverlay({
  variant,
  title,
  liveText,
  telemetryLabel = "Live status",
  showElapsed = true,
}: ForensicProgressOverlayProps) {
  const accent = variantAccent[variant];
  const [elapsed, setElapsed] = useState(0);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!showElapsed) return;
    const id = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(id);
  }, [showElapsed]);

  useEffect(() => {
    setTick((t) => t + 1);
  }, [liveText]);

  const displayLine =
    liveText.trim() ||
    (variant === "council"
      ? "Council arbiter is synthesising the signed report…"
      : "Initialising secure forensic stream…");

  return (
    <motion.div
      className="fixed inset-0 z-[250] flex items-center justify-center px-4"
      style={{
        background: "radial-gradient(ellipse 120% 80% at 50% -20%, rgba(15,23,42,0.92) 0%, rgba(2,6,12,0.96) 45%, rgba(0,0,0,0.92) 100%)",
        backdropFilter: "blur(24px)",
        WebkitBackdropFilter: "blur(24px)",
      }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.35 }}
    >
      {/* Ambient */}
      <div
        className="absolute inset-0 pointer-events-none overflow-hidden"
        aria-hidden="true"
      >
        <motion.div
          className="absolute -top-32 left-1/2 -translate-x-1/2 w-[min(90vw,720px)] h-[min(90vw,720px)] rounded-full opacity-70"
          style={{ background: `radial-gradient(circle, ${accent.glow} 0%, transparent 65%)` }}
          animate={{ scale: [1, 1.05, 1], opacity: [0.5, 0.75, 0.5] }}
          transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }}
        />
        <motion.div
          className="absolute bottom-0 right-0 w-[400px] h-[400px] rounded-full opacity-40"
          style={{ background: "radial-gradient(circle, rgba(99,102,241,0.08) 0%, transparent 70%)" }}
          animate={{ x: [0, -30, 0], y: [0, -20, 0] }}
          transition={{ duration: 12, repeat: Infinity, ease: "easeInOut" }}
        />
      </div>

      <motion.div
        className="relative w-full max-w-md rounded-3xl overflow-hidden"
        style={{
          boxShadow: `0 0 0 1px ${accent.ring}, 0 25px 80px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.06)`,
        }}
        initial={{ y: 24, scale: 0.96, opacity: 0 }}
        animate={{ y: 0, scale: 1, opacity: 1 }}
        transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      >
        <div
          className="absolute inset-0 rounded-3xl opacity-90"
          style={{
            background:
              "linear-gradient(165deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.02) 40%, rgba(0,0,0,0.2) 100%)",
          }}
        />
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/15 to-transparent" />

        <div className="relative px-8 py-10 flex flex-col items-center text-center gap-6">
          {/* Orb */}
          <div className="relative w-28 h-28 flex items-center justify-center">
            <motion.div
              className="absolute inset-2 rounded-2xl"
              style={{
                border: `1px solid ${accent.ring}`,
                boxShadow: `0 0 40px ${accent.glow}`,
              }}
              animate={{ rotate: 360 }}
              transition={{ duration: 28, repeat: Infinity, ease: "linear" }}
            />
            <motion.div
              className="absolute inset-0 rounded-2xl"
              style={{ border: `2px solid transparent`, borderTopColor: accent.primary }}
              animate={{ rotate: -360 }}
              transition={{ duration: 2.8, repeat: Infinity, ease: "linear" }}
            />
            <div
              className="relative z-10 w-14 h-14 rounded-xl flex items-center justify-center"
              style={{
                background: `linear-gradient(145deg, ${accent.glow}, rgba(0,0,0,0.35))`,
                border: `1px solid ${accent.ring}`,
              }}
            >
              {variant === "council" ? (
                <Radio className="w-7 h-7" style={{ color: accent.primary }} aria-hidden />
              ) : (
                <Activity className="w-7 h-7" style={{ color: accent.primary }} aria-hidden />
              )}
            </div>
          </div>

          <div className="space-y-2">
            <p className={`text-[10px] font-mono font-bold uppercase tracking-[0.35em] ${accent.label}`}>
              {telemetryLabel}
            </p>
            <h2 className="text-xl md:text-2xl font-black text-white tracking-tight font-heading uppercase leading-tight">
              {title}
            </h2>
          </div>

          {/* Live feed */}
          <div
            className="w-full rounded-2xl px-4 py-3.5 text-left min-h-[4.5rem] flex items-center"
            style={{
              background: "rgba(0,0,0,0.35)",
              border: "1px solid rgba(255,255,255,0.06)",
              boxShadow: "inset 0 1px 0 rgba(255,255,255,0.04)",
            }}
          >
            <AnimatePresence mode="wait">
              <motion.p
                key={`${tick}-${displayLine.slice(0, 48)}`}
                className="text-[13px] leading-snug text-white/85 font-medium"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.25 }}
                aria-live="polite"
                aria-atomic="true"
              >
                <span className="font-mono text-[11px] font-bold mr-2 opacity-40" style={{ color: accent.primary }}>
                  {"/"}/
                </span>
                {displayLine}
              </motion.p>
            </AnimatePresence>
          </div>

          {/* Scan line */}
          <div className="w-full h-1 rounded-full overflow-hidden bg-white/[0.06]">
            <motion.div
              className="h-full w-1/3 rounded-full opacity-90"
              style={{
                background: `linear-gradient(90deg, transparent, ${accent.primary}, transparent)`,
                boxShadow: `0 0 12px ${accent.primary}`,
              }}
              animate={{ x: ["-120%", "220%"] }}
              transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
            />
          </div>

          {showElapsed && (
            <p className="text-[10px] font-mono font-bold tracking-widest text-white/25 uppercase">
              Elapsed {elapsed}s
            </p>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}

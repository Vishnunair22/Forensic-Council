"use client";

import { useEffect, useState, useRef, Fragment } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Activity, Radio } from "lucide-react";

export type ForensicProgressVariant = "stream" | "council";

export interface ForensicProgressOverlayProps {
  variant: ForensicProgressVariant;
  title: string;
  /** Primary line — backend / pipeline status (updated live). */
  liveText: string;
  /** Short label above the live feed, e.g. "Live telemetry". */
  telemetryLabel?: string;
  /** Show elapsed seconds in the footer strip. */
  showElapsed?: boolean;
}

// ─── Accent tokens ────────────────────────────────────────────────────────────

const variantAccent: Record<
  ForensicProgressVariant,
  { primary: string; glow: string; ring: string; label: string }
> = {
  stream: {
    primary: "#22d3ee",
    glow: "rgba(34,211,238,0.14)",
    ring: "rgba(34,211,238,0.28)",
    label: "text-cyan-400/50",
  },
  council: {
    primary: "#f59e0b",
    glow: "rgba(245,158,11,0.16)",
    ring: "rgba(245,158,11,0.32)",
    label: "text-amber-400/50",
  },
};

// ─── Stage detection ──────────────────────────────────────────────────────────

type Stage = "uploading" | "connecting" | "analyzing" | "synthesizing";

const STREAM_STAGES: { key: Stage; label: string }[] = [
  { key: "uploading",    label: "Upload"     },
  { key: "connecting",   label: "Connect"    },
  { key: "analyzing",    label: "Analyze"    },
  { key: "synthesizing", label: "Synthesize" },
];

function detectStage(texts: string[], variant: ForensicProgressVariant): Stage {
  if (variant === "council") return "synthesizing";
  const combined = texts.join(" ").toLowerCase();
  if (
    combined.includes("arbiter") ||
    combined.includes("synthes") ||
    combined.includes("deliberat") ||
    combined.includes("council") ||
    combined.includes("signing") ||
    combined.includes("report")
  ) return "synthesizing";
  if (
    combined.includes("agent") ||
    combined.includes("ela") ||
    combined.includes("scan") ||
    combined.includes("running") ||
    combined.includes("queued") ||
    combined.includes("yolo") ||
    combined.includes("forensic") ||
    combined.includes("optical") ||
    combined.includes("audio") ||
    combined.includes("exif") ||
    combined.includes("calling") ||
    combined.includes("classif")
  ) return "analyzing";
  if (
    combined.includes("connect") ||
    combined.includes("stream") ||
    combined.includes("dispatch") ||
    combined.includes("session") ||
    combined.includes("websocket") ||
    combined.includes("agents")
  ) return "connecting";
  return "uploading";
}

// ─── Message categorisation ───────────────────────────────────────────────────

type MsgCategory = "action" | "success" | "info" | "system";

function categorize(text: string): MsgCategory {
  if (!text) return "system";
  if (
    text.toLowerCase().includes("complete") ||
    text.toLowerCase().includes("finished") ||
    text.toLowerCase().includes("done") ||
    text.startsWith("✅") || text.startsWith("✓")
  ) return "success";
  if (
    text.toLowerCase().includes("calling") ||
    text.toLowerCase().includes("running") ||
    text.toLowerCase().includes("scanning") ||
    text.toLowerCase().includes("launching") ||
    text.toLowerCase().includes("loading") ||
    text.toLowerCase().includes("starting") ||
    text.toLowerCase().includes("extracting") ||
    text.toLowerCase().includes("analysing") ||
    text.toLowerCase().includes("analyzing") ||
    text.toLowerCase().includes("detecting")
  ) return "action";
  if (
    text.toLowerCase().includes("connect") ||
    text.toLowerCase().includes("upload") ||
    text.toLowerCase().includes("deploy") ||
    text.toLowerCase().includes("initializ") ||
    text.toLowerCase().includes("establ")
  ) return "system";
  return "info";
}

interface LogEntry {
  id: number;
  text: string;
  category: MsgCategory;
}

const MAX_LOG = 6;

// ─── Component ────────────────────────────────────────────────────────────────

export function ForensicProgressOverlay({
  variant,
  title,
  liveText,
  telemetryLabel = "Live status",
  showElapsed = true,
}: ForensicProgressOverlayProps) {
  const accent = variantAccent[variant];

  // Elapsed counter
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!showElapsed) return;
    const id = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(id);
  }, [showElapsed]);

  // Scrolling log — accumulate messages instead of replacing
  const [log, setLog] = useState<LogEntry[]>([]);
  const idRef = useRef(0);
  const lastTextRef = useRef("");

  useEffect(() => {
    const stripRegex = /[\u{1F300}-\u{1FFFF}]|[\u2600-\u27FF]/gu;
    const trimmed = liveText.replace(stripRegex, '').trim();
    if (!trimmed || trimmed === lastTextRef.current) return;
    lastTextRef.current = trimmed;
    const id = ++idRef.current;
    setLog((prev) => {
      const next = [...prev, { id, text: trimmed, category: categorize(trimmed) }];
      return next.length > MAX_LOG ? next.slice(next.length - MAX_LOG) : next;
    });
  }, [liveText]);

  // Stage indicator
  const currentStage = detectStage(log.map((m) => m.text), variant);
  const stageIndex = STREAM_STAGES.findIndex((s) => s.key === currentStage);

  // Per-category text colours
  const catColor: Record<MsgCategory, string> = {
    action:  accent.primary,
    success: "#4ade80",
    info:    "rgba(255,255,255,0.65)",
    system:  "rgba(255,255,255,0.38)",
  };

  return (
    <motion.div
      className="fixed inset-0 z-[250] flex items-center justify-center px-4"
      style={{
        background:
          "radial-gradient(ellipse 130% 90% at 50% -10%, rgba(10,18,38,0.97) 0%, rgba(2,6,14,0.99) 50%, rgba(0,0,0,0.97) 100%)",
        backdropFilter: "blur(28px)",
        WebkitBackdropFilter: "blur(28px)",
      }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
    >
      {/* ── Ambient layer ─────────────────────────────────────────────────── */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden" aria-hidden="true">
        {/* Primary glow */}
        <motion.div
          className="absolute -top-48 left-1/2 -translate-x-1/2 w-[min(100vw,780px)] h-[min(100vw,780px)] rounded-full"
          style={{ background: `radial-gradient(circle, ${accent.glow} 0%, transparent 62%)` }}
          animate={{ scale: [1, 1.1, 1], opacity: [0.45, 0.8, 0.45] }}
          transition={{ duration: 5.5, repeat: Infinity, ease: "easeInOut" }}
        />
        {/* Secondary corner glow */}
        <motion.div
          className="absolute -bottom-32 right-0 w-[420px] h-[420px] rounded-full opacity-25"
          style={{ background: "radial-gradient(circle, rgba(99,102,241,0.12) 0%, transparent 70%)" }}
          animate={{ x: [0, -35, 0], y: [0, -25, 0] }}
          transition={{ duration: 13, repeat: Infinity, ease: "easeInOut" }}
        />
        {/* Subtle grid */}
        <div
          className="absolute inset-0"
          style={{
            backgroundImage: `linear-gradient(${accent.primary}18 1px, transparent 1px), linear-gradient(90deg, ${accent.primary}18 1px, transparent 1px)`,
            backgroundSize: "64px 64px",
            opacity: 0.4,
          }}
        />
        {/* Floating particles */}
        {[...Array(6)].map((_, i) => (
          <motion.div
            key={i}
            className="absolute w-1 h-1 rounded-full"
            style={{
              background: accent.primary,
              left: `${15 + i * 14}%`,
              top: `${20 + (i % 3) * 25}%`,
              opacity: 0.2 + i * 0.04,
            }}
            animate={{
              y: [0, -18, 0],
              opacity: [0.15, 0.5, 0.15],
            }}
            transition={{
              duration: 3.5 + i * 0.7,
              repeat: Infinity,
              delay: i * 0.55,
              ease: "easeInOut",
            }}
          />
        ))}
      </div>

      {/* ── Card ──────────────────────────────────────────────────────────── */}
      <motion.div
        className="relative w-full max-w-[460px] rounded-3xl overflow-hidden"
        style={{
          boxShadow: `0 0 0 1px ${accent.ring}, 0 32px 96px rgba(0,0,0,0.65), inset 0 1px 0 rgba(255,255,255,0.06)`,
        }}
        initial={{ y: 32, scale: 0.93, opacity: 0 }}
        animate={{ y: 0, scale: 1, opacity: 1 }}
        transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
      >
        {/* Glass fill */}
        <div
          className="absolute inset-0 rounded-3xl"
          style={{
            background:
              "linear-gradient(160deg, rgba(255,255,255,0.055) 0%, rgba(255,255,255,0.018) 45%, rgba(0,0,0,0.22) 100%)",
          }}
        />
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/18 to-transparent" />

        <div className="relative px-7 py-7 flex flex-col items-center gap-5">

          {/* ── Header: orb + title + stage ─────────────────────────────── */}
          <div className="flex items-center gap-4 w-full">

            {/* Multi-ring orb */}
            <div className="relative w-[72px] h-[72px] flex-shrink-0 flex items-center justify-center">
              {/* Outermost slow ring */}
              <motion.div
                className="absolute inset-0 rounded-2xl"
                style={{ border: `1px solid ${accent.ring}`, opacity: 0.4 }}
                animate={{ rotate: 360 }}
                transition={{ duration: 48, repeat: Infinity, ease: "linear" }}
              />
              {/* Mid ring — counter-rotate */}
              <motion.div
                className="absolute inset-[5px] rounded-xl"
                style={{ border: `1px solid ${accent.ring}`, opacity: 0.65 }}
                animate={{ rotate: -360 }}
                transition={{ duration: 14, repeat: Infinity, ease: "linear" }}
              />
              {/* Fast arc spinner */}
              <motion.div
                className="absolute inset-[2px] rounded-2xl"
                style={{
                  border: "2px solid transparent",
                  borderTopColor: accent.primary,
                  borderRightColor: `${accent.primary}35`,
                }}
                animate={{ rotate: 360 }}
                transition={{ duration: 1.9, repeat: Infinity, ease: "linear" }}
              />
              {/* Pulsing inner glow */}
              <motion.div
                className="absolute inset-[10px] rounded-lg"
                style={{ background: `radial-gradient(circle, ${accent.glow} 0%, transparent 75%)` }}
                animate={{ scale: [0.85, 1.25, 0.85], opacity: [0.35, 0.85, 0.35] }}
                transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
              />
              {/* Core icon */}
              <div
                className="relative z-10 w-10 h-10 rounded-lg flex items-center justify-center"
                style={{
                  background: `linear-gradient(145deg, ${accent.glow}, rgba(0,0,0,0.5))`,
                  border: `1px solid ${accent.ring}`,
                  boxShadow: `0 0 22px ${accent.glow}`,
                }}
              >
                {variant === "council" ? (
                  <Radio className="w-[18px] h-[18px]" style={{ color: accent.primary }} aria-hidden />
                ) : (
                  <Activity className="w-[18px] h-[18px]" style={{ color: accent.primary }} aria-hidden />
                )}
              </div>
            </div>

            {/* Title + stage breadcrumb */}
            <div className="flex-1 min-w-0">
              <p className={`text-[9px] font-mono font-bold uppercase tracking-[0.32em] mb-0.5 ${accent.label}`}>
                {telemetryLabel}
              </p>
              <h2 className="text-[17px] font-black text-white tracking-tight font-heading uppercase leading-tight truncate">
                {title}
              </h2>

              {/* Stage breadcrumb */}
              <div className="flex items-center gap-1 mt-1.5 flex-wrap">
                {STREAM_STAGES.map((s, i) => {
                  const isActive = i === stageIndex;
                  const isDone   = i < stageIndex;
                  return (
                    <Fragment key={s.key}>
                      <div className="flex items-center gap-1">
                        <motion.div
                          className="w-1.5 h-1.5 rounded-full"
                          style={{
                            background:
                              isActive || isDone ? accent.primary : "rgba(255,255,255,0.18)",
                          }}
                          animate={
                            isActive
                              ? { scale: [1, 1.6, 1], opacity: [1, 0.55, 1] }
                              : {}
                          }
                          transition={{ duration: 1.1, repeat: Infinity }}
                        />
                        <span
                          className="text-[8px] font-mono font-bold uppercase tracking-wide"
                          style={{
                            color: isActive
                              ? accent.primary
                              : isDone
                              ? "rgba(255,255,255,0.45)"
                              : "rgba(255,255,255,0.2)",
                          }}
                        >
                          {s.label}
                        </span>
                      </div>
                      {i < STREAM_STAGES.length - 1 && (
                        <div
                          className="w-3 h-px rounded-full"
                          style={{
                            background:
                              i < stageIndex ? accent.primary : "rgba(255,255,255,0.1)",
                          }}
                        />
                      )}
                    </Fragment>
                  );
                })}
              </div>
            </div>
          </div>

          {/* ── Terminal log ─────────────────────────────────────────────── */}
          <div
            className="w-full rounded-xl overflow-hidden"
            style={{
              background: "rgba(0,0,0,0.45)",
              border: "1px solid rgba(255,255,255,0.07)",
              boxShadow: "inset 0 1px 0 rgba(255,255,255,0.04), inset 0 0 28px rgba(0,0,0,0.28)",
            }}
          >
            {/* Mac-style terminal header */}
            <div
              className="flex items-center gap-1.5 px-3 py-1.5 border-b border-white/[0.05]"
              style={{ background: "rgba(255,255,255,0.025)" }}
            >
              <div className="w-2 h-2 rounded-full bg-red-500/45"   />
              <div className="w-2 h-2 rounded-full bg-yellow-500/45"/>
              <div className="w-2 h-2 rounded-full bg-green-500/45" />
              <span
                className="ml-2 text-[8px] font-mono uppercase tracking-[0.25em] select-none"
                style={{ color: `${accent.primary}55` }}
              >
                forensic · telemetry
              </span>
              {/* Live badge */}
              <div className="ml-auto flex items-center gap-1">
                <motion.div
                  className="w-1.5 h-1.5 rounded-full"
                  style={{ background: "#4ade80" }}
                  animate={{ opacity: [1, 0.25, 1] }}
                  transition={{ duration: 1.3, repeat: Infinity }}
                />
                <span className="text-[7px] font-mono uppercase tracking-widest text-white/30">
                  live
                </span>
              </div>
            </div>

            {/* Log lines */}
            <div className="px-3 pt-2.5 pb-2 min-h-[112px] flex flex-col justify-end gap-[3px]">
              <AnimatePresence initial={false}>
                {log.length === 0 ? (
                  <motion.div
                    key="placeholder"
                    className="text-[10px] font-mono italic"
                    style={{ color: "rgba(255,255,255,0.2)" }}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                  >
                    Awaiting telemetry stream…
                  </motion.div>
                ) : (
                  log.map((entry, idx) => {
                    const isLatest = idx === log.length - 1;
                    const ageRatio = (log.length - 1 - idx) / Math.max(log.length - 1, 1);
                    const textOpacity = isLatest ? 1 : Math.max(0.18, 0.75 - ageRatio * 0.55);

                    return (
                      <motion.div
                        key={entry.id}
                        className="flex items-start gap-2 leading-none"
                        initial={{ opacity: 0, y: 10, x: -6 }}
                        animate={{ opacity: textOpacity, y: 0, x: 0 }}
                        exit={{ opacity: 0, y: -8, transition: { duration: 0.18 } }}
                        transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
                      >
                        {/* Indicator */}
                        <span
                          className="text-[9px] font-mono font-bold shrink-0 mt-[1px] w-3"
                          style={{ color: isLatest ? catColor[entry.category] : "rgba(255,255,255,0.2)" }}
                        >
                          {isLatest ? "▶" : "·"}
                        </span>
                        {/* Text */}
                        <span
                          className="text-[10.5px] font-mono leading-[1.45]"
                          style={{
                            color: isLatest
                              ? "rgba(255,255,255,0.92)"
                              : "rgba(255,255,255,0.42)",
                          }}
                          aria-live={isLatest ? "polite" : undefined}
                          aria-atomic={isLatest ? "true" : undefined}
                        >
                          {entry.text}
                        </span>
                      </motion.div>
                    );
                  })
                )}
              </AnimatePresence>

              {/* Blinking cursor */}
              <motion.span
                className="text-[11px] font-mono leading-none"
                style={{ color: accent.primary }}
                animate={{ opacity: [1, 1, 0, 0] }}
                transition={{ duration: 1.0, repeat: Infinity, ease: "linear", times: [0, 0.45, 0.5, 1] }}
              >
                █
              </motion.span>
            </div>
          </div>

          {/* ── Scan bar ─────────────────────────────────────────────────── */}
          <div
            className="w-full h-[3px] rounded-full overflow-hidden"
            style={{ background: "rgba(255,255,255,0.05)" }}
          >
            <motion.div
              className="h-full w-1/4 rounded-full"
              style={{
                background: `linear-gradient(90deg, transparent, ${accent.primary}, ${accent.primary}55, transparent)`,
                boxShadow: `0 0 14px ${accent.primary}`,
              }}
              animate={{ x: ["-130%", "240%"] }}
              transition={{ duration: 2.0, repeat: Infinity, ease: "easeInOut" }}
            />
          </div>

          {/* ── Footer ───────────────────────────────────────────────────── */}
          {showElapsed && (
            <div className="flex items-center justify-between w-full">
              <span
                className="text-[8px] font-mono font-bold uppercase tracking-widest"
                style={{ color: `${accent.primary}55` }}
              >
                {variant === "council" ? "Council deliberation" : "Forensic stream"}
              </span>
              <span className="text-[8px] font-mono font-bold tracking-widest text-white/22 uppercase">
                {elapsed}s elapsed
              </span>
            </div>
          )}

        </div>
      </motion.div>
    </motion.div>
  );
}

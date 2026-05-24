"use client";

import React from "react";
import { Activity, Gauge, ShieldAlert } from "lucide-react";
import { motion, useReducedMotion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import type { VerdictConfig } from "@/lib/verdict";

interface VerdictSectionProps {
  vc: VerdictConfig;
  confPct: number;
  manipPct: number;
  errPct: number;
  discordPct: number;
  isDeepPhase: boolean;
  agentCount: number;
}

const VERDICT_THEMES: Record<string, { color: string; colorRgb: string; labelColor: string }> = {
  emerald: { color: "var(--color-success-light)", colorRgb: "var(--color-success-light-rgb)", labelColor: "var(--color-success-light)" },
  red:     { color: "var(--color-danger)",        colorRgb: "var(--color-danger-rgb)",        labelColor: "#fca5a5" },
  amber:   { color: "var(--color-warning)",       colorRgb: "var(--color-warning-rgb)",       labelColor: "var(--color-warning)" },
};

export function VerdictSection({
  vc,
  confPct,
  manipPct,
  errPct,
  discordPct,
  isDeepPhase,
  agentCount,
}: VerdictSectionProps) {
  const prefersReduced = useReducedMotion();
  const theme = VERDICT_THEMES[vc.color] ?? VERDICT_THEMES.amber;
  const VerdictIcon = vc.Icon;

  const primaryText = vc.desc;

  return (
    <section className="relative flex flex-col overflow-hidden fc-surface rounded-2xl border border-white/10 shadow-2xl">
      {/* Cryptographic Watermark Background */}
      <div className="absolute -right-20 -top-20 opacity-[0.03] pointer-events-none select-none z-0 mix-blend-overlay">
        <VerdictIcon className="w-96 h-96" style={{ color: theme.color }} aria-hidden="true" />
      </div>

      <div
        className="px-6 md:px-10 py-8 relative z-10"
        style={{
          background: `radial-gradient(circle at top left, rgba(${theme.colorRgb}, 0.15), transparent 70%)`,
          borderBottom: `1px solid rgba(${theme.colorRgb}, 0.2)`,
        }}
      >
        <div className="flex items-start justify-between gap-6">
          <div className="flex items-center gap-5 min-w-0">
            {/* Elevated Icon Container */}
            <div
              className="w-16 h-16 rounded-2xl flex items-center justify-center shrink-0 border backdrop-blur-md relative overflow-hidden"
              style={{
                borderColor: `rgba(${theme.colorRgb}, 0.4)`,
                backgroundColor: `rgba(${theme.colorRgb}, 0.1)`,
                boxShadow: `0 0 30px rgba(${theme.colorRgb}, 0.2)`,
              }}
            >
              <div className="absolute inset-0 bg-gradient-to-tr from-transparent via-white/10 to-transparent translate-y-[-100%] animate-[shimmer_3s_infinite]" />
              <VerdictIcon className="w-8 h-8" style={{ color: theme.color }} aria-hidden="true" />
            </div>

            <div className="min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <div className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ backgroundColor: theme.color }} />
                <div className="text-xs font-mono tracking-widest uppercase" style={{ color: theme.labelColor }}>
                  Official Council Verdict &middot; {isDeepPhase ? "Deep" : "Initial"}
                </div>
              </div>

              <motion.h2
                initial={prefersReduced ? false : { opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.4, delay: 0.2, ease: "easeOut" }}
                className="text-4xl md:text-5xl font-heading font-black leading-none tracking-tight text-white drop-shadow-md"
                role="alert"
              >
                {vc.label}
              </motion.h2>
            </div>
          </div>

          <div className="text-right shrink-0 hidden sm:flex flex-col items-end justify-center">
            <div className="text-6xl font-mono font-black leading-none tabular-nums" style={{ color: theme.color, textShadow: `0 0 20px rgba(${theme.colorRgb}, 0.4)` }}>
              {confPct}%
            </div>
            <div className="text-xs font-mono tracking-widest uppercase fc-text-muted mt-2 border-t border-white/10 pt-1">
              Confidence Index
            </div>
          </div>
        </div>

        {primaryText && (
          <p className="mt-6 text-base text-white/80 leading-relaxed max-w-3xl font-medium border-l-2 pl-4" style={{ borderColor: theme.color }}>
            {primaryText}
          </p>
        )}

        {agentCount > 0 && (
          <p className="mt-3 text-xs font-mono" style={{ color: theme.labelColor }}>
            Signed {isDeepPhase ? "deep-analysis" : "initial-analysis"} report &middot; {agentCount} active agent{agentCount === 1 ? "" : "s"} &middot; {confPct}% aggregate confidence.
          </p>
        )}
      </div>

      {/* Metric Strip */}
      <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-white/[0.06] bg-black/40">
        <MetricCell
          label="Manipulation Risk"
          value={manipPct}
          color={manipPct > 50 ? "var(--color-danger)" : "var(--color-success-light)"}
          icon={ShieldAlert}
        />
        <MetricCell
          label="Tool Error Rate"
          value={errPct}
          color={errPct > 20 ? "var(--color-warning)" : "var(--color-success-light)"}
          icon={Gauge}
          inverted
        />
        <MetricCell
          label="Agent Spread"
          value={discordPct}
          color={discordPct > 20 ? "var(--color-warning)" : "var(--color-success-light)"}
          icon={Activity}
          inverted
        />
      </div>
    </section>
  );
}

function MetricCell({
  label,
  value,
  color,
  icon: Icon,
  inverted = false,
}: {
  label: string;
  value: number;
  color: string;
  icon: LucideIcon;
  inverted?: boolean;
}) {
  const prefersReduced = useReducedMotion();
  const clampedValue = Math.max(0, Math.min(100, value));

  const totalSegments = 20;
  const activeSegments = Math.round((clampedValue / 100) * totalSegments);

  return (
    <div className="px-5 py-5 flex flex-col justify-between group hover:bg-white/[0.02] transition-colors">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-widest fc-text-muted">
          <Icon className="w-3.5 h-3.5 opacity-70" aria-hidden="true" />
          <span className="truncate">{label}</span>
        </div>
        <span className="text-lg font-mono font-bold tabular-nums" style={{ color }}>
          {value}%
        </span>
      </div>

      {/* Segmented Tactical Bar */}
      <div className="flex gap-[2px] h-1.5 w-full" aria-hidden="true">
        {Array.from({ length: totalSegments }).map((_, i) => {
          const isActive = inverted
            ? i >= (totalSegments - activeSegments)
            : i < activeSegments;

          return (
            <motion.div
              key={i}
              initial={prefersReduced ? false : { opacity: 0 }}
              animate={{ opacity: isActive ? 1 : 0.2 }}
              transition={{ delay: i * 0.02 }}
              className="flex-1 rounded-sm"
              style={{ backgroundColor: isActive ? color : 'rgba(255,255,255,0.1)' }}
            />
          );
        })}
      </div>
    </div>
  );
}

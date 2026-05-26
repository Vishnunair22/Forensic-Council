"use client";

import React from "react";
import { Activity, Gauge, ShieldAlert } from "lucide-react";
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
            {/* Icon container — no neon glow, no inline backdrop-blur */}
            <div
              className="w-16 h-16 rounded-2xl flex items-center justify-center shrink-0 border relative overflow-hidden"
              style={{
                borderColor: `rgba(${theme.colorRgb}, 0.4)`,
                backgroundColor: `rgba(${theme.colorRgb}, 0.1)`,
              }}
            >
              <VerdictIcon className="w-8 h-8" style={{ color: theme.color }} aria-hidden="true" />
            </div>

            <div className="min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <div className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ backgroundColor: theme.color }} />
                <p className="text-xs fc-text-secondary font-medium">
                  Official Council Verdict &middot; {isDeepPhase ? "Deep" : "Initial"}
                </p>
              </div>

              <h2
                className="text-4xl md:text-5xl font-heading font-black leading-none tracking-tight text-white drop-shadow-md"
                role="alert"
              >
                {vc.label}
              </h2>
            </div>
          </div>

          <div className="text-right shrink-0 hidden sm:flex flex-col items-end justify-center">
            <div className="text-6xl font-mono font-black leading-none tabular-nums" style={{ color: theme.color }}>
              {confPct}%
            </div>
            <div className="text-xs fc-text-muted mt-2 border-t border-white/10 pt-1">
              Confidence Index
            </div>
          </div>
        </div>

        {primaryText && (
          <p className="mt-6 text-base fc-text-secondary leading-relaxed max-w-3xl font-medium border-l-2 pl-4" style={{ borderColor: theme.color }}>
            {primaryText}
          </p>
        )}

        {agentCount > 0 && (
          <p className="mt-3 text-xs fc-text-muted">
            Signed {isDeepPhase ? "deep-analysis" : "initial-analysis"} report &middot; {agentCount} active agent{agentCount === 1 ? "" : "s"} &middot; {confPct}% aggregate confidence.
          </p>
        )}
      </div>

      {/* Metric Strip */}
      <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-white/[0.06]">
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
  const clampedValue = Math.max(0, Math.min(100, value));
  const fillPct = inverted ? 100 - clampedValue : clampedValue;

  return (
    <div className="px-5 py-5 flex flex-col justify-between group hover:bg-white/[0.02] transition-colors duration-[160ms]">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-xs fc-text-muted">
          <Icon className="w-3.5 h-3.5 opacity-70" aria-hidden="true" />
          <span className="truncate">{label}</span>
        </div>
        <span className="text-lg font-mono font-bold tabular-nums" style={{ color }}>
          {value}%
        </span>
      </div>

      {/* Simple progress bar — replaces 20-segment LED array */}
      <div
        className="h-1.5 w-full rounded-full overflow-hidden"
        style={{ background: "rgba(255,255,255,0.08)" }}
        aria-hidden="true"
      >
        <div
          className="h-full rounded-full transition-[width] duration-[160ms] ease-out"
          style={{ width: `${fillPct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

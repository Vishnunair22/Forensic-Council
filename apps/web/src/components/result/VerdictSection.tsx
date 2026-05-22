"use client";

import React from "react";
import { Activity, Gauge, ShieldAlert } from "lucide-react";
import { motion } from "framer-motion";
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
  verdictSentence?: string | null;
}

const VERDICT_THEMES: Record<string, { color: string; colorRgb: string }> = {
  emerald: { color: "var(--color-success-light)", colorRgb: "var(--color-success-light-rgb)" },
  red:     { color: "var(--color-danger)",        colorRgb: "var(--color-danger-rgb)"        },
  amber:   { color: "var(--color-warning)",       colorRgb: "var(--color-warning-rgb)"       },
};

export function VerdictSection({
  vc,
  confPct,
  manipPct,
  errPct,
  discordPct,
  isDeepPhase,
  agentCount,
  verdictSentence,
}: VerdictSectionProps) {
  const theme = VERDICT_THEMES[vc.color] ?? VERDICT_THEMES.amber;
  const VerdictIcon = vc.Icon;

  const agentLine = agentCount > 0
    ? `Signed ${isDeepPhase ? "deep-analysis" : "initial-analysis"} report — ${agentCount} active agent${agentCount === 1 ? "" : "s"} · ${confPct}% aggregate confidence.`
    : null;
  const primaryText = verdictSentence ?? vc.desc;

  return (
    <section className="rounded-2xl border border-white/[0.06] overflow-hidden">
      {/* Verdict Hero */}
      <div
        className="px-6 md:px-8 py-7"
        style={{
          background: `linear-gradient(135deg, rgba(${theme.colorRgb}, 0.09) 0%, transparent 60%)`,
          borderBottom: `1px solid rgba(${theme.colorRgb}, 0.13)`,
        }}
      >
        <div className="flex items-start justify-between gap-6">
          <div className="flex items-center gap-4 min-w-0">
            <div
              className="w-12 h-12 rounded-2xl flex items-center justify-center shrink-0 border"
              style={{
                borderColor: `rgba(${theme.colorRgb}, 0.22)`,
                backgroundColor: `rgba(${theme.colorRgb}, 0.09)`,
              }}
            >
              <VerdictIcon className="w-6 h-6" style={{ color: theme.color }} />
            </div>
            <div className="min-w-0">
              <div className="fc-eyebrow" style={{ color: theme.color }}>
                Final Verdict · {isDeepPhase ? "Deep" : "Initial"} Analysis · Arbiter Signed
              </div>
              <motion.h2
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.16, ease: "easeOut" }}
                className="mt-1 text-3xl md:text-4xl font-heading font-bold leading-none tracking-tight"
                style={{ color: theme.color }}
              >
                {vc.label}
              </motion.h2>
            </div>
          </div>

          <div className="text-right shrink-0 hidden sm:block">
            <div className="text-5xl font-mono font-bold leading-none tabular-nums" style={{ color: theme.color }}>
              {confPct}%
            </div>
            <div className="fc-eyebrow fc-text-muted mt-2">Confidence</div>
          </div>
        </div>

        {primaryText && (
          <p className="mt-4 text-sm fc-text-muted leading-relaxed max-w-2xl">{primaryText}</p>
        )}
        {agentLine && (
          <p className="mt-1.5 text-xs font-mono fc-text-muted">{agentLine}</p>
        )}
      </div>

      {/* Metric Strip */}
      <div className="grid grid-cols-3 divide-x divide-white/[0.06]">
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
        />
        <MetricCell
          label="Agent Spread"
          value={discordPct}
          color={discordPct > 20 ? "var(--color-warning)" : "var(--color-success-light)"}
          icon={Activity}
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
}: {
  label: string;
  value: number;
  color: string;
  icon: LucideIcon;
}) {
  return (
    <div className="px-4 md:px-5 py-4">
      <div className="flex items-center gap-1.5 fc-eyebrow fc-text-muted mb-2">
        <Icon className="w-3 h-3 shrink-0" />
        <span className="truncate">{label}</span>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-xl font-mono font-bold tabular-nums shrink-0" style={{ color }}>
          {value}%
        </span>
        <div className="flex-1 h-1 bg-white/[0.06] rounded-full overflow-hidden">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${Math.max(0, Math.min(100, value))}%` }}
            transition={{ duration: 0.16, ease: "easeOut" }}
            className="h-full rounded-full"
            style={{ backgroundColor: color }}
          />
        </div>
      </div>
    </div>
  );
}

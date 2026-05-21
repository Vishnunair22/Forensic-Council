"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  Activity,
  Check,
  Copy,
  Fingerprint,
  Gauge,
  Shield,
  ShieldAlert,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { motion } from "framer-motion";
import clsx from "clsx";
import type { ReportDTO } from "@/lib/api";
import type { VerdictConfig } from "@/lib/verdict";
import { EvidenceThumbnail } from "./EvidenceThumbnail";

interface ResultHeaderProps {
  report: ReportDTO;
  fileName: string;
  mimeType: string | null;
  thumbnail: string | null;
  isDeepPhase: boolean;
  vc: VerdictConfig;
  confPct: number;
  manipPct: number;
  errPct: number;
  discordPct: number;
  activeAgentIds: string[];
  pipelineDuration: string | null;
}

const VERDICT_THEMES: Record<string, { color: string; colorRgb: string; icon: LucideIcon }> = {
  emerald: { color: "var(--color-success-light)", colorRgb: "var(--color-success-light-rgb)", icon: ShieldCheck },
  red:     { color: "var(--color-danger)",        colorRgb: "var(--color-danger-rgb)",        icon: ShieldAlert },
  amber:   { color: "var(--color-warning)",       colorRgb: "var(--color-warning-rgb)",       icon: Shield      },
};

export function ResultHeader({
  report,
  fileName,
  mimeType,
  thumbnail,
  isDeepPhase,
  vc,
  confPct,
  manipPct,
  errPct,
  discordPct,
  activeAgentIds,
  pipelineDuration,
}: ResultHeaderProps) {
  const theme = VERDICT_THEMES[vc.color] || VERDICT_THEMES.amber;
  const VerdictIcon = theme.icon;
  const displayName = cleanDisplayName(fileName, report);
  const signature = report.cryptographic_signature || report.report_hash || "";
  const [copied, setCopied] = useState(false);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    };
  }, []);

  const handleCopyHash = () => {
    if (!signature) return;
    navigator.clipboard.writeText(signature).then(() => {
      setCopied(true);
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => setCopied(false), 2000);
    }).catch(() => {});
  };

  return (
    <section className="overflow-hidden rounded-2xl border border-white/[0.06]">

      {/* ── Verdict Hero ── */}
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
                className="mt-1 text-3xl md:text-4xl font-heading font-bold leading-none tracking-tight"
                style={{ color: theme.color }}
              >
                {vc.label}
              </motion.h2>
            </div>
          </div>

          <div className="text-right shrink-0 hidden sm:block">
            <div
              className="text-5xl font-mono font-bold leading-none tabular-nums"
              style={{ color: theme.color }}
            >
              {confPct}%
            </div>
            <div className="fc-eyebrow fc-text-faint mt-2">Confidence</div>
          </div>
        </div>

        <p className="mt-4 text-sm fc-text-muted leading-relaxed max-w-2xl">
          {buildVerdictContext({
            confidence: confPct,
            agents: activeAgentIds.length,
            phase: isDeepPhase ? "deep" : "initial",
            fallback: vc.desc,
          })}
        </p>
      </div>

      {/* ── Metric Strip ── */}
      <div className="grid grid-cols-3 divide-x divide-white/[0.06] border-b border-white/[0.06]">
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

      {/* ── File + Integrity Footer ── */}
      <div className="px-6 md:px-8 py-4 flex items-center gap-4 justify-between flex-wrap">
        <div className="flex items-center gap-3 min-w-0">
          <EvidenceThumbnail
            thumbnail={thumbnail}
            mimeType={mimeType}
            fileName={fileName}
            className="w-9 h-9 rounded-lg border border-white/10 shrink-0"
          />
          <div className="min-w-0">
            <h1 className="text-sm font-bold text-white/90 truncate">{displayName}</h1>
            <div className="flex items-center flex-wrap gap-x-2 gap-y-0.5 mt-0.5">
              {mimeType && <span className="fc-eyebrow fc-text-faint">{mimeType}</span>}
              <span className="fc-text-faint text-[10px]">·</span>
              <span className="fc-eyebrow fc-text-faint">Case {shortId(report.case_id)}</span>
              <span className="fc-text-faint text-[10px]">·</span>
              <span className="fc-eyebrow fc-text-faint">
                {activeAgentIds.length} agent{activeAgentIds.length === 1 ? "" : "s"}
              </span>
              {pipelineDuration && (
                <>
                  <span className="fc-text-faint text-[10px]">·</span>
                  <span className="fc-eyebrow fc-text-faint">{pipelineDuration}</span>
                </>
              )}
            </div>
          </div>
        </div>

        {signature && (
          <div className="flex items-center gap-2 shrink-0">
            <p className="text-xs font-mono fc-text-faint hidden md:block max-w-[180px] truncate">
              {signature.slice(0, 26)}…
            </p>
            <button
              type="button"
              onClick={handleCopyHash}
              aria-label="Copy report hash to clipboard"
              className="flex items-center gap-1.5 fc-eyebrow fc-text-muted hover:text-primary-accent transition-colors rounded px-2 py-1 border border-white/[0.08] hover:border-white/[0.15] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
            >
              {copied ? <Check className="w-3 h-3 text-success" /> : <Copy className="w-3 h-3" />}
              {copied ? "Copied" : "Hash"}
            </button>
            <div className="flex items-center gap-1.5 fc-eyebrow text-success">
              <Fingerprint className="w-3.5 h-3.5" />
              Verified
            </div>
          </div>
        )}
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
      <div className="flex items-center gap-1.5 fc-eyebrow fc-text-faint mb-2">
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
            transition={{ duration: 0.6, ease: "easeOut" }}
            className="h-full rounded-full"
            style={{ backgroundColor: color }}
          />
        </div>
      </div>
    </div>
  );
}

function buildVerdictContext({
  confidence,
  agents,
  phase,
  fallback,
}: {
  confidence: number;
  agents: number;
  phase: "initial" | "deep";
  fallback: string;
}): string {
  if (agents <= 0) return fallback;
  const phaseLabel = phase === "deep" ? "deep-analysis" : "initial-analysis";
  return `Signed ${phaseLabel} report based on ${agents} active agent${agents === 1 ? "" : "s"} with ${confidence}% aggregate confidence.`;
}

function cleanDisplayName(fileName: string, report: ReportDTO): string {
  if (!fileName || fileName.startsWith("CASE-")) {
    return report.case_id ? `Evidence ${shortId(report.case_id)}` : "Evidence File";
  }
  return fileName;
}

function shortId(value: string | null | undefined): string {
  if (!value) return "Unavailable";
  return value.length > 12 ? value.slice(-8) : value;
}

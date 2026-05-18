"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  Activity,
  Clock3,
  Copy,
  Check,
  Fingerprint,
  FileType,
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
import { ArcGauge } from "./ArcGauge";

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

// V-C-3: verdict accent colors resolve to semantic CSS variables. `colorRgb`
// pairs each color with its r,g,b tuple so the `borderColor` / `backgroundColor`
// styles below can render `rgba(...)` with the same alpha levels we previously
// got from concatenating hex opacity suffixes (e.g. "#A7FFD230").
const VERDICT_THEMES: Record<string, { color: string; colorRgb: string; icon: LucideIcon; tone: string }> = {
  emerald: { color: "var(--color-success-light)", colorRgb: "var(--color-success-light-rgb)", icon: ShieldCheck, tone: "text-success border-success/20 bg-success/5" },
  red:     { color: "var(--color-danger)",        colorRgb: "var(--color-danger-rgb)",        icon: ShieldAlert, tone: "text-danger border-danger/20 bg-danger/5" },
  amber:   { color: "var(--color-warning)",       colorRgb: "var(--color-warning-rgb)",       icon: Shield,      tone: "text-warning border-warning/20 bg-warning/5" },
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

  // F-L-5: clear the copy-flash timer on unmount so it can't setState on a
  // torn-down component after navigation.
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
    <section
      className="overflow-hidden rounded-2xl"
      style={{
        border: "1px solid rgba(165,200,255,0.08)",
      }}
    >
      <div className="p-6 md:p-8 space-y-7">
        <div className="flex flex-col lg:flex-row gap-6 lg:gap-8">
          <EvidenceThumbnail
            thumbnail={thumbnail}
            mimeType={mimeType}
            fileName={fileName}
            className="w-full lg:w-48 h-40 lg:h-36 rounded-xl border border-white/10 shadow-xl"
          />

          <div className="flex-1 min-w-0 flex flex-col justify-center">
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <Pill icon={FileType} label={mimeType || "Unknown file type"} />
              <Pill icon={Activity} label={isDeepPhase ? "Deep analysis" : "Initial analysis"} />
              <Pill icon={Clock3} label={pipelineDuration ? `Completed in ${pipelineDuration}` : "Report complete"} />
            </div>

            <h1 className="text-2xl md:text-3xl font-heading font-bold text-white/90 tracking-tight truncate">
              {displayName}
            </h1>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 fc-eyebrow fc-text-faint">
              <span>Case {shortId(report.case_id)}</span>
              <span>Session {shortId(report.session_id)}</span>
              <span>{activeAgentIds.length} active agent{activeAgentIds.length === 1 ? "" : "s"}</span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_auto] gap-6 items-center border-t border-white/6 pt-7">
          <div className="flex items-start gap-4 min-w-0">
            <div
              className="w-14 h-14 rounded-2xl border flex items-center justify-center shrink-0"
              style={{
                borderColor: `rgba(${theme.colorRgb}, 0.19)`,
                backgroundColor: `transparent`,
              }}
            >
              <VerdictIcon className="w-7 h-7" style={{ color: theme.color }} />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-3">
                <span
                  className="fc-eyebrow"
                  style={{ color: theme.color }}
                >
                  Final Verdict
                </span>
                <span className={clsx("px-2.5 py-1 rounded-md border fc-eyebrow", theme.tone)}>
                  Arbiter Signed
                </span>
              </div>
              <motion.h2
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="mt-1 text-4xl md:text-5xl font-heading font-bold leading-none tracking-tight"
                style={{ color: theme.color }}
              >
                {vc.label}
              </motion.h2>
              <p className="mt-3 max-w-3xl text-sm fc-text-muted leading-relaxed">
                {buildVerdictContext({
                  confidence: confPct,
                  agents: activeAgentIds.length,
                  phase: isDeepPhase ? "deep" : "initial",
                  fallback: vc.desc,
                })}
              </p>
            </div>
          </div>

          <div className="flex items-center justify-between lg:justify-end gap-5 border border-white/8 rounded-2xl bg-transparent px-5 py-4">
            <div>
              <div className="fc-eyebrow fc-text-muted">Confidence</div>
              <div className="mt-1 text-4xl font-mono font-bold tracking-tight" style={{ color: theme.color }}>
                {confPct}%
              </div>
            </div>
            <div className="w-24 h-24 shrink-0">
              <ArcGauge value={confPct} label="" sublabel="" color={theme.color} />
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Metric label="Manipulation Risk" value={manipPct} color={manipPct > 50 ? "var(--color-danger)" : "var(--color-success-light)"} icon={ShieldAlert} />
          <Metric label="Tool Error Rate" value={errPct} color={errPct > 20 ? "var(--color-warning)" : "var(--color-success-light)"} icon={Gauge} />
          <Metric label="Agent Spread" value={discordPct} color={discordPct > 20 ? "var(--color-warning)" : "var(--color-success-light)"} icon={Activity} />
        </div>

        {signature && (
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 rounded-xl border border-white/8 bg-transparent px-4 py-3">
            <div className="min-w-0">
              <div className="fc-eyebrow fc-text-faint">
                Report Integrity
              </div>
              <p className="mt-1 text-xs font-mono fc-text-muted truncate">
                {signature}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={handleCopyHash}
                aria-label="Copy report hash to clipboard"
                title="Copy hash"
                className="flex items-center gap-1.5 fc-eyebrow fc-text-muted hover:text-primary-accent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 rounded px-2 py-1"
              >
                {copied ? <Check className="w-3 h-3 text-success" /> : <Copy className="w-3 h-3" />}
                {copied ? "Copied" : "Copy"}
              </button>
              <div className="flex items-center gap-2 fc-eyebrow text-success">
                <Fingerprint className="w-3.5 h-3.5" />
                Verified
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function Pill({ icon: Icon, label }: { icon: LucideIcon; label: string }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-md border border-white/8 bg-transparent px-2.5 py-1.5 fc-eyebrow fc-text-faint">
      <Icon className="w-3 h-3 text-white/25" />
      {label}
    </span>
  );
}

function Metric({ label, value, color, icon: Icon }: { label: string; value: number; color: string; icon: LucideIcon }) {
  return (
    <div className="rounded-xl border border-white/8 bg-transparent p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <Icon className="w-3.5 h-3.5 shrink-0 text-white/25" />
          <span className="fc-eyebrow fc-text-faint truncate">
            {label}
          </span>
        </div>
        <span className="text-lg font-mono font-bold" style={{ color }}>
          {value}%
        </span>
      </div>
      <div className="mt-3 h-1.5 bg-white/6 rounded-full overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${Math.max(0, Math.min(100, value))}%` }}
          transition={{ duration: 0.9, ease: "easeOut" }}
          className="h-full rounded-full"
          style={{ backgroundColor: color }}
        />
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

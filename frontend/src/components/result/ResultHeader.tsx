"use client";

import { Lock, Fingerprint } from "lucide-react";
import type { ReportDTO } from "@/lib/api";
import type { VerdictConfig } from "@/lib/verdict";
import { ArcGauge } from "./ArcGauge";
import { EvidenceThumbnail } from "./EvidenceThumbnail";

interface ResultHeaderProps {
  report: ReportDTO;
  fileName: string;
  mimeType: string | null;
  thumbnail: string | null;
  isDeepPhase: boolean;
  vc: VerdictConfig;
  confPct: number;
  errPct: number;
  manipPct: number;
  activeAgentIds: string[];
  pipelineDuration: string | null;
}

const VERDICT_BORDER: Record<string, string> = {
  emerald: "border-emerald-500/30",
  red: "border-red-500/30",
  amber: "border-amber-500/30",
};

const VERDICT_GLOW: Record<string, string> = {
  emerald: "rgba(52,211,153,0.06)",
  red: "rgba(239,68,68,0.06)",
  amber: "rgba(245,158,11,0.06)",
};

export function ResultHeader({
  report,
  fileName,
  mimeType,
  thumbnail,
  isDeepPhase,
  vc,
  confPct,
  errPct,
  manipPct,
  activeAgentIds,
  pipelineDuration,
}: ResultHeaderProps) {
  const borderClass = VERDICT_BORDER[vc.color] ?? "border-white/[0.06]";
  const glowBg = VERDICT_GLOW[vc.color] ?? "transparent";

  // Gauge accent colour per verdict
  const confColor =
    vc.color === "emerald"
      ? "#34d399"
      : vc.color === "red"
        ? "#f87171"
        : "#fbbf24";

  const manipColor =
    manipPct >= 60 ? "#f87171" : manipPct >= 30 ? "#fbbf24" : "#34d399";

  return (
    <section
      aria-label="Forensic verdict summary"
      className={`rounded-3xl overflow-hidden border ${borderClass} glass-panel`}
      style={{ background: glowBg }}
    >
      {/* ── Top accent bar ──────────────────────────────────────────────── */}
      <div
        className="h-1 w-full"
        style={{
          background: `linear-gradient(90deg, transparent, ${confColor}80, transparent)`,
        }}
        aria-hidden="true"
      />

      <div className="p-6 md:p-8 space-y-6">
        {/* ── Row 1: file + verdict ───────────────────────────────────────── */}
        <div className="flex flex-col md:flex-row gap-6 items-start">
          {/* Thumbnail */}
          <EvidenceThumbnail
            thumbnail={thumbnail}
            mimeType={mimeType}
            fileName={fileName}
            className="w-full md:w-48 shrink-0"
          />

          {/* Verdict block */}
          <div className="flex-1 min-w-0 space-y-4">
            {/* File name */}
            <p className="text-[10px] font-mono font-bold uppercase tracking-widest text-white/30 truncate">
              {fileName}
            </p>

            {/* Verdict icon + label */}
            <div className="flex items-center gap-3">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
                style={{
                  background: `${confColor}18`,
                  border: `1px solid ${confColor}35`,
                }}
              >
                <vc.Icon
                  className="w-5 h-5"
                  style={{ color: confColor }}
                  aria-hidden="true"
                />
              </div>
              <div>
                <p
                  className="text-3xl font-black uppercase tracking-tight leading-none"
                  style={{ color: confColor }}
                >
                  {vc.label}
                </p>
                <p className="text-[11px] text-white/40 mt-1 font-medium">
                  {vc.desc}
                </p>
              </div>
            </div>

            {/* Verdict sentence */}
            {report.verdict_sentence && (
              <p className="text-sm text-white/70 leading-relaxed border-l-2 border-white/10 pl-4 italic">
                {report.verdict_sentence}
              </p>
            )}

            {/* Meta row */}
            <div className="flex flex-wrap gap-3 items-center">
              <div className="flex items-center gap-1.5 text-[10px] font-mono text-white/30">
                <Lock className="w-3 h-3" aria-hidden="true" />
                <span className="text-white/50 font-bold">
                  {activeAgentIds.length}
                </span>{" "}
                agents active
              </div>
              {pipelineDuration && (
                <div className="text-[10px] font-mono text-white/30">
                  Pipeline:{" "}
                  <span className="text-white/50 font-bold">
                    {pipelineDuration}
                  </span>
                </div>
              )}
              {isDeepPhase && (
                <span className="text-[9px] font-mono font-bold uppercase tracking-widest px-2 py-0.5 rounded-full bg-violet-500/15 border border-violet-500/30 text-violet-400">
                  Deep Analysis
                </span>
              )}
            </div>
          </div>
        </div>

        {/* ── Row 2: gauge metrics ─────────────────────────────────────────── */}
        <div
          className="grid grid-cols-3 gap-4 pt-4 border-t border-white/[0.05]"
          role="group"
          aria-label="Analysis metrics"
        >
          <ArcGauge
            value={confPct}
            color={confColor}
            label="Confidence"
            sublabel="Overall"
          />
          <ArcGauge
            value={manipPct}
            color={manipColor}
            label="Manipulation"
            sublabel="Probability"
          />
          <ArcGauge
            value={errPct}
            color={errPct > 30 ? "#f87171" : "#34d399"}
            label="Error Rate"
            sublabel="Pipeline"
          />
        </div>

        {/* ── Row 3: cryptographic integrity ──────────────────────────────── */}
        {report.cryptographic_signature && (
          <div
            className="flex items-start gap-3 rounded-xl bg-white/[0.02] border border-white/[0.04] px-4 py-3"
            aria-label="Cryptographic signature"
          >
            <Fingerprint
              className="w-4 h-4 text-cyan-400/60 shrink-0 mt-0.5"
              aria-hidden="true"
            />
            <div className="min-w-0 flex-1">
              <p className="text-[9px] font-mono font-bold uppercase tracking-widest text-white/25 mb-1">
                ECDSA P-256 Signature
              </p>
              <p className="text-[10px] font-mono text-white/35 truncate">
                {report.cryptographic_signature.slice(0, 64)}…
              </p>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

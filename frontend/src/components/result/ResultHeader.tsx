"use client";

import React from "react";
import { Lock, Fingerprint, ShieldCheck, ShieldAlert, Shield, type LucideIcon } from "lucide-react";
import type { ReportDTO } from "@/lib/api";
import type { VerdictConfig } from "@/lib/verdict";
import { ArcGauge } from "./ArcGauge";
import { EvidenceThumbnail } from "./EvidenceThumbnail";
import { clsx } from "clsx";

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

const VERDICT_THEMES: Record<string, { border: string; glow: string; text: string; bg: string; icon: LucideIcon }> = {
  emerald: { 
    border: "border-emerald-500/20", 
    glow: "shadow-[0_0_40px_rgba(16,185,129,0.05)]", 
    text: "text-emerald-400", 
    bg: "bg-emerald-500/5",
    icon: ShieldCheck 
  },
  red: { 
    border: "border-rose-500/20", 
    glow: "shadow-[0_0_40px_rgba(244,63,94,0.05)]", 
    text: "text-rose-400", 
    bg: "bg-rose-500/5",
    icon: ShieldAlert 
  },
  amber: { 
    border: "border-amber-500/20", 
    glow: "shadow-[0_0_40px_rgba(245,158,11,0.05)]", 
    text: "text-amber-400", 
    bg: "bg-amber-500/5",
    icon: Shield 
  },
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
  const theme = VERDICT_THEMES[vc.color] || VERDICT_THEMES.amber;

  return (
    <section 
      aria-label="Forensic Verdict Summary"
      className={clsx(
        "rounded-3xl border overflow-hidden glass-panel transition-all duration-700",
        theme.border,
        theme.glow
      )}
    >
      {/* Dynamic Status Bar */}
      <div className={clsx("h-1 w-full bg-gradient-to-r from-transparent via-current to-transparent opacity-30", theme.text)} />

      <div className="p-8 space-y-8">
        <div className="flex flex-col lg:flex-row gap-8 items-start">
          {/* Enhanced Thumbnail */}
          <div className="w-full lg:w-56 shrink-0">
            <EvidenceThumbnail
              thumbnail={thumbnail}
              mimeType={mimeType}
              fileName={fileName}
              className="w-full aspect-square rounded-2xl border-white/5 shadow-2xl"
            />
          </div>

          {/* Verdict Intelligence */}
          <div className="flex-1 min-w-0 space-y-6">
            <div className="space-y-1">
              <p className="text-[10px] font-black font-mono uppercase tracking-[0.3em] text-white/20">
                Case Entry: {report.case_id || "FC-DEFAULT"}
              </p>
              <h2 className="text-sm font-bold text-white/40 truncate uppercase tracking-widest">{fileName}</h2>
            </div>

            <div className="flex items-center gap-5">
              <div className={clsx("w-14 h-14 rounded-2xl flex items-center justify-center shrink-0 border transition-transform hover:scale-105 duration-500", theme.bg, theme.border)}>
                <theme.icon className={clsx("w-7 h-7", theme.text)} />
              </div>
              <div className="space-y-1">
                <p className={clsx("text-4xl font-black uppercase tracking-tighter leading-none font-heading", theme.text)}>
                  {vc.label}
                </p>
                <p className="text-[11px] font-bold text-white/30 uppercase tracking-[0.1em]">{vc.desc}</p>
              </div>
            </div>

            {report.verdict_sentence && (
              <div className="relative p-5 rounded-2xl bg-white/[0.01] border border-white/5">
                <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-8 bg-cyan-500/20 rounded-full" />
                <p className="text-[13px] text-white/60 leading-relaxed italic font-medium">
                  &ldquo;{report.verdict_sentence}&rdquo;
                </p>
              </div>
            )}

            <div className="flex flex-wrap gap-4 items-center">
              <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-white/[0.03] border border-white/[0.05] text-[9px] font-black uppercase tracking-widest text-white/40">
                <Lock className="w-3 h-3 text-cyan-500/40" />
                <span>{activeAgentIds.length} Verified Nodes</span>
              </div>
              <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-white/[0.03] border border-white/[0.05] text-[9px] font-black uppercase tracking-widest text-white/40">
                <Fingerprint className="w-3 h-3 text-cyan-500/40" />
                <span>Pipeline: {pipelineDuration || "N/A"}</span>
              </div>
              {isDeepPhase && (
                <div className="px-3 py-1 rounded-full bg-violet-500/10 border border-violet-500/20 text-[9px] font-black uppercase tracking-widest text-violet-400">
                  Deep Phase Active
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Metrics Visualization */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-8 border-t border-white/5">
          <ArcGauge
            value={confPct}
            color={theme.text.replace('text-', '') === 'rose-400' ? '#f43f5e' : theme.text.replace('text-', '') === 'emerald-400' ? '#10b981' : '#f59e0b'}
            label="Confidence"
            sublabel="Arbiter Weighted"
          />
          <ArcGauge
            value={manipPct}
            color={manipPct > 60 ? "#f43f5e" : manipPct > 30 ? "#f59e0b" : "#10b981"}
            label="Manipulation"
            sublabel="Probability"
          />
          <ArcGauge
            value={errPct}
            color={errPct > 20 ? "#f43f5e" : "#10b981"}
            label="Error Rate"
            sublabel="Data Integrity"
          />
        </div>

        {/* Cryptographic Signature Footer */}
        {report.cryptographic_signature && (
          <div className="px-6 py-4 rounded-2xl bg-[#000]/20 border border-white/5 flex items-center justify-between group">
            <div className="flex items-center gap-4 min-w-0">
              <Fingerprint className="w-5 h-5 text-cyan-500/30 group-hover:text-cyan-500/60 transition-colors" />
              <div className="min-w-0">
                <p className="text-[9px] font-black uppercase tracking-[0.3em] text-white/10 mb-0.5">ECDSA P-256 Digital Signature</p>
                <p className="text-[10px] font-mono text-white/20 truncate">{report.cryptographic_signature}</p>
              </div>
            </div>
            <div className="shrink-0 text-right">
              <span className="text-[8px] font-black uppercase tracking-widest text-emerald-500/50 bg-emerald-500/5 border border-emerald-500/10 px-2 py-1 rounded">Verified integrity</span>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

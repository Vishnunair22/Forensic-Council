"use client";

import React from "react";
import { Fingerprint, ShieldCheck, ShieldAlert, Shield, type LucideIcon } from "lucide-react";
import type { ReportDTO } from "@/lib/api";
import type { VerdictConfig } from "@/lib/verdict";
import { EvidenceThumbnail } from "./EvidenceThumbnail";
import { motion } from "framer-motion";

interface ResultHeaderProps {
  report: ReportDTO;
  fileName: string;
  mimeType: string | null;
  thumbnail: string | null;
  isDeepPhase: boolean;
  vc: VerdictConfig;
  confPct: number;
  activeAgentIds: string[];
  pipelineDuration: string | null;
}

const VERDICT_THEMES: Record<string, { color: string; icon: LucideIcon }> = {
  emerald: { color: "#A7FFD2", icon: ShieldCheck },
  red:     { color: "#F43F5E", icon: ShieldAlert },
  amber:   { color: "#F59E0B", icon: Shield },
};

export function ResultHeader({
  report,
  fileName,
  mimeType,
  thumbnail,
  isDeepPhase,
  vc,
  confPct,
  activeAgentIds,
  pipelineDuration,
}: ResultHeaderProps) {
  const theme = VERDICT_THEMES[vc.color] || VERDICT_THEMES.amber;

  return (
    <section className="bg-[#070A12] border border-white/8 rounded-2xl shadow-[0_4px_24px_rgba(0,0,0,0.5),0_1px_0_rgba(255,255,255,0.04)_inset] relative overflow-hidden">
      <div className="p-8 md:p-12 space-y-12">

        {/* --- Identity & Verdict --- */}
        <div className="flex flex-col lg:flex-row gap-12 items-center lg:items-start">

          {/* Thumbnail */}
          <div className="relative w-40 h-40 shrink-0">
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 40, repeat: Infinity, ease: "linear" }}
              className="absolute inset-[-10px] rounded-full border border-[var(--color-success-light)]/10 border-dashed"
            />
            <EvidenceThumbnail
              thumbnail={thumbnail}
              mimeType={mimeType}
              fileName={fileName}
              className="w-full h-full rounded-2xl border border-white/10 shadow-2xl relative z-10"
            />
          </div>

          <div className="flex-1 flex flex-col items-center lg:items-start text-center lg:text-left">
            <div className="flex items-center gap-4 mb-4">
               <span className="text-[10px] font-mono font-bold text-[var(--color-success-light)] border border-[var(--color-success-light)]/20 px-3 py-1 rounded-full bg-[var(--color-success-light)]/5 uppercase tracking-widest">
                 ID_{typeof report.case_id === 'string' ? report.case_id.slice(-8) : "FC_ALPHA"}
               </span>
               <span className="text-[10px] font-mono text-white/20 uppercase tracking-[0.3em]">
                 {isDeepPhase ? "Deep_Forensics" : "Standard_Ingestion"}
               </span>
            </div>

            <h2 className="text-xl font-heading font-bold text-white/40 mb-2 truncate max-w-xl tracking-tight">{fileName}</h2>

            <motion.p
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="text-5xl md:text-7xl font-heading font-bold tracking-tighter text-white mb-4 leading-none"
              style={{ color: theme.color }}
            >
              {vc.label.toUpperCase()}
            </motion.p>

            <div className="space-y-3">
              <p className="text-base font-medium text-white/30 max-w-2xl leading-relaxed italic">
                {vc.desc}
              </p>
              {report.analysis_coverage_note && (
                <p className="text-[10px] font-mono font-bold text-white/20 uppercase tracking-widest">
                  {report.analysis_coverage_note}
                </p>
              )}
              {report.reliability_note && (
                <p className="text-[10px] text-white/15 italic">
                  Note: {report.reliability_note}
                </p>
              )}
            </div>
          </div>

          {/* Quick Meta */}
          <div className="flex flex-col gap-3 min-w-[200px]">
             <div className="flex items-center justify-between px-4 py-2.5 rounded-xl bg-white/[0.02] border border-white/5">
                <span className="text-[9px] font-mono text-white/20 uppercase tracking-widest">Active Nodes</span>
                <span className="text-[10px] font-mono font-bold text-white/50">{activeAgentIds.length}</span>
             </div>
             <div className="flex items-center justify-between px-4 py-2.5 rounded-xl bg-white/[0.02] border border-white/5">
                <span className="text-[9px] font-mono text-white/20 uppercase tracking-widest">Total Time</span>
                <span className="text-[10px] font-mono font-bold text-white/50">{pipelineDuration}</span>
             </div>
          </div>
        </div>

        {/* --- Confidence Bar --- */}
        <div className="space-y-4 pt-8 border-t border-white/5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <ShieldCheck className="w-3.5 h-3.5 text-[var(--color-success-light)]/40" />
              <span className="text-[10px] font-mono font-bold text-white/30 uppercase tracking-[0.2em]">Consensus Confidence</span>
            </div>
            <span className="text-xl font-mono font-bold text-white">{confPct}%</span>
          </div>
          <div className="w-full h-2 bg-white/5 rounded-full overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${confPct}%` }}
              className="h-full bg-[var(--color-success-light)] shadow-[0_0_20px_rgba(167,255,210,0.3)]"
            />
          </div>
        </div>

        {/* --- Digital Signature --- */}
        {report.cryptographic_signature && (
          <div className="p-5 rounded-xl border border-primary/10 bg-primary/[0.02] flex flex-col md:flex-row items-center justify-between gap-6">
            <div className="flex flex-col gap-1">
              <span className="text-[9px] font-mono font-bold text-primary/40 uppercase tracking-[0.2em]">ECDSA_P256_CERTIFIED</span>
              <p className="text-[10px] font-mono text-white/25 truncate max-w-[200px] md:max-w-md">
                {report.cryptographic_signature}
              </p>
            </div>

            <div className="px-3 py-1.5 rounded-full border border-success/20 bg-success/5 flex items-center gap-2">
               <Fingerprint className="w-3 h-3 text-success/60" />
               <span className="text-[9px] font-mono font-bold text-success/60 uppercase tracking-widest">Verified_Integrity</span>
            </div>
          </div>
        )}

      </div>
    </section>
  );
}

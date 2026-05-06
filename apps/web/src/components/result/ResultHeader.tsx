"use client";

import React from "react";
import {
  Fingerprint, ShieldCheck, ShieldAlert, Shield, Activity,
  ShieldX, Zap, type LucideIcon
} from "lucide-react";
import type { ReportDTO } from "@/lib/api";
import type { VerdictConfig } from "@/lib/verdict";
import { EvidenceThumbnail } from "./EvidenceThumbnail";
import { ArcGauge } from "./ArcGauge";
import { motion } from "framer-motion";

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

const VERDICT_THEMES: Record<string, { color: string; icon: LucideIcon }> = {
  emerald: { color: "#A7FFD2", icon: ShieldCheck },
  red:     { color: "#F43F5E", icon: ShieldAlert },
  amber:   { color: "#F59E0B", icon: Shield },
};

interface MetricCellProps {
  label: string;
  value: number;
  unit?: string;
  subtext: string;
  icon: LucideIcon;
  color: string;
}

function MetricCell({ label, value, unit = "%", subtext, icon: Icon, color }: MetricCellProps) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-6 px-4 group">
      <div className="flex items-center gap-2 mb-3">
        <Icon className="w-3 h-3 text-white/15 group-hover:text-white/30 transition-colors" />
        <span className="text-[9px] font-mono font-bold text-white/20 uppercase tracking-[0.2em]">{label}</span>
      </div>
      <div className="text-3xl font-mono font-bold tracking-tighter mb-2" style={{ color }}>
        {value}{unit}
      </div>
      <div className="w-full max-w-[80px] h-[3px] bg-white/5 rounded-full overflow-hidden mb-2">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${Math.min(value, 100)}%` }}
          transition={{ duration: 1.2, ease: "easeOut", delay: 0.3 }}
          className="h-full rounded-full"
          style={{ backgroundColor: color, boxShadow: `0 0 10px ${color}60` }}
        />
      </div>
      <span className="text-[9px] font-mono text-white/15 uppercase tracking-widest">{subtext}</span>
    </div>
  );
}

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

  // Derive a clean display name for the file
  const displayName = fileName.startsWith("CASE-")
    ? (report.session_id ? `Session_${report.session_id.slice(0, 8).toUpperCase()}` : "Evidence File")
    : fileName;

  return (
    <section className="bg-[#070A12] border border-white/8 rounded-2xl shadow-[0_4px_24px_rgba(0,0,0,0.5),0_1px_0_rgba(255,255,255,0.04)_inset] relative overflow-hidden">
      <div className="p-8 md:p-10">

        {/* ── Header Identity Row ─────────────────────────────────────── */}
        <div className="flex flex-col lg:flex-row gap-10 items-center lg:items-start mb-10">

          {/* Thumbnail with orbit ring */}
          <div className="relative w-36 h-36 shrink-0">
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 40, repeat: Infinity, ease: "linear" }}
              className="absolute inset-[-10px] rounded-full border border-dashed"
              style={{ borderColor: `${theme.color}20` }}
            />
            <EvidenceThumbnail
              thumbnail={thumbnail}
              mimeType={mimeType}
              fileName={fileName}
              className="w-full h-full rounded-2xl border border-white/10 shadow-2xl relative z-10"
            />
          </div>

          {/* Verdict + Identity */}
          <div className="flex-1 flex flex-col items-center lg:items-start text-center lg:text-left">
            {/* Top tags */}
            <div className="flex items-center gap-3 flex-wrap mb-4">
              <span
                className="text-[10px] font-mono font-bold border px-3 py-1 rounded-full uppercase tracking-widest"
                style={{ color: theme.color, borderColor: `${theme.color}30`, background: `${theme.color}08` }}
              >
                ID_{typeof report.case_id === "string" ? report.case_id.slice(-8).toUpperCase() : "FC_ALPHA"}
              </span>
              <span className="text-[10px] font-mono text-white/20 uppercase tracking-[0.3em]">
                {isDeepPhase ? "Deep_Forensics" : "Standard_Ingestion"}
              </span>
              <span className="text-[10px] font-mono text-white/20 uppercase tracking-[0.3em]">
                {activeAgentIds.length} Agents · {pipelineDuration}
              </span>
            </div>

            {/* File name */}
            <h2 className="text-sm font-mono font-bold text-white/30 mb-3 truncate max-w-xl tracking-tight">
              {displayName}
            </h2>

            {/* Verdict label */}
            <div className="flex items-center gap-4 mb-4">
              <VerdictIcon className="w-8 h-8 shrink-0" style={{ color: theme.color }} />
              <motion.p
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="text-5xl md:text-6xl font-heading font-bold tracking-tighter leading-none"
                style={{ color: theme.color }}
              >
                {vc.label.toUpperCase()}
              </motion.p>
            </div>

            {/* Verdict description */}
            <p className="text-sm font-medium text-white/30 max-w-2xl leading-relaxed italic mb-2">
              {vc.desc}
            </p>
            {report.analysis_coverage_note && (
              <p className="text-[10px] font-mono font-bold text-white/20 uppercase tracking-widest">
                {report.analysis_coverage_note}
              </p>
            )}
            {report.reliability_note && (
              <p className="text-[10px] text-white/15 italic mt-1">Note: {report.reliability_note}</p>
            )}
          </div>

          {/* ArcGauge — Confidence */}
          <div className="flex flex-col items-center shrink-0">
            <div className="w-28 h-28">
              <ArcGauge value={confPct} label="" sublabel="" color={theme.color} />
            </div>
            <span className="text-[9px] font-mono font-bold text-white/20 uppercase tracking-widest mt-2">Consensus</span>
            <span className="text-lg font-mono font-bold mt-1" style={{ color: theme.color }}>{confPct}%</span>
          </div>
        </div>

        {/* ── Metrics Row ─────────────────────────────────────────────── */}
        <div className="grid grid-cols-3 divide-x divide-white/5 border-t border-white/5 rounded-b-xl overflow-hidden">
          <MetricCell
            label="Integrity_Risk"
            value={manipPct}
            subtext="Manipulation Prob."
            icon={ShieldAlert}
            color={manipPct > 50 ? "#F43F5E" : "#A7FFD2"}
          />
          <MetricCell
            label="System_Noise"
            value={errPct}
            subtext="Tool Error Rate"
            icon={Zap}
            color={errPct > 20 ? "#F59E0B" : "#A7FFD2"}
          />
          <MetricCell
            label="Agent_Spread"
            value={discordPct}
            subtext="Neural Discord"
            icon={Activity}
            color="#A7FFD2"
          />
        </div>

        {/* ── Digital Signature ───────────────────────────────────────── */}
        {report.cryptographic_signature && (
          <div className="mt-6 p-4 rounded-xl border border-primary/10 bg-primary/[0.02] flex flex-col md:flex-row items-center justify-between gap-4">
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

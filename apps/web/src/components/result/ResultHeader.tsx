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
  border: "border-primary/20", 
  glow: "shadow-[0_0_40px_rgba(34,211,238,0.1)]", 
  text: "text-primary", 
  bg: "bg-primary/5",
  icon: ShieldCheck 
 },
 red: { 
  border: "border-danger/20", 
  glow: "shadow-[0_0_40px_rgba(244,63,94,0.1)]", 
  text: "text-danger", 
  bg: "bg-danger/5",
  icon: ShieldAlert 
 },
 amber: { 
  border: "border-warning/20", 
  glow: "shadow-[0_0_40px_rgba(245,158,11,0.1)]", 
  text: "text-warning", 
  bg: "bg-warning/5",
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

 // Calculate Neural Discord (Agreement vs Disagreement)
 const discordPct = report.confidence_std_dev ? Math.round(report.confidence_std_dev * 100) : 0;

 return (
  <section 
   aria-label="Forensic Verdict Summary"
   className={clsx(
    "rounded-[2.5rem] border overflow-hidden premium-glass transition-all duration-700",
    theme.border,
    theme.glow
   )}
  >
   {/* Dynamic Status Bar */}
   <div className={clsx("h-1.5 w-full bg-gradient-to-r from-transparent via-current to-transparent opacity-20", theme.text)} />

   <div className="p-10 space-y-12">
    <div className="flex flex-col items-center text-center space-y-8">
     
     {/* Enhanced Thumbnail */}
     <div className="w-32 h-32 shrink-0">
      <EvidenceThumbnail
       thumbnail={thumbnail}
       mimeType={mimeType}
       fileName={fileName}
       className="w-full h-full rounded-[2rem] border-white/5 shadow-2xl bg-white/[0.02]"
      />
     </div>

     {/* Verdict Intelligence */}
     <div className="w-full space-y-6">
      <div className="space-y-2">
       <div className="flex items-center justify-center gap-3">
         <span className="text-[10px] font-bold tracking-[0.2em] text-white/20">Case Entry</span>
         <span className="text-[10px] font-mono text-white/40">{report.case_id || "FC-DEFAULT"}</span>
       </div>
       <h2 className="text-lg font-bold text-white/50 truncate tracking-tight">{fileName}</h2>
      </div>

      <div className="flex flex-col items-center gap-5">
       <div className={clsx("w-20 h-20 rounded-[2rem] flex items-center justify-center shrink-0 border shadow-2xl transition-transform hover:scale-110 duration-500", theme.bg, theme.border)}>
        <theme.icon className={clsx("w-10 h-10", theme.text)} />
       </div>
       <div className="space-y-3">
        <p className={clsx("text-5xl sm:text-7xl font-black tracking-tighter leading-none uppercase text-glow-cyan", theme.text)}>
         {vc.label}
        </p>
        <p className="text-sm font-black text-white/50 tracking-[0.3em] uppercase">{vc.desc}</p>
       </div>
      </div>

      <div className="flex flex-wrap gap-4 items-center justify-center pt-2">
       <div className="flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/[0.02] border border-white/[0.05] text-[10px] font-bold text-white/40 transition-colors hover:bg-white/[0.04]">
        <Lock className="w-3.5 h-3.5 text-cyan-500/40" />
        <span>{activeAgentIds.length} Applicable Agents</span>
       </div>
       <div className="flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/[0.02] border border-white/[0.05] text-[10px] font-bold text-white/40 transition-colors hover:bg-white/[0.04]">
        <Fingerprint className="w-3.5 h-3.5 text-cyan-500/40" />
        <span>Pipeline: {pipelineDuration || "N/A"}</span>
       </div>
        <div className={clsx(
         "px-5 py-2 rounded-full border text-[10px] font-black tracking-[0.2em] transition-all uppercase",
         isDeepPhase ? "bg-accent/10 border-accent/20 text-accent" : "bg-primary/10 border-primary/20 text-primary"
        )}>
         {isDeepPhase ? "Deep Analysis Active" : "Initial Intake Scan"}
        </div>
        {report.compression_penalty != null && report.compression_penalty < 1.0 && (
         <div className="flex items-center gap-2 px-4 py-1.5 rounded-full bg-amber-500/10 border border-amber-500/20 text-[10px] font-bold text-amber-400 transition-colors">
          <ShieldAlert className="w-3.5 h-3.5 text-amber-500/40" />
          <span>Compression-Adjusted Verdict</span>
         </div>
        )}
      </div>
     </div>
    </div>

    {/* Metrics Row — centered flow, clear hierarchy */}
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4 pt-10 border-t border-white/5" role="group" aria-label="Analysis metrics">
     {/* Confidence — primary metric */}
     <div className="flex flex-col items-center justify-center gap-4 p-6 rounded-3xl bg-white/[0.01] border border-white/5 hover:bg-white/[0.02] transition-colors">
      <ArcGauge
       value={confPct}
       size={110}
       color={confPct >= 70 ? "#10b981" : confPct >= 40 ? "#f59e0b" : "#f43f5e"}
       label="Confidence"
       sublabel="Consensus"
      />
     </div>

     {/* Neural Discord — consensus vs disagreement */}
     <div className="flex flex-col items-center justify-center gap-4 p-6 rounded-3xl bg-white/[0.01] border border-white/5 hover:bg-white/[0.02] transition-colors">
       <div className="space-y-1 text-center">
        <span className="text-[10px] font-bold tracking-widest text-white/20">Confidence Spread</span>
        <div className={clsx(
         "text-3xl font-bold font-mono",
         discordPct > 30 ? "text-rose-400" : discordPct > 15 ? "text-amber-400" : "text-emerald-400"
        )}>{discordPct}%</div>
         <span className="text-[10px] font-bold text-cyan-400 tracking-[0.2em]">{isDeepPhase ? "Deep Analysis Complete" : "Initial Phase Complete"}</span>
       </div>
       <div className="w-16 h-1 w-full bg-white/5 rounded-full overflow-hidden">
        <div 
         className={clsx("h-full rounded-full transition-all duration-1000", discordPct > 30 ? "bg-rose-500" : "bg-cyan-500")}
         style={{ width: `${discordPct}%` }}
        />
       </div>
     </div>

     {/* Manipulation risk */}
     <div className="flex flex-col justify-center items-center gap-4 p-6 rounded-3xl bg-white/[0.01] border border-white/5 hover:bg-white/[0.02] transition-colors">
      <div className="space-y-1 text-center">
       <span className="text-[10px] font-bold tracking-widest text-white/20">Integrity Risk</span>
       <div className={clsx(
        "text-3xl font-bold font-mono",
        manipPct > 60 ? "text-rose-400" : manipPct > 30 ? "text-amber-400" : "text-emerald-400"
       )}>{manipPct}%</div>
        <span className="text-[10px] font-bold text-white/20 tracking-[0.2em]">Manipulation Probability</span>
      </div>
      <div className="h-1 w-full bg-white/5 rounded-full overflow-hidden">
       <div
        className={clsx("h-full rounded-full transition-all duration-1000",
         manipPct > 60 ? "bg-rose-500" : manipPct > 30 ? "bg-amber-500" : "bg-emerald-500"
        )}
        style={{ width: `${manipPct}%` }}
       />
      </div>
     </div>

     {/* Error rate */}
      <div className="flex flex-col justify-center items-center gap-2 p-6 premium-card rounded-3xl">
      <span className="text-[10px] font-black tracking-widest text-white/20 uppercase">System Noise</span>
      <span className={clsx(
       "text-3xl font-black font-mono",
       errPct > 20 ? "text-danger" : "text-primary"
      )}>{errPct}%</span>
      <p className="text-[10px] font-black text-white/10 tracking-[0.2em] uppercase">Error Rate</p>
     </div>
    </div>

    {/* Cryptographic Signature Footer */}
    {report.cryptographic_signature && (
     <div className="px-8 py-5 rounded-[2rem] bg-[#000]/30 border border-white/5 flex flex-col sm:flex-row items-center justify-between gap-4 group">
      <div className="flex items-center gap-4 min-w-0">
       <Fingerprint className="w-5 h-5 text-cyan-500/30 group-hover:text-cyan-500/60 transition-colors" />
       <div className="min-w-0">
        <p className="text-[10px] font-bold tracking-[0.2em] text-white/10 mb-0.5">ECDSA P-256 Digital Signature</p>
        <p className="text-[10px] font-mono text-white/20 truncate max-w-[200px] sm:max-w-md">{report.cryptographic_signature}</p>
       </div>
      </div>
      <div className="shrink-0">
       <span className="text-[10px] font-bold tracking-widest text-emerald-500/40 border border-emerald-500/10 px-3 py-1 rounded-full bg-emerald-500/5">Verified Integrity</span>
      </div>
     </div>
    )}
   </div>
  </section>
 );
}

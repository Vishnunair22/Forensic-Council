"use client";

import React from "react";
import { Lock, Fingerprint, ShieldCheck, ShieldAlert, Shield, type LucideIcon } from "lucide-react";
import type { ReportDTO } from "@/lib/api";
import type { VerdictConfig } from "@/lib/verdict";
import { ArcGauge } from "./ArcGauge";
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
  errPct: number;
  manipPct: number;
  activeAgentIds: string[];
  pipelineDuration: string | null;
}

const VERDICT_THEMES: Record<string, { color: string; icon: LucideIcon }> = {
  emerald: { color: "#00FFFF", icon: ShieldCheck },
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
  errPct,
  manipPct,
  activeAgentIds,
  pipelineDuration,
}: ResultHeaderProps) {
  const theme = VERDICT_THEMES[vc.color] || VERDICT_THEMES.amber;
  const discordPct = report.confidence_std_dev ? Math.round(report.confidence_std_dev * 100) : 0;

  return (
    <section className="horizon-card p-1 relative overflow-hidden rounded-3xl">
      <div className="bg-[#020617] rounded-[inherit] p-10 space-y-12">
        
        {/* --- Top Row: Identity & Verdict --- */}
        <div className="flex flex-col lg:flex-row gap-12 items-center">
          
          {/* Thumbnail with Aperture */}
          <div className="relative w-40 h-40 flex items-center justify-center shrink-0">
            <motion.div 
              animate={{ rotate: 360 }}
              transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
              className="absolute inset-0 rounded-full border border-primary/20 border-dashed"
            />
            <div className="absolute inset-4 rounded-full border border-primary/5" />
            <div className="w-24 h-24 relative z-10">
              <EvidenceThumbnail
                thumbnail={thumbnail}
                mimeType={mimeType}
                fileName={fileName}
                className="w-full h-full rounded-xl border border-white/10 shadow-2xl"
              />
            </div>
          </div>

          <div className="flex-1 flex flex-col items-center lg:items-start text-center lg:text-left">
            <div className="flex items-center gap-3 mb-4">
               <span className="text-[10px] font-mono font-bold text-primary border border-primary/20 px-2 py-0.5 rounded bg-primary/5">
                 CASE_{report.case_id?.slice(-8) || "FC_ALPHA"}
               </span>
               <span className="text-[10px] font-mono text-white/30 uppercase tracking-[0.2em]">
                 {isDeepPhase ? "Deep_Forensics_Active" : "Initial_Intake"}
               </span>
            </div>

            <h2 className="text-xl font-heading font-bold text-white/60 mb-2 truncate max-w-md">{fileName}</h2>
            
            <motion.p 
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="text-5xl md:text-7xl font-heading font-bold tracking-tight text-white mb-4"
              style={{ color: theme.color }}
            >
              {vc.label.toUpperCase()}
            </motion.p>
            
            <p className="text-sm font-medium text-white/40 max-w-lg italic">
              {vc.desc}
            </p>
          </div>

          {/* Quick Stats Pill */}
          <div className="flex flex-col gap-3">
             <div className="flex items-center gap-3 px-4 py-2 rounded-lg bg-white/[0.02] border border-white/5">
                <Lock className="w-3.5 h-3.5 text-primary/40" />
                <span className="text-[10px] font-mono font-bold text-white/60">{activeAgentIds.length} ACTIVE_NODES</span>
             </div>
             <div className="flex items-center gap-3 px-4 py-2 rounded-lg bg-white/[0.02] border border-white/5">
                <Fingerprint className="w-3.5 h-3.5 text-primary/40" />
                <span className="text-[10px] font-mono font-bold text-white/60">SCAN_TIME: {pipelineDuration}</span>
             </div>
          </div>
        </div>

        {/* --- Metrics Grid --- */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 pt-12 border-t border-white/5">
          <ArcGauge value={confPct} label="Consensus" sublabel="Confidence Score" color="#00FFFF" />
          
          <div className="horizon-card p-6 flex flex-col items-center justify-center text-center">
             <span className="text-[10px] font-mono font-bold text-white/30 uppercase tracking-[0.2em] mb-4">Neural_Discord</span>
             <div className="text-3xl font-mono font-bold text-white mb-2">{discordPct}%</div>
             <div className="w-full h-1 bg-white/5 rounded-full overflow-hidden">
                <motion.div 
                  initial={{ width: 0 }} animate={{ width: `${discordPct}%` }}
                  className="h-full bg-primary shadow-[0_0_10px_#00FFFF]" 
                />
             </div>
             <span className="text-[9px] font-mono text-white/20 mt-3 uppercase">Confidence Spread</span>
          </div>

          <div className="horizon-card p-6 flex flex-col items-center justify-center text-center">
             <span className="text-[10px] font-mono font-bold text-white/30 uppercase tracking-[0.2em] mb-4">Integrity_Risk</span>
             <div className="text-3xl font-mono font-bold text-white mb-2" style={{ color: manipPct > 50 ? '#F43F5E' : '#00FFFF' }}>{manipPct}%</div>
             <div className="w-full h-1 bg-white/5 rounded-full overflow-hidden">
                <motion.div 
                  initial={{ width: 0 }} animate={{ width: `${manipPct}%` }}
                  className="h-full bg-primary" 
                  style={{ backgroundColor: manipPct > 50 ? '#F43F5E' : '#00FFFF' }}
                />
             </div>
             <span className="text-[9px] font-mono text-white/20 mt-3 uppercase">Manipulation Prob.</span>
          </div>

          <div className="horizon-card p-6 flex flex-col items-center justify-center text-center">
             <span className="text-[10px] font-mono font-bold text-white/30 uppercase tracking-[0.2em] mb-4">System_Noise</span>
             <div className="text-3xl font-mono font-bold text-white mb-2" style={{ color: errPct > 20 ? '#F59E0B' : '#00FFFF' }}>{errPct}%</div>
             <div className="w-full h-1 bg-white/5 rounded-full overflow-hidden">
                <motion.div 
                  initial={{ width: 0 }} animate={{ width: `${errPct}%` }}
                  className="h-full bg-primary" 
                  style={{ backgroundColor: errPct > 20 ? '#F59E0B' : '#00FFFF' }}
                />
             </div>
             <span className="text-[9px] font-mono text-white/20 mt-3 uppercase">Error Variance</span>
          </div>
        </div>

        {/* --- Digital Signature --- */}
        {report.cryptographic_signature && (
          <div className="p-6 rounded-xl border border-primary/20 bg-primary/5 flex flex-col md:flex-row items-center justify-between gap-6 relative overflow-hidden group">
            {/* Stamp Detail */}
            <div className="absolute -right-4 -top-4 w-24 h-24 border border-primary/10 rounded-full flex items-center justify-center opacity-20">
               <Fingerprint className="w-12 h-12 text-primary" />
            </div>
            
            <div className="flex flex-col gap-1">
              <span className="text-[10px] font-mono font-bold text-primary uppercase tracking-[0.2em]">ECDSA_P256_CERTIFIED</span>
              <p className="text-[10px] font-mono text-white/40 truncate max-w-[200px] md:max-w-md">
                {report.cryptographic_signature}
              </p>
            </div>
            
            <div className="px-4 py-2 rounded-full border border-success/30 bg-success/10 flex items-center gap-2">
               <ShieldCheck className="w-3 h-3 text-success" />
               <span className="text-[10px] font-mono font-bold text-success uppercase">Verified_Integrity</span>
            </div>
          </div>
        )}

      </div>
    </section>
  );
}

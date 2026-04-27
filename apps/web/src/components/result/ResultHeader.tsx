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
  errPct,
  manipPct,
  activeAgentIds,
  pipelineDuration,
}: ResultHeaderProps) {
  const theme = VERDICT_THEMES[vc.color] || VERDICT_THEMES.amber;
  const discordPct = report.confidence_std_dev ? Math.round(report.confidence_std_dev * 100) : 0;

  return (
    <section className="glass-panel p-1 relative overflow-hidden rounded-[2.5rem] border-white/5 shadow-[0_64px_128px_rgba(0,0,0,0.6)]">
      <div className="bg-[#020203]/40 rounded-[inherit] p-12 space-y-16">
        
        {/* --- Top Row: Identity & Verdict --- */}
        <div className="flex flex-col lg:flex-row gap-16 items-center">
          
          {/* Thumbnail with Aperture */}
          <div className="relative w-48 h-48 flex items-center justify-center shrink-0">
            <motion.div 
              animate={{ rotate: 360 }}
              transition={{ duration: 30, repeat: Infinity, ease: "linear" }}
              className="absolute inset-0 rounded-full border border-[var(--color-success-light)]/20 border-dashed"
            />
            <div className="absolute inset-4 rounded-full border border-white/5" />
            <div className="w-32 h-32 relative z-10">
              <EvidenceThumbnail
                thumbnail={thumbnail}
                mimeType={mimeType}
                fileName={fileName}
                className="w-full h-full rounded-2xl border border-white/10 shadow-2xl"
              />
            </div>
          </div>

          <div className="flex-1 flex flex-col items-center lg:items-start text-center lg:text-left">
            <div className="flex items-center gap-4 mb-6">
               <span className="text-[10px] font-mono font-bold text-[var(--color-success-light)] border border-[var(--color-success-light)]/20 px-3 py-1 rounded-full bg-[var(--color-success-light)]/5 uppercase tracking-widest">
                 ID_{report.case_id?.slice(-8) || "FC_ALPHA"}
               </span>
               <span className="text-[10px] font-mono text-white/20 uppercase tracking-[0.3em]">
                 {isDeepPhase ? "Deep_Forensics" : "Standard_Ingestion"}
               </span>
            </div>

            <h2 className="text-2xl font-heading font-bold text-white/40 mb-3 truncate max-w-xl tracking-tight">{fileName}</h2>
            
            <motion.p 
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="text-6xl md:text-8xl font-heading font-bold tracking-tighter text-white mb-6 leading-none"
              style={{ color: theme.color }}
            >
              {vc.label.toUpperCase()}
            </motion.p>
            
            <p className="text-lg font-medium text-white/30 max-w-2xl leading-relaxed italic">
              {vc.desc}
            </p>
          </div>

          {/* Quick Stats Pill */}
          <div className="flex flex-col gap-4">
             <div className="flex items-center gap-4 px-6 py-3 rounded-2xl bg-white/[0.02] border border-white/5">
                <Lock className="w-4 h-4 text-[var(--color-success-light)]/40" />
                <span className="text-[10px] font-mono font-bold text-white/50 tracking-widest uppercase">{activeAgentIds.length} ACTIVE_NODES</span>
             </div>
             <div className="flex items-center gap-4 px-6 py-3 rounded-2xl bg-white/[0.02] border border-white/5">
                <Fingerprint className="w-4 h-4 text-[var(--color-success-light)]/40" />
                <span className="text-[10px] font-mono font-bold text-white/50 tracking-widest uppercase">TTL: {pipelineDuration}</span>
             </div>
          </div>
        </div>

        {/* --- Metrics Grid --- */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8 pt-16 border-t border-white/5">
          <ArcGauge value={confPct} label="Consensus" sublabel="Confidence" color="#A7FFD2" />
          
          <div className="glass-panel p-8 flex flex-col items-center justify-center text-center border-white/5">
             <span className="text-[10px] font-mono font-bold text-white/20 uppercase tracking-[0.2em] mb-6">Neural_Discord</span>
             <div className="text-4xl font-mono font-bold text-white mb-3 tracking-tighter">{discordPct}%</div>
             <div className="w-full h-1 bg-white/5 rounded-full overflow-hidden">
                <motion.div 
                  initial={{ width: 0 }} animate={{ width: `${discordPct}%` }}
                  className="h-full bg-[var(--color-success-light)] shadow-[0_0_15px_rgba(167,255,210,0.5)]" 
                />
             </div>
             <span className="text-[9px] font-mono text-white/10 mt-4 uppercase tracking-widest">Confidence Spread</span>
          </div>

          <div className="glass-panel p-8 flex flex-col items-center justify-center text-center border-white/5">
             <span className="text-[10px] font-mono font-bold text-white/20 uppercase tracking-[0.2em] mb-6">Integrity_Risk</span>
             <div className="text-4xl font-mono font-bold text-white mb-3 tracking-tighter" style={{ color: manipPct > 50 ? '#F43F5E' : '#A7FFD2' }}>{manipPct}%</div>
             <div className="w-full h-1 bg-white/5 rounded-full overflow-hidden">
                <motion.div 
                  initial={{ width: 0 }} animate={{ width: `${manipPct}%` }}
                  className="h-full" 
                  style={{ backgroundColor: manipPct > 50 ? '#F43F5E' : '#A7FFD2', boxShadow: manipPct > 50 ? '0 0 15px rgba(244,63,94,0.5)' : '0 0 15px rgba(167,255,210,0.5)' }}
                />
             </div>
             <span className="text-[9px] font-mono text-white/10 mt-4 uppercase tracking-widest">Manipulation Prob.</span>
          </div>

          <div className="glass-panel p-8 flex flex-col items-center justify-center text-center border-white/5">
             <span className="text-[10px] font-mono font-bold text-white/20 uppercase tracking-[0.2em] mb-6">System_Noise</span>
             <div className="text-4xl font-mono font-bold text-white mb-3 tracking-tighter" style={{ color: errPct > 20 ? '#F59E0B' : '#A7FFD2' }}>{errPct}%</div>
             <div className="w-full h-1 bg-white/5 rounded-full overflow-hidden">
                <motion.div 
                  initial={{ width: 0 }} animate={{ width: `${errPct}%` }}
                  className="h-full" 
                  style={{ backgroundColor: errPct > 20 ? '#F59E0B' : '#A7FFD2', boxShadow: errPct > 20 ? '0 0 15px rgba(245,158,11,0.5)' : '0 0 15px rgba(167,255,210,0.5)' }}
                />
             </div>
             <span className="text-[9px] font-mono text-white/10 mt-4 uppercase tracking-widest">Error Variance</span>
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

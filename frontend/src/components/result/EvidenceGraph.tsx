"use client";

import React from "react";
import { LinkIcon, Activity, Share2, Zap, Target } from "lucide-react";
import { ReportDTO, AgentFindingDTO } from "@/lib/api";

interface EvidenceGraphProps {
  report: ReportDTO;
}

export function EvidenceGraph({ report }: EvidenceGraphProps) {
  const confirmed = (report.cross_modal_confirmed as AgentFindingDTO[]) || [];

  if (confirmed.length === 0) return null;

  return (
    <div className="rounded-2xl overflow-hidden glass-panel border border-emerald-500/10 bg-emerald-500/[0.01] relative group">
      <div className="px-5 py-3.5 border-b border-white/[0.05] bg-white/[0.02] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <LinkIcon className="w-3.5 h-3.5 text-emerald-400" />
          <span className="text-[10px] font-bold uppercase tracking-widest text-foreground/60">
            Cross-Modal Evidence Correlation
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-[8px] font-mono font-black text-emerald-500/50 uppercase tracking-widest">
            Link Analysis ACTIVE
          </span>
        </div>
      </div>
      <div className="p-5 flex flex-col gap-4">
        {/* Node Visualization Container */}
        <div className="relative h-[240px] w-full rounded-xl bg-black/30 border border-white/[0.05] overflow-hidden flex items-center justify-center p-4">
          {/* Stylized Node Network */}
          <div className="absolute inset-0 flex flex-wrap gap-4 items-center justify-center opacity-30 select-none" aria-hidden="true">
            {Array.from({ length: 48 }).map((_, i) => (
              <div key={i} className="w-1 h-1 rounded-full bg-emerald-500/10" />
            ))}
          </div>

          <div className="relative z-10 flex flex-col md:flex-row items-center gap-8 w-full max-w-2xl justify-between px-8">
            {/* Domain Node: Source */}
            <div className="flex flex-col items-center gap-3 w-40 min-w-[160px] text-center p-4 rounded-2xl bg-white/[0.02] border border-white/[0.05] relative animate-pulse shadow-[0_0_20px_rgba(16,185,129,0.05)]">
              <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                <Activity className="w-6 h-6" />
              </div>
              <div className="space-y-1">
                <p className="text-[9px] font-black uppercase text-emerald-400 tracking-widest">
                  Source Domain
                </p>
                <p className="text-[7px] font-mono text-foreground/20 leading-tight">
                  TELEMETRY_STREAM_A
                </p>
              </div>
            </div>

            {/* Central Connection: Logic Logic Link */}
            <div className="relative flex-1 flex items-center justify-center">
              <div className="h-px w-full bg-gradient-to-r from-emerald-500/0 via-emerald-500/60 to-emerald-500/0 relative">
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 p-2.5 rounded-full bg-emerald-500/10 border border-emerald-500/40 shadow-[0_0_15px_rgba(16,185,129,0.2)]">
                  <Zap className="w-4 h-4 text-emerald-400 animate-pulse" />
                </div>
              </div>
            </div>

            {/* Domain Node: Verified Target */}
            <div className="flex flex-col items-center gap-3 w-40 min-w-[160px] text-center p-4 rounded-2xl bg-white/[0.05] border border-white/[0.1] relative">
              <div className="p-3.5 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
                <Share2 className="w-6 h-6" />
              </div>
              <div className="space-y-1">
                <p className="text-[9px] font-black uppercase text-cyan-400 tracking-widest">
                  Payload Domain
                </p>
                <p className="text-[7px] font-mono text-foreground/20 leading-tight">
                  FORENSIC_OBJECT_B
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Narrative findings */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-2">
          {confirmed.slice(0, 6).map((f, i) => (
            <div
              key={i}
              className="p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.04] space-y-2 group/item hover:bg-emerald-500/[0.03] hover:border-emerald-500/20 transition-all duration-300"
            >
              <div className="flex items-center justify-between">
                <span className="text-[8px] font-black uppercase text-emerald-400/60 tracking-tighter">
                  Correlation confirmed
                </span>
                <Target className="w-2.5 h-2.5 text-emerald-400/30 group-hover/item:text-emerald-400 transition-colors" />
              </div>
              <p className="text-[10px] text-foreground/50 leading-relaxed font-bold line-clamp-2">
                {f.reasoning_summary || f.finding_type.replace(/_/g, " ")}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

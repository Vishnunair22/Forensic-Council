"use client";

import React from "react";
import { Info, ShieldCheck, AlertTriangle } from "lucide-react";
import { clsx } from "clsx";
import type { ReportDTO } from "@/lib/api";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";

interface MetricsPanelProps {
 report: ReportDTO;
 activeAgentIds: string[];
}

function StatCard({ label, value, color, sublabel }: { label: string; value: string; color: string; sublabel?: string }) {
 return (
  <div className="p-5 rounded-2xl bg-white/[0.01] border border-white/5 space-y-2 group hover:bg-white/[0.02] transition-colors">
   <p className="text-xs font-semibold tracking-wide text-white/50 group-hover:text-white/50 transition-colors">{label}</p>
   <div className="flex items-baseline gap-2">
    <span className={clsx("text-2xl font-black font-mono tracking-tighter", color)}>
      {Number.isNaN(parseInt(value)) ? value : <><AnimatedNumber value={parseInt(value)} />{value.replace(/\d/g, "")}</>}
    </span>
    {sublabel && <span className="text-xs font-medium text-white/20 ">{sublabel}</span>}
   </div>
  </div>
 );
}

const AGENT_THEMES: Record<string, { color: string; label: string }> = {
 "Agent1": { color: "text-primary",  label: "Image Forensics" },
 "Agent2": { color: "text-blue-400",  label: "Audio Forensics" },
 "Agent3": { color: "text-amber-400", label: "Object Detection" },
 "Agent4": { color: "text-teal-400",  label: "Video Forensics" },
 "Agent5": { color: "text-violet-400", label: "Metadata Expert" },
};

export function MetricsPanel({ report, activeAgentIds }: MetricsPanelProps) {
  return (
   <section aria-label="Forensic Intelligence Metrics" className="space-y-6">
    {(report.degradation_flags ?? []).length > 0 && (
     <div className="p-4 rounded-2xl border border-amber-500/30 bg-amber-500/[0.03] flex gap-3">
      <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
      <div>
       <p className="text-[10px] font-black text-amber-400/60 tracking-wide mb-1">
        Analysis Degradation Flags
       </p>
       <ul className="space-y-1">
        {(report.degradation_flags ?? []).map((flag, i) => (
         <li key={i} className="text-[11px] text-amber-200/70">{flag}</li>
        ))}
       </ul>
      </div>
     </div>
    )}
    <div className="flex items-center gap-3 px-1">
    <h2 className="text-[10px] font-bold tracking-wide text-white/50">
     Intelligence & Key Signals
    </h2>
   </div>

   <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
    {/* Agent Confidence Matrix */}
    <div className="rounded-3xl border border-white/5 bg-white/[0.01] p-8 space-y-6 glass-panel">
     <div className="flex items-center justify-between border-b border-white/5 pb-4">
      <p className="text-[10px] font-bold text-white/20 tracking-wide">Global Consensus Profile</p>
      <h3 className="text-[11px] font-bold text-white/60 font-heading">
       Agent Confidence Matrix
      </h3>
      <span className="text-[10px] font-mono text-white/10">{activeAgentIds.length} Nodes</span>
     </div>

     <div className="space-y-5">
      {activeAgentIds.length === 0 ? (
       <p className="text-xs text-white/20 font-mono italic">No agent execution data detected.</p>
      ) : (
       activeAgentIds.map((agentId) => {
        const metrics = report.per_agent_metrics?.[agentId];
        const conf = metrics?.confidence_score ?? 0;
        const theme = AGENT_THEMES[agentId] || { color: "text-white/40", label: agentId };

        return (
         <div key={agentId} className="space-y-2 group">
          <div className="flex items-center justify-between">
           <span className={clsx("text-[10px] font-bold", theme.color)}>
            {theme.label}
           </span>
           <span className={clsx("text-[10px] font-bold font-mono tabular-nums", theme.color)}>
            {Math.round(conf * 100)}%
           </span>
          </div>
          <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
           <div
            className={clsx("h-full rounded-full transition-all duration-1000 group-hover:brightness-125", theme.color.replace('text-', 'bg-'))}
            style={{ width: `${Math.round(conf * 100)}%` }}
           />
          </div>
         </div>
        );
       })
      )}
     </div>
    </div>

    {/* Holistic Stats */}
    <div className="grid grid-cols-2 gap-4">
     <StatCard
      label="Arbiter Confidence"
      value={`${Math.round((report.overall_confidence ?? 0) * 100)}%`}
      color={(report.overall_confidence ?? 0) >= 0.75 ? "text-emerald-400" : (report.overall_confidence ?? 0) >= 0.5 ? "text-amber-400" : "text-rose-400"}
      sublabel="Weighted"
     />
     <StatCard
      label="Integrity Risk"
      value={`${Math.round((report.manipulation_probability ?? 0) * 100)}%`}
      color={(report.manipulation_probability ?? 0) >= 0.6 ? "text-rose-400" : (report.manipulation_probability ?? 0) >= 0.3 ? "text-amber-400" : "text-emerald-400"}
      sublabel="Risk"
     />
     <StatCard
      label="Analysis Error"
      value={`${Math.round((report.overall_error_rate ?? 0) * 100)}%`}
      color={(report.overall_error_rate ?? 0) >= 0.2 ? "text-rose-400" : "text-emerald-400/50"}
      sublabel="Noise"
     />
      <StatCard
       label="Active Probes"
       value={String(report.applicable_agent_count ?? activeAgentIds.length)}
       color="text-primary/80"
       sublabel="Verified"
      />
      <StatCard
       label="Agent Spread σ"
       value={`${Math.round((report.confidence_std_dev ?? 0) * 100)}%`}
       color={(report.confidence_std_dev ?? 0) > 0.2 ? "text-amber-400" : "text-emerald-400/50"}
       sublabel="Disagreement"
      />
    </div>
   </div>

   {/* Reliability & Security Notes */}
   {(report.reliability_note || report.cryptographic_signature) && (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
     {report.reliability_note && (
      <div className="p-6 rounded-2xl bg-primary/[0.02] border border-primary/10 flex gap-4">
       <Info className="w-5 h-5 text-primary/30 shrink-0" />
       <div className="space-y-1">
        <p className="text-[10px] font-bold text-primary/30">Reliability Note</p>
        <p className="text-[11px] text-white/50 leading-relaxed font-medium">{report.reliability_note}</p>
       </div>
      </div>
     )}
     {report.cryptographic_signature && (
      <div className="p-6 rounded-2xl bg-emerald-500/[0.02] border border-emerald-500/10 flex gap-4">
       <ShieldCheck className="w-5 h-5 text-emerald-400/30 shrink-0" />
       <div className="space-y-1">
        <p className="text-[10px] font-bold text-emerald-400/30">Security Protocol</p>
        <p className="text-[11px] text-white/50 leading-relaxed font-medium">This report is cryptographically signed and immutable via ECDSA P-256 protocol.</p>
       </div>
      </div>
     )}
    </div>
   )}
  </section>
 );
}

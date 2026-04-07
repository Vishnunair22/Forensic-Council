"use client";

import React from "react";
import { BarChart2, Hash, AlertCircle, Info, ShieldCheck } from "lucide-react";
import { clsx } from "clsx";
import type { ReportDTO } from "@/lib/api";

interface MetricsPanelProps {
  report: ReportDTO;
  activeAgentIds: string[];
  keyFindings: string[];
}

function StatCard({ label, value, color, sublabel }: { label: string; value: string; color: string; sublabel?: string }) {
  return (
    <div className="p-5 rounded-2xl bg-white/[0.01] border border-white/5 space-y-2 group hover:bg-white/[0.02] transition-colors">
      <p className="text-[9px] font-black uppercase tracking-[0.2em] text-white/20 group-hover:text-white/40 transition-colors">{label}</p>
      <div className="flex items-baseline gap-2">
        <span className={clsx("text-2xl font-black font-mono tracking-tighter", color)}>{value}</span>
        {sublabel && <span className="text-[10px] font-bold text-white/10 uppercase">{sublabel}</span>}
      </div>
    </div>
  );
}

const AGENT_THEMES: Record<string, { color: string; label: string }> = {
  Agent1: { color: "text-cyan-400", label: "Visual" },
  Agent2: { color: "text-blue-400", label: "Acoustic" },
  Agent3: { color: "text-amber-400", label: "Context" },
  Agent4: { color: "text-teal-400", label: "Temporal" },
  Agent5: { color: "text-violet-400", label: "Metadata" },
};

export function MetricsPanel({ report, activeAgentIds, keyFindings }: MetricsPanelProps) {
  return (
    <section aria-label="Forensic Intelligence Metrics" className="space-y-6">
      <div className="flex items-center gap-3 px-1">
        <BarChart2 className="w-4 h-4 text-white/20" />
        <h2 className="text-[10px] font-black font-mono uppercase tracking-[0.3em] text-white/30">
          Intelligence & Key Signals
        </h2>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Agent Confidence Matrix */}
        <div className="rounded-3xl border border-white/5 bg-white/[0.01] p-8 space-y-6 glass-panel">
          <div className="flex items-center justify-between border-b border-white/5 pb-4">
            <h3 className="text-[11px] font-black uppercase tracking-widest text-white/60 font-heading">
              Agent Confidence Matrix
            </h3>
            <span className="text-[9px] font-mono text-white/10 font-black uppercase">{activeAgentIds.length} Nodes</span>
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
                      <span className={clsx("text-[10px] font-black uppercase tracking-widest", theme.color)}>
                        {theme.label}
                      </span>
                      <span className={clsx("text-[10px] font-black font-mono tabular-nums", theme.color)}>
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
            color="text-cyan-400/80"
            sublabel="Verified"
          />
        </div>
      </div>

      {/* Key Findings Section */}
      {keyFindings.length > 0 && (
        <div className="rounded-3xl border border-white/5 bg-white/[0.01] p-8 glass-panel space-y-6">
          <div className="flex items-center gap-3 border-b border-white/5 pb-4">
            <Hash className="w-4 h-4 text-amber-500/50" />
            <h3 className="text-[11px] font-black uppercase tracking-widest text-white/60 font-heading">
              Intelligence Briefing
            </h3>
          </div>
          <ul className="space-y-4">
            {keyFindings.map((finding, i) => (
              <li key={i} className="flex items-start gap-4 p-4 rounded-2xl bg-white/[0.02] border border-white/5 group hover:border-amber-500/10 transition-colors">
                <AlertCircle className="w-4 h-4 text-amber-500/40 shrink-0 mt-0.5 group-hover:text-amber-500/70 transition-colors" />
                <p className="text-[13px] text-white/70 leading-relaxed font-medium">
                  {finding}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Reliability & Security Notes */}
      {(report.reliability_note || report.cryptographic_signature) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {report.reliability_note && (
            <div className="p-6 rounded-2xl bg-cyan-500/[0.02] border border-cyan-500/10 flex gap-4">
              <Info className="w-5 h-5 text-cyan-400/30 shrink-0" />
              <div className="space-y-1">
                <p className="text-[9px] font-black uppercase tracking-widest text-cyan-400/30">Reliability Note</p>
                <p className="text-[11px] text-white/50 leading-relaxed font-medium">{report.reliability_note}</p>
              </div>
            </div>
          )}
          {report.cryptographic_signature && (
            <div className="p-6 rounded-2xl bg-emerald-500/[0.02] border border-emerald-500/10 flex gap-4">
              <ShieldCheck className="w-5 h-5 text-emerald-400/30 shrink-0" />
              <div className="space-y-1">
                <p className="text-[9px] font-black uppercase tracking-widest text-emerald-400/30">Security Protocol</p>
                <p className="text-[11px] text-white/50 leading-relaxed font-medium">This report is cryptographically signed and immutable via ECDSA P-256 protocol.</p>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

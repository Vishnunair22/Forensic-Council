"use client";

import React, { useState, useMemo } from "react";
import { 
  ChevronDown, 
  Clock, 
  Activity, 
  Cpu, 
  ShieldCheck, 
  ShieldAlert, 
  Shield, 
  ShieldX,
  Plus
} from "lucide-react";
import { clsx } from "clsx";
import { Badge } from "@/components/ui/Badge";
import { AgentFindingDTO, AgentMetricsDTO } from "@/lib/api";
import { 
  ConfidenceBar, 
  ToolRow, 
  MoreFindingsToggle 
} from "@/components/result/AgentFindingSubComponents";

export interface AgentFindingCardProps {
  agentId: string;
  initialFindings: AgentFindingDTO[];
  deepFindings: AgentFindingDTO[];
  metrics?: AgentMetricsDTO;
  narrative?: string;
  phase?: "initial" | "deep";
  defaultOpen?: boolean;
}

const AGENT_META: Record<string, { name: string; role: string; color: string; icon: any }> = {
  Agent1: { name: "Agent 01", role: "Visual Integrity", color: "cyan", icon: ShieldCheck },
  Agent2: { name: "Agent 02", role: "Acoustic Forensic", color: "blue", icon: Activity },
  Agent3: { name: "Agent 03", role: "Contextual Analysis", color: "amber", icon: Shield },
  Agent4: { name: "Agent 04", role: "Temporal Analysis", color: "teal", icon: ShieldAlert },
  Agent5: { name: "Agent 05", role: "Metadata Expert", color: "violet", icon: Cpu },
};

const COLOR_MAP: Record<string, { bg: string; border: string; text: string; glow: string }> = {
  cyan: { bg: "bg-cyan-500/5", border: "border-cyan-500/20", text: "text-cyan-400", glow: "shadow-[0_0_30px_rgba(34,211,238,0.1)]" },
  blue: { bg: "bg-blue-500/5", border: "border-blue-500/20", text: "text-blue-400", glow: "shadow-[0_0_30px_rgba(59,130,246,0.1)]" },
  amber: { bg: "bg-amber-500/5", border: "border-amber-500/20", text: "text-amber-400", glow: "shadow-[0_0_30px_rgba(245,158,11,0.1)]" },
  teal: { bg: "bg-teal-500/5", border: "border-teal-500/20", text: "text-teal-400", glow: "shadow-[0_0_30px_rgba(45,212,191,0.1)]" },
  violet: { bg: "bg-violet-500/5", border: "border-violet-500/20", text: "text-violet-400", glow: "shadow-[0_0_30px_rgba(139,92,246,0.1)]" },
};

export function AgentFindingCard({
  agentId,
  initialFindings,
  deepFindings,
  metrics,
  narrative,
  phase = "initial",
  defaultOpen = false,
}: AgentFindingCardProps) {
  const [open, setOpen] = useState(defaultOpen);
  const meta = AGENT_META[agentId] || { name: agentId, role: "Unknown", color: "cyan", icon: ShieldX };
  const theme = COLOR_MAP[meta.color];

  const findings = phase === "deep" ? deepFindings : initialFindings;
  const SKIP_TYPES = new Set(["file type not applicable", "format not supported"]);
  const realFindings = findings.filter(f => !SKIP_TYPES.has(String(f.finding_type).toLowerCase()));

  const isSkipped = realFindings.length === 0 && findings.some(f => SKIP_TYPES.has(String(f.finding_type).toLowerCase()));
  const confidence = metrics?.confidence_score ?? 0;
  
  const totalTimingMs = useMemo(() => {
    return realFindings.reduce((acc, f) => acc + ((f.metadata?.execution_time_ms as number) || 0), 0);
  }, [realFindings]);

  if (isSkipped) {
    return (
      <div className="rounded-3xl p-6 border border-white/[0.03] bg-white/[0.01] opacity-30 flex items-center justify-between group grayscale hover:grayscale-0 transition-all duration-700">
        <div className="flex items-center gap-4">
          <div className="w-11 h-11 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center">
            <meta.icon className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-xs font-black uppercase text-white/50 tracking-widest">{meta.name}</h3>
            <p className="text-[10px] font-mono font-bold text-white/20 uppercase mt-0.5">{meta.role} · Protocol Skip</p>
          </div>
        </div>
        <span className="text-[9px] font-black uppercase tracking-widest text-white/10 px-3 py-1 rounded-full border border-white/5">Not Applicable</span>
      </div>
    );
  }

  return (
    <div className={clsx(
      "rounded-3xl overflow-hidden glass-panel border transition-all duration-500",
      open ? "border-white/10 shadow-[0_32px_64px_rgba(0,0,0,0.4)]" : "border-white/5 shadow-none"
    )}>
      {/* Header Button */}
      <button
        onClick={() => setOpen(!open)}
        className={clsx(
          "w-full p-6 text-left transition-all relative overflow-hidden group",
          open ? "bg-white/[0.04]" : "hover:bg-white/[0.02]"
        )}
        aria-expanded={open}
        aria-controls={`agent-content-${agentId}`}
      >
        <div className="flex items-start justify-between gap-6 relative z-10">
          <div className="flex items-center gap-5">
            <div className={clsx(
              "w-14 h-14 rounded-2xl flex items-center justify-center shrink-0 border transition-transform duration-500",
              theme.bg, theme.border, theme.text, open && "scale-105"
            )}>
              <meta.icon className="w-7 h-7" />
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-black text-white uppercase font-heading tracking-tight">{meta.name}</h3>
                <span className="text-[10px] text-white/20 font-bold uppercase tracking-widest truncate max-w-[120px]">{meta.role}</span>
              </div>
              <p className="text-[11px] font-mono font-bold text-white/30 truncate flex items-center gap-2">
                {realFindings.length} Active Probe{realFindings.length > 1 ? 's' : ''} 
                <span className="text-white/10">·</span>
                <Clock className="w-3 h-3" /> {totalTimingMs >= 1000 ? `${(totalTimingMs/1000).toFixed(1)}s` : `${totalTimingMs}ms`}
              </p>
            </div>
          </div>

          <div className="flex flex-col items-end gap-3 text-right">
            <ConfidenceBar value={confidence} />
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="text-[9px] font-black uppercase tracking-widest border-white/5 px-3 py-0">
                {phase === 'deep' ? 'DeepPass' : 'IntakeScan'}
              </Badge>
              <div className={clsx(
                "p-2 rounded-xl border transition-all duration-500",
                open ? "bg-cyan-500/10 border-cyan-500/30 text-cyan-400 rotate-180" : "bg-white/5 border-white/10 text-white/20"
              )}>
                <ChevronDown className="w-4 h-4" />
              </div>
            </div>
          </div>
        </div>
      </button>

      {/* Expandable Content */}
      <div 
        id={`agent-content-${agentId}`}
        className={clsx(
          "grid transition-all duration-500 ease-in-out",
          open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
        )}
      >
        <div className="overflow-hidden">
          <div className="p-8 pt-2 space-y-8 animate-in fade-in slide-in-from-top-4 duration-700">
            {/* Narrative Summary */}
            {narrative && (
              <div className="relative p-6 rounded-2xl bg-[#000]/30 border border-white/5 group">
                <div className="flex items-center gap-2 mb-4">
                  <Activity className="w-3.5 h-3.5 text-cyan-400/50" />
                  <span className="text-[9px] font-black uppercase tracking-[0.3em] text-white/20">Agent Synthesis Report</span>
                </div>
                <p className="text-[13px] text-white/80 leading-relaxed font-medium">
                  "{narrative}"
                </p>
              </div>
            )}

            {/* Findings List */}
            <div className="space-y-4">
              <div className="flex items-center justify-between border-b border-white/5 pb-2">
                <div className="flex items-center gap-2">
                  <Cpu className="w-3 h-3 text-white/20" />
                  <span className="text-[10px] font-black uppercase tracking-widest text-white/20">Signal Timeline</span>
                </div>
                <span className="text-[9px] font-mono text-white/10 uppercase font-black">{realFindings.length} Total Signals</span>
              </div>
              
              <div className="rounded-2xl border border-white/[0.04] bg-white/[0.01] overflow-hidden">
                {realFindings.slice(0, 4).map((f, i) => (
                  <ToolRow key={i} finding={f} isLast={i === realFindings.length - 1 || i === 3} />
                ))}
                
                {realFindings.length > 4 && (
                  <MoreFindingsToggle findings={realFindings.slice(4)} count={realFindings.length - 4} />
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

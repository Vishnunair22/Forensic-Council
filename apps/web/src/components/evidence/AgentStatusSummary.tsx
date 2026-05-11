"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronRight, SkipForward, Activity, type LucideIcon, ScanEye, AudioWaveform, Boxes, Film, Database } from "lucide-react";
import { clsx } from "clsx";
import type { AgentUpdate } from "./AgentProgressDisplay";

const AGENT_GRAPHICS: Record<string, { icon: LucideIcon; color: string }> = {
  "Agent1": { icon: ScanEye,       color: "text-[#60A5FA]" },
  "Agent2": { icon: AudioWaveform, color: "text-[#38BDF8]" },
  "Agent3": { icon: Boxes,         color: "text-[#818CF8]" },
  "Agent4": { icon: Film,          color: "text-[#22D3EE]" },
  "Agent5": { icon: Database,      color: "text-[#93C5FD]" },
};

interface AgentStatusSummaryProps {
  visibleAgents: Array<{ id: string; name: string }>;
  skippedAgents: Array<{ id: string; name: string }>;
  agentUpdates: Record<string, { status: string }>;
  completedAgents: AgentUpdate[];
}

export function AgentStatusSummary({
  visibleAgents,
  skippedAgents,
  agentUpdates,
  completedAgents,
}: AgentStatusSummaryProps) {
  const [activeExpanded, setActiveExpanded] = useState(false);
  const [skippedExpanded, setSkippedExpanded] = useState(false);

  const getAgentStatus = (agentId: string) => {
    const completed = completedAgents?.find((c) => c.agent_id === agentId);
    if (completed) {
      if (completed.status === "error" || completed.status === "failed") return "error";
      return "complete";
    }
    const liveStatus = agentUpdates[agentId]?.status;
    if (liveStatus === "error" || liveStatus === "failed") return "error";
    if (liveStatus === "running") return "running";
    if (agentUpdates[agentId]) return "running";
    return "waiting";
  };

  const getStatusDot = (status: string) => {
    switch (status) {
      case "running":  return "bg-primary animate-pulse";
      case "complete": return "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]";
      case "error":    return "bg-red-500";
      default:         return "bg-white/10";
    }
  };

  return (
    <div className="rounded-2xl overflow-hidden min-w-[200px] max-w-[260px]" style={{ background: "rgba(5,9,18,0.95)", border: "1px solid rgba(165,200,255,0.08)", boxShadow: "0 8px 28px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.03)" }}>

      {/* Active specialists row */}
      <button
        type="button"
        onClick={() => setActiveExpanded((v) => !v)}
        className="flex items-center justify-between w-full px-5 py-4 hover:bg-white/[0.02] transition-colors group"
      >
        <div className="flex items-center gap-3">
          <Activity className="w-3.5 h-3.5 text-primary group-hover:scale-110 transition-transform shrink-0" />
          <span className="text-[10px] font-mono font-bold text-white uppercase tracking-[0.18em]">
            Active Specialists
          </span>
        </div>
        <div className="flex items-center gap-2.5">
          <span className="text-[10px] font-mono font-bold text-white/35">({visibleAgents.length})</span>
          <motion.div animate={{ rotate: activeExpanded ? 90 : 0 }} transition={{ duration: 0.2 }}>
            <ChevronRight className="w-3.5 h-3.5 text-white/30" />
          </motion.div>
        </div>
      </button>

      <AnimatePresence initial={false}>
        {activeExpanded && (
          <motion.div
            key="active-list"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22 }}
            className="overflow-hidden"
          >
            <div className="pb-3 px-2 flex flex-col gap-0.5">
              {visibleAgents.map((agent) => {
                const graphic = AGENT_GRAPHICS[agent.id];
                const status = getAgentStatus(agent.id);
                const Icon = graphic?.icon || Activity;
                return (
                  <div key={agent.id} className="flex items-center justify-between gap-3 pl-4 pr-3 py-2 hover:bg-white/[0.02] rounded-lg transition-colors">
                    <div className="flex items-center gap-3 min-w-0">
                      <Icon className={clsx("w-3.5 h-3.5 shrink-0", graphic?.color || "text-white/40")} />
                      <span className="text-[11px] font-medium text-white/70 truncate">{agent.name}</span>
                    </div>
                    <div className={clsx("w-1.5 h-1.5 rounded-full shrink-0 transition-colors duration-500", getStatusDot(status))} />
                  </div>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Skipped specialists row — only rendered when there are skipped agents */}
      {skippedAgents.length > 0 && (
        <>
          <div className="mx-5 h-px bg-white/[0.06]" />

          <button
            type="button"
            onClick={() => setSkippedExpanded((v) => !v)}
            className="flex items-center justify-between w-full px-5 py-4 hover:bg-white/[0.02] transition-colors group"
          >
            <div className="flex items-center gap-3">
              <SkipForward className="w-3.5 h-3.5 text-white/40 group-hover:scale-110 transition-transform shrink-0" />
              <span className="text-[10px] font-mono font-bold text-white/50 uppercase tracking-[0.18em]">
                Skipped
              </span>
            </div>
            <div className="flex items-center gap-2.5">
              <span className="text-[10px] font-mono font-bold text-white/35">({skippedAgents.length})</span>
              <motion.div animate={{ rotate: skippedExpanded ? 90 : 0 }} transition={{ duration: 0.2 }}>
                <ChevronRight className="w-3.5 h-3.5 text-white/30" />
              </motion.div>
            </div>
          </button>

          <AnimatePresence initial={false}>
            {skippedExpanded && (
              <motion.div
                key="skipped-list"
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.22 }}
                className="overflow-hidden"
              >
                <div className="pb-3 px-2 flex flex-col gap-0.5">
                  {skippedAgents.map((agent) => {
                    const graphic = AGENT_GRAPHICS[agent.id];
                    const Icon = graphic?.icon || SkipForward;
                    return (
                      <div key={agent.id} className="flex items-center gap-3 pl-4 py-2">
                        <Icon className={clsx("w-3.5 h-3.5 shrink-0 opacity-40", graphic?.color || "text-white/40")} />
                        <span className="text-[11px] font-medium text-white/45 truncate">{agent.name}</span>
                      </div>
                    );
                  })}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </>
      )}
    </div>
  );
}

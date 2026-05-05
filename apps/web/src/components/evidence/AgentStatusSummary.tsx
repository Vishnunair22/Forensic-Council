"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronRight, SkipForward, Activity, type LucideIcon, ScanEye, AudioWaveform, Boxes, Film, Database } from "lucide-react";
import { clsx } from "clsx";
import type { AgentUpdate } from "./AgentProgressDisplay";

const AGENT_GRAPHICS: Record<string, { icon: LucideIcon; color: string }> = {
  "Agent1": { icon: ScanEye,      color: "text-[#60A5FA]" },
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
  const [activeExpanded, setActiveExpanded] = useState(true);
  const [skippedExpanded, setSkippedExpanded] = useState(false);

  const getAgentStatus = (agentId: string) => {
    const completed = completedAgents.find((c) => c.agent_id === agentId);
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

  const getStatusColor = (status: string) => {
    switch (status) {
      case "running": return "bg-primary animate-pulse";
      case "complete": return "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]";
      case "error": return "bg-red-500";
      default: return "bg-white/10";
    }
  };

  return (
    <div className="w-full flex flex-col gap-3">
      <div className="bg-[#070A12] border border-white/8 rounded-2xl overflow-hidden shadow-xl">
        {/* Active Agents Section */}
        <div className="flex flex-col">
          <button
            onClick={() => setActiveExpanded(!activeExpanded)}
            className="flex items-center justify-between w-full px-5 py-4 hover:bg-white/[0.02] transition-colors group"
          >
            <div className="flex items-center gap-3">
              <Activity className="w-3.5 h-3.5 text-primary group-hover:scale-110 transition-transform" />
              <span className="text-[10px] font-mono font-bold text-white uppercase tracking-[0.2em]">
                Forensic Specialists
              </span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-[10px] font-mono font-bold text-white/30">({visibleAgents.length})</span>
              <motion.div animate={{ rotate: activeExpanded ? 90 : 0 }} transition={{ duration: 0.2 }}>
                <ChevronRight className="w-3.5 h-3.5 text-white/20" />
              </motion.div>
            </div>
          </button>

          <AnimatePresence>
            {activeExpanded && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
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
                          <span className="text-[11px] font-medium text-white/70 truncate">
                            {agent.name}
                          </span>
                        </div>
                        <div className={clsx("w-1.5 h-1.5 rounded-full shrink-0 transition-colors duration-500", getStatusColor(status))} />
                      </div>
                    );
                  })}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Skipped Agents Section */}
        {skippedAgents.length > 0 && (
          <div className="flex flex-col border-t border-white/5">
            <button
              onClick={() => setSkippedExpanded(!skippedExpanded)}
              className="flex items-center justify-between w-full px-5 py-4 hover:bg-white/[0.02] transition-colors group"
            >
              <div className="flex items-center gap-3">
                <SkipForward className="w-3.5 h-3.5 text-white/30 group-hover:scale-110 transition-transform" />
                <span className="text-[10px] font-mono font-bold text-white/30 uppercase tracking-[0.2em]">
                  Skipped Specialists
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-[10px] font-mono font-bold text-white/10">({skippedAgents.length})</span>
                <motion.div animate={{ rotate: skippedExpanded ? 90 : 0 }} transition={{ duration: 0.2 }}>
                  <ChevronRight className="w-3.5 h-3.5 text-white/10" />
                </motion.div>
              </div>
            </button>

            <AnimatePresence>
              {skippedExpanded && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden"
                >
                  <div className="pb-3 px-2 flex flex-col gap-0.5 opacity-40">
                    {skippedAgents.map((agent) => {
                      const graphic = AGENT_GRAPHICS[agent.id];
                      const Icon = graphic?.icon || SkipForward;
                      return (
                        <div key={agent.id} className="flex items-center gap-3 pl-4 py-2">
                          <Icon className={clsx("w-3.5 h-3.5 shrink-0", graphic?.color || "text-white/40")} />
                          <span className="text-[11px] font-medium text-white/60 truncate">
                            {agent.name}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>
    </div>
  );
}

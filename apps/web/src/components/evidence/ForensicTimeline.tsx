"use client";

import React, { useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
 History,
 BadgeCheck,
 Search,
 Zap,
 Clock
} from "lucide-react";
import { clsx } from "clsx";
import { fmtTool } from "@/lib/fmtTool";
import { getToolIcon } from "@/lib/tool-icons";
import type { AgentUpdate } from "./AgentProgressDisplay";
import { AGENTS as AGENTS_DATA } from "@/lib/constants";

interface ForensicTimelineProps {
 completedAgents: AgentUpdate[];
 agentUpdates: Record<string, { status: string; thinking: string }>;
 isInitializing?: boolean;
}

export function ForensicTimeline({
 completedAgents,
 agentUpdates: _agentUpdates,
 isInitializing
}: ForensicTimelineProps) {

 // Aggregate all findings across all agents
 const allFindings = useMemo(() => {
  const list: Array<{
   agentId: string;
   agentName: string;
   tool: string;
   summary: string;
   verdict?: string;
   severity?: string;
   timestamp: number;
  }> = [];

  completedAgents.forEach(agent => {
   const aData = AGENTS_DATA.find(a => a.id === agent.agent_id);
   if (agent.findings_preview) {
    agent.findings_preview.forEach(finding => {
     list.push({
      agentId: agent.agent_id,
      agentName: aData?.name || agent.agent_id,
      tool: finding.tool,
      summary: finding.summary,
      verdict: finding.verdict,
      severity: finding.severity,
      // Use approximate completion time if available
      timestamp: agent.completed_at ? new Date(agent.completed_at).getTime() : Date.now()
     });
    });
   }
  });

  // Sort by timestamp (latest first for a ticker/feed feel, or oldest first for a timeline)
  return list.sort((a, b) => b.timestamp - a.timestamp);
 }, [completedAgents]);

  const ALERT_VERDICTS = new Set(["FLAGGED", "SUSPICIOUS", "LIKELY_MANIPULATED", "NEEDS_REVIEW"]);
  const flaggedFindings = allFindings.filter(f => ALERT_VERDICTS.has(f.verdict ?? "") || f.severity === "CRITICAL" || f.severity === "HIGH");

 return (
  <div className="w-full h-full flex flex-col gap-6">
   {/* Interactive Header */}
   <div className="flex items-center justify-between">
    <div className="flex items-center gap-3">
     <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center border border-primary/20">
      <History className="w-4 h-4 text-primary" />
     </div>
     <div>
      <h4 className="text-xs font-black tracking-wide text-white/50 leading-none mb-1">Evidence Ledger</h4>
      <span className="text-[10px] font-mono text-white/20 tracking-tighter">Real-time Forensic Feed</span>
     </div>
    </div>

    <div className="flex gap-2 items-center">
       <motion.div
        animate={{ opacity: [0.4, 1, 0.4] }}
        transition={{ duration: 2, repeat: Infinity }}
        className="px-2 py-0.5 rounded-full bg-primary/10 border border-primary/30 text-primary text-[10px] font-black tracking-wide flex items-center gap-1.5"
       >
        <span className="w-1.5 h-1.5 rounded-full bg-primary" />
        Live Feed
       </motion.div>
      <div className="px-2 py-0.5 rounded-full bg-rose-500/10 border border-rose-500/20 text-rose-400 text-[10px] font-black ">
       {flaggedFindings.length} Alerts
      </div>
    </div>
   </div>

   {/* Timeline List */}
    <div
     className="flex-1 overflow-y-auto custom-scrollbar relative pr-2"
     role="log"
     aria-label="Forensic evidence feed"
     aria-live="polite"
     aria-relevant="additions"
    >
    <div className="absolute left-[15px] top-0 bottom-0 w-[1px] bg-gradient-to-b from-primary/20 via-white/5 to-transparent z-0" />

    <div className="space-y-6 relative z-10">
     <AnimatePresence mode="popLayout">
      {isInitializing && (
       <motion.div
        initial={{ opacity: 0, x: -10 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, scale: 0.9 }}
        className="flex items-start gap-4"
       >
        <div className="w-8 h-8 rounded-full bg-primary/10 border border-primary/30 flex items-center justify-center shrink-0">
         <Clock className="w-4 h-4 text-primary animate-spin" />
        </div>
        <div className="flex-1 pt-1.5 min-w-0">
          <p className="text-[11px] font-mono text-primary leading-relaxed font-black tracking-wide">
           Establishing Secure Pipe
          </p>
          <span className="text-[10px] text-white/20 ">Awaiting Stream Initialization</span>
        </div>
       </motion.div>
      )}

      {allFindings.length > 0 ? (
       allFindings.map((finding, idx) => {
        const ToolIcon = getToolIcon(finding.tool);
         const ALERT_VERDICTS_RENDER = new Set(["FLAGGED", "SUSPICIOUS", "LIKELY_MANIPULATED", "NEEDS_REVIEW"]);
         const isAlert = ALERT_VERDICTS_RENDER.has(finding.verdict ?? "") || finding.severity === "CRITICAL" || finding.severity === "HIGH";

        return (
         <motion.div
          layout
          initial={{ opacity: 0, x: -20, scale: 0.95 }}
          animate={{ opacity: 1, x: 0, scale: 1 }}
          key={`${finding.agentId}-${finding.tool}-${idx}`}
          className="flex items-start gap-4"
         >
          <div
           className={clsx(
            "rounded-xl p-3 border flex items-start gap-3 group hover:bg-white/[0.04] transition-colors relative overflow-hidden",
            isAlert ? "bg-rose-500/5 border-rose-500/20" : "bg-white/[0.02] border-white/5"
           )}
          >
           {/* New item highlight sweep */}
           <motion.div
            initial={{ left: "-100%" }}
            animate={{ left: "100%" }}
            transition={{ duration: 1, ease: "easeInOut" }}
            className="absolute inset-0 bg-gradient-to-r from-transparent via-white/5 to-transparent z-0 pointer-events-none"
           />

           <div className={clsx(
            "w-7 h-7 rounded-lg flex items-center justify-center border shrink-0 relative z-10",
            isAlert ? "bg-rose-500/20 border-rose-500/30 text-rose-400 shadow-[0_0_10px_rgba(244,63,94,0.2)]" : "bg-white/5 border-white/10 text-white/50"
           )}>
            <ToolIcon className="w-3.5 h-3.5" />
           </div>
            <div className="flex-1 min-w-0 relative z-10">
              <div className="flex justify-between items-start gap-2 mb-0.5">
               <div className="flex flex-col min-w-0">
                <span className={clsx(
                 "text-[10px] font-black tracking-wider truncate transition-colors",
                 isAlert ? "text-rose-300" : "text-white/70 group-hover:text-white"
                )}>
                  {fmtTool(finding.tool)}
                </span>
                <span className="text-[10px] text-white/20 tracking-wide">
                  {finding.agentName}
                </span>
               </div>
               <BadgeCheck className={clsx("w-3.5 h-3.5 shrink-0", isAlert ? "text-rose-400" : "text-emerald-400/40")} />
              </div>

            <p className={clsx(
             "text-[11px] font-medium leading-relaxed",
             isAlert ? "text-rose-300" : "text-white/60"
            )}>
             {finding.summary}
            </p>
           </div>
          </div>
         </motion.div>
        );
       })
      ) : !isInitializing && (
       <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="flex flex-col items-center justify-center py-20 text-center gap-4 opacity-20"
       >
        <Search className="w-10 h-10" />
        <p className="text-[10px] font-black tracking-wide">No Intelligence Logged</p>
       </motion.div>
      )}
     </AnimatePresence>
    </div>
   </div>

   {/* Footer Stats */}
   <div className="mt-auto border-t border-white/5 pt-4 flex items-center justify-between">
     <div className="flex items-center gap-1.5">
      <Zap className="w-3 h-3 text-primary" />
      <span className="text-[10px] font-black tracking-wide text-white/20">Live Intelligence Feed</span>
     </div>
     <span className="text-xs font-mono text-white/30 font-semibold tracking-wide">
      Total Signals: {allFindings.length.toString().padStart(3, '0')}
     </span>
   </div>
  </div>
 );
}

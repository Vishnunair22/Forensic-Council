"use client";

import React, { useState, useEffect } from "react";
import {
 Loader2,
 FileText,
 ArrowRight,
 Microscope,
 RotateCcw,
 CheckCircle2,
 Activity,
 Ban,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import dynamic from "next/dynamic";
import { AGENTS as AGENTS_DATA } from "@/lib/constants";
import { SoundType } from "@/hooks/useSound";

export interface FindingPreview {
 tool: string;
 summary: string;
 confidence?: number | null;
 flag?: string;
 severity?: string;
 verdict?: string;
 key_signal?: string;
 section?: string;
 elapsed_s?: number | null;
 degraded?: boolean | null;
 fallback_reason?: string | null;
}

export interface AgentUpdate {
 agent_id: string;
 agent_name: string;
 message: string;
 status: "running" | "complete" | "skipped" | "error" | "failed";
 confidence: number;
 findings_count: number;
 error?: string;
 deep_analysis_pending?: boolean;
 agent_verdict?: "AUTHENTIC" | "INCONCLUSIVE" | "LIKELY_MANIPULATED" | "LIKELY_AI_GENERATED" | "LIKELY_SPOOFED" | "LIKELY_SYNTHETIC";
 tool_error_rate?: number;
 section_flags?: Array<{ id: string; label: string; flag: string; key_signal?: string }>;
 findings_preview?: FindingPreview[];
 tools_ran?: number;
 tools_skipped?: number;
 tools_failed?: number;
 verdict_score?: number;
 degraded?: boolean;
 fallback_reason?: string;
 completed_at?: string;
}

interface AgentProgressDisplayProps {
 agentUpdates: Record<
  string,
  {
   status: string;
   thinking: string;
   tools_done?: number;
   tools_total?: number;
   tool_name?: string;
  }
 >;
 completedAgents: AgentUpdate[];
 progressText: string;
 allAgentsDone: boolean;
 phase: "initial" | "deep";
 awaitingDecision: boolean;
 pipelineStatus?: string;
 pipelineMessage?: string;
 onAcceptAnalysis?: () => void;
 onDeepAnalysis?: () => void;
 onNewUpload?: () => void;
 onViewResults?: () => void;
 playSound?: (type: SoundType) => void;
 isNavigating?: boolean;
 mimeType?: string;
}

const AgentStatusCard = dynamic(
  () => import("./AgentStatusCard").then((m) => m.AgentStatusCard),
  { ssr: false },
);

const allValidAgents = AGENTS_DATA.filter((agent) => agent.id !== "AGT-06");

function unsupportedAgentIdsForMime(mimeType?: string): string[] {
 if (!mimeType) return [];
 if (mimeType.startsWith("image/")) return ["Agent2", "Agent4"];
 if (mimeType.startsWith("audio/")) return ["Agent1", "Agent3", "Agent4"];
 if (mimeType.startsWith("video/")) return ["Agent1", "Agent2"];
 return [];
}

export function AgentProgressDisplay({
 agentUpdates,
 completedAgents,
 progressText,
 allAgentsDone,
 phase,
 awaitingDecision,
 pipelineStatus,
 pipelineMessage,
 onAcceptAnalysis,
 onDeepAnalysis,
 onNewUpload,
 onViewResults,
 playSound: _playSound,
 isNavigating = false,
 mimeType,
}: AgentProgressDisplayProps) {
  const [hiddenAgentIds, setHiddenAgentIds] = useState<Set<string>>(new Set());
  const [skippedAgentIds, setSkippedAgentIds] = useState<Set<string>>(new Set());
  const [isRunningExpanded, setIsRunningExpanded] = useState(false);
  const [isSkippedExpanded, setIsSkippedExpanded] = useState(false);

 useEffect(() => {
  const unsupportedIds = unsupportedAgentIdsForMime(mimeType);
  if (unsupportedIds.length === 0) return;

  setSkippedAgentIds((prev) => new Set([...prev, ...unsupportedIds]));
  const timer = setTimeout(() => {
   setHiddenAgentIds((prev) => new Set([...prev, ...unsupportedIds]));
  }, 10000);

  return () => clearTimeout(timer);
 }, [mimeType]);

 // Track which agents are unsupported
 useEffect(() => {
  completedAgents.forEach((agent) => {
   const isUnsupported = agent.status === "skipped" ||
    (agent.error && /not applicable|not supported|skipping|skipped/i.test(agent.error));
   
   if (isUnsupported && !skippedAgentIds.has(agent.agent_id)) {
    setSkippedAgentIds(prev => new Set([...prev, agent.agent_id]));
    
    // Schedule cleanup after 10 seconds
    setTimeout(() => {
     setHiddenAgentIds(prev => new Set([...prev, agent.agent_id]));
    }, 10000);
   }
  });
 }, [completedAgents, skippedAgentIds]);

 const visibleAgents = allValidAgents.filter(a => !hiddenAgentIds.has(a.id));

 // Variants for staggered entrance
 const containerVariants = {
  hidden: { opacity: 0 },
  show: {
   opacity: 1,
   transition: {
    staggerChildren: 0.15,
    delayChildren: 0.2
   }
  }
 };

 const itemVariants: import("framer-motion").Variants = {
  hidden: { opacity: 0, scale: 0.9, y: 30 },
  show: { 
   opacity: 1, 
   scale: 1,
   y: 0,
   transition: { 
    type: "spring", 
    damping: 25, 
    stiffness: 120 
   }
  }
 };

  const getAgentStatus = (agentId: string) => {
   if (skippedAgentIds.has(agentId)) return "unsupported";
   const completed = completedAgents.find((c) => c.agent_id === agentId);
   if (completed) {
    const isSkipped =
     completed.status === "skipped" ||
     (completed.error
      ? /not applicable|not supported|skipping|skipped/i.test(completed.error)
      : false);
    if (isSkipped) return "unsupported";
    return (completed.status === "error" || completed.status === "failed" || completed.error) ? "error" : "complete";
   }
   if (agentUpdates[agentId]) return "running";

   // If the pipeline is active but agent hasn't started yet, show as "checking" (Connecting)
   // instead of "waiting" (Dim/0.3 opacity). This provides better visual feedback during ingestion.
   if (pipelineStatus === "analyzing" || pipelineStatus === "initiating" || pipelineStatus === "processing") {
     return "checking";
   }

   return "waiting";
  };

 const showInitialDecision = phase === "initial" && (awaitingDecision || allAgentsDone);
 const showDeepComplete = phase === "deep" && (allAgentsDone || pipelineStatus === "complete");
 const phaseStatusText = allAgentsDone || pipelineStatus === "complete"
  ? `${phase === "initial" ? "Initial" : "Deep"} analysis phase complete`
  : `${phase === "initial" ? "Initial" : "Deep"} analysis in progress`;

 const runningCount = Object.keys(agentUpdates).filter(id => !completedAgents.some(c => c.agent_id === id)).length;
 const skippedCount = skippedAgentIds.size;

 return (
  <div className="flex flex-col w-full max-w-[1560px] mx-auto gap-8 pb-36 pt-24">

    {/* ── Evidence Analysis Title & Phase ────────────────────────────────── */}
    <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-10 w-full mb-12 px-2">
      <div className="flex flex-col gap-2">
        <motion.h1
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          className="text-4xl md:text-5xl font-heading font-bold text-white tracking-tight"
        >
          Evidence Analysis
        </motion.h1>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse shadow-[0_0_10px_#00FFFF]" />
            <p className="text-[10px] font-mono font-bold text-primary tracking-[0.2em] uppercase">
              {phase === "initial" ? "Initial_Pipeline" : "Deep_Pipeline"}
            </p>
          </div>
          <div className="w-[1px] h-3 bg-white/10" />
          <p className="text-xs font-medium text-white/40 italic" role="status" aria-live="polite">
            {pipelineMessage || progressText || phaseStatusText}
          </p>
        </div>
      </div>

      {/* Running Agents HUD */}
      <div className="flex items-center gap-4">
        <div className="horizon-card px-6 py-4 rounded-xl flex items-center gap-6 border-primary/20">
           <div className="flex flex-col items-start">
             <span className="text-[9px] font-mono font-bold text-white/20 uppercase tracking-widest">Active_Nodes</span>
             <span className="text-2xl font-mono font-bold text-white leading-none mt-1">0{runningCount}</span>
           </div>
           <div className="w-10 h-10 rounded-full border border-primary/20 flex items-center justify-center">
              <motion.div animate={{ rotate: 360 }} transition={{ duration: 4, repeat: Infinity, ease: "linear" }}>
                <Activity className="w-5 h-5 text-primary" />
              </motion.div>
           </div>
        </div>
      </div>
    </div>

   {/* ── Agent Cards Grid ──────────────────────────────────────────────── */}
   <div className="w-full">
    <motion.div 
     layout
     variants={containerVariants}
     initial="hidden"
     animate="show"
     className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
    >
     <AnimatePresence mode="popLayout">
      {visibleAgents.map((agent) => (
       <motion.div
        key={agent.id}
        layout
        variants={itemVariants}
        exit={{ opacity: 0, scale: 0.8, transition: { duration: 0.3 } }}
       >
        <AgentStatusCard
         agentId={agent.id}
         name={agent.name}
         badge={agent.badge}
         status={getAgentStatus(agent.id)}
         thinking={agentUpdates[agent.id]?.thinking}
         liveUpdate={agentUpdates[agent.id]}
         completedData={completedAgents.find((c) => c.agent_id === agent.id)}
         isRevealed={true}
         fileMime={mimeType}
        />
       </motion.div>
      ))}
     </AnimatePresence>
    </motion.div>
   </div>



   <AnimatePresence>
    {(showInitialDecision || showDeepComplete) && (
      <motion.div
       initial={{ opacity: 0, y: 100 }}
       animate={{ opacity: 1, y: 0 }}
       exit={{ opacity: 0, y: 100 }}
       className="fixed bottom-12 left-1/2 -translate-x-1/2 z-50 w-full max-w-2xl px-6 pointer-events-none"
      >
       <div className="horizon-card p-2 rounded-[2rem] shadow-[0_40px_100px_rgba(0,0,0,0.8)] pointer-events-auto">
         <div className="bg-[#020617] rounded-[1.8rem] p-3 flex items-center gap-4">
           {showInitialDecision ? (
            <>
             <button
              onClick={onAcceptAnalysis}
              disabled={isNavigating}
              className="flex-1 btn-horizon-outline py-4 text-xs"
             >
              {isNavigating ? <Loader2 className="w-4 h-4 animate-spin" /> : "Accept Analysis"}
             </button>
             <button
              onClick={onDeepAnalysis}
              disabled={isNavigating}
              className="flex-[1.5] btn-horizon-primary py-4 text-xs flex items-center justify-center gap-3"
             >
              <Microscope className="w-4 h-4" />
              Deep Analysis
              <ArrowRight className="w-4 h-4" />
             </button>
            </>
           ) : (
            <>
             <button
              onClick={onNewUpload}
              className="flex-1 btn-horizon-outline py-4 text-xs"
             >
              New Upload
             </button>
             <button
              onClick={onViewResults}
              disabled={isNavigating}
              className="flex-[1.5] btn-horizon-primary py-4 text-xs flex items-center justify-center gap-3"
             >
              {isNavigating ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
              Generate Report
              <ArrowRight className="w-4 h-4" />
             </button>
            </>
           )}
         </div>
       </div>
      </motion.div>
    )}
   </AnimatePresence>
  </div>
 );
}

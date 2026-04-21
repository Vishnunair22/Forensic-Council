"use client";

import React, { useState, useEffect } from "react";
import { clsx } from "clsx";
import {
 Loader2,
 FileText,
 ArrowRight,
 Microscope,
 RotateCcw,
 CheckCircle2,
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
 agentUpdates: Record<string, { status: string; thinking: string }>;
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
const ForensicTimeline = dynamic(
  () => import("./ForensicTimeline").then((m) => m.ForensicTimeline),
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
 const [showTimeline, setShowTimeline] = useState(false);

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
  return "waiting";
 };

 const showInitialDecision = phase === "initial" && (awaitingDecision || allAgentsDone);
 const showDeepComplete = phase === "deep" && (allAgentsDone || pipelineStatus === "complete");

 // Metrics
 const activeCompleted = completedAgents.filter((a) => {
  const skip = a.status === "skipped" || (a.error ? /not applicable|not supported|skipping|skipped/i.test(a.error) : false);
  return !skip;
 });
 const totalFlagged = activeCompleted.reduce((s, c) => s + (c.findings_count || 0), 0);

 const runningCount = Object.keys(agentUpdates).filter(id => !completedAgents.some(c => c.agent_id === id)).length;
 const finishedCount = completedAgents.filter(a => {
  const skip = a.status === "skipped" || (a.error ? /not applicable|not supported|skipping|skipped/i.test(a.error) : false);
  return !skip;
 }).length;
 const skippedCount = skippedAgentIds.size;
 const alertCount = totalFlagged;

 return (
  <div className="flex flex-col w-full max-w-[1560px] mx-auto gap-6 pb-36">

    {/* ── Cinematic Header ────────────────────────────────────────────────── */}
    <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-5 w-full">
     <div className="flex flex-col">
       <motion.h1
       initial={{ opacity: 0, x: -20 }}
       animate={{ opacity: 1, x: 0 }}
       className="text-3xl sm:text-4xl md:text-5xl font-black text-white uppercase leading-none"
      >
       Evidence <span className="text-primary">Analysis</span>
      </motion.h1>
      <div className="flex flex-wrap items-center gap-3 mt-3">
        <span className="text-[10px] font-black text-primary/90 font-mono px-2 py-1 bg-primary/10 border border-primary/20 rounded">
          {phase === "initial" ? "PHASE_01: SCREENING" : "PHASE_02: INVESTIGATION"}
        </span>
        <p className="text-xs text-white/50 font-semibold flex items-center gap-2">
          {pipelineMessage || progressText}
        </p>
      </div>
     </div>

    <motion.div
     initial={{ opacity: 0, y: 10 }}
     animate={{ opacity: 1, y: 0 }}
     transition={{ delay: 0.2 }}
     className="flex items-stretch gap-3 w-full lg:w-auto"
    >
       <div className="min-w-32 rounded-lg border border-border-subtle bg-white/[0.02] px-4 py-3">
        <span className="text-[10px] font-black text-white/35 tracking-widest uppercase block mb-1">System Load</span>
        <span className="text-2xl font-black text-white leading-none font-mono">
         {allAgentsDone ? "100%" : `${Math.round((finishedCount / allValidAgents.length) * 100)}%`}
        </span>
       </div>
       <div className="min-w-32 rounded-lg border border-border-subtle bg-white/[0.02] px-4 py-3">
         <span className="text-[10px] font-black text-white/35 tracking-widest uppercase block mb-1">Active Threads</span>
         <span className="text-2xl font-black text-primary leading-none font-mono">
          {runningCount}
         </span>
       </div>
    </motion.div>
   </div>

   {/* ── Agent Cards Grid ──────────────────────────────────────────────── */}
   <div className="w-full">
    <motion.div 
     layout
     variants={containerVariants}
     initial="hidden"
     animate="show"
     className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5"
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
         completedData={completedAgents.find((c) => c.agent_id === agent.id)}
         isRevealed={true}
         fileMime={mimeType}
        />
       </motion.div>
      ))}
     </AnimatePresence>
    </motion.div>
   </div>


   {/* ── Status Row + View Ledger ──────────────────────────────────────── */}
    <div className="flex flex-col sm:flex-row items-center justify-between gap-5 w-full">
     <div className="w-full flex flex-col sm:flex-row items-start sm:items-center justify-between premium-glass p-4 sm:px-5 rounded-xl relative overflow-hidden gap-4 border border-border-subtle">
      <div className="absolute inset-0 bg-primary/5 opacity-50" />
      
      <div className="grid grid-cols-2 sm:flex sm:items-center gap-x-12 gap-y-3 relative z-10 w-full sm:w-auto">
       {[
        { label: "Active Threads",  value: runningCount, color: "text-primary" },
        { label: "Verified Labs", value: finishedCount, color: "text-primary" },
        { label: "Phase Skips", value: skippedCount, color: "text-white/20" },
        { label: "Findings",  value: alertCount,  color: alertCount > 0 ? "text-primary" : "text-white/10" },
       ].map((s) => (
        <div key={s.label} className="flex flex-col items-start gap-0.5">
         <span className="text-[10px] font-black text-white/30 tracking-widest uppercase leading-none mb-1">{s.label}</span>
         <span className={clsx("text-xl font-black font-mono tracking-tight", s.color)}>{s.value}</span>
        </div>
       ))}
      </div>

     <div className="flex items-center gap-6 relative z-10 shrink-0 w-full sm:w-auto justify-end sm:justify-start">
      {hiddenAgentIds.size > 0 && (
       <button
        onClick={() => setHiddenAgentIds(new Set())}
        className="text-[10px] font-bold text-white/20 hover:text-white/40 tracking-widest transition-colors"
       >
        Restore Hidden ({hiddenAgentIds.size})
       </button>
      )}
      <button
       onClick={() => setShowTimeline(!showTimeline)}
       aria-expanded={showTimeline}
       aria-controls="evidence-ledger"
       className={clsx(
        "flex items-center gap-2.5 px-6 py-2.5 rounded-full border transition-all duration-300 font-bold text-[10px] tracking-widest",
        showTimeline
         ? "bg-white/10 border-white/20 text-white"
         : "bg-white/[0.02] border-white/10 text-white/40 hover:border-white/20 hover:text-white"
       )}
      >
       <FileText className="w-3.5 h-3.5" aria-hidden="true" />
       <span>{showTimeline ? "Close Ledger" : "View Ledger"}</span>
      </button>
     </div>
    </div>
   </div>

   <AnimatePresence>
    {showTimeline && (
     <motion.div
      id="evidence-ledger"
      initial={{ height: 0, opacity: 0 }}
      animate={{ height: "auto", opacity: 1 }}
      exit={{ height: 0, opacity: 0 }}
      className="w-full max-w-4xl mx-auto overflow-hidden"
     >
      <ForensicTimeline
       completedAgents={completedAgents}
       agentUpdates={agentUpdates}
      />
     </motion.div>
    )}
   </AnimatePresence>

   <AnimatePresence>
    {(showInitialDecision || showDeepComplete) && (
     <motion.div
      initial={{ opacity: 0, y: "100%" }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: "100%" }}
      transition={{ type: "spring", damping: 30, stiffness: 200 }}
      className="fixed bottom-0 left-0 right-0 z-50 glass-dock pb-safe pb-8 pt-5 px-4 sm:px-6 pointer-events-auto shadow-[0_-20px_50px_rgba(0,0,0,0.8)] flex flex-col items-center justify-center text-center"
      role="region"
      aria-label="Analysis complete — choose next step"
     >
      <div className="flex flex-col items-center w-full max-w-4xl mx-auto gap-4">
       <div className="flex flex-col items-center">
        <span className="flex items-center justify-center gap-2 text-[10px] font-bold text-cyan-400 tracking-[0.2em] mb-1">
         <span className="w-2 h-2 bg-cyan-400 rounded-full animate-pulse" aria-hidden="true" />
         Analysis Phase Complete
        </span>
        <span className="text-sm text-white/50 font-medium">
         {showInitialDecision
          ? "Initial results ready. Commit findings or initiate depth pass."
          : "Comprehensive analysis finalized. All signals verified."}
        </span>
       </div>

       <div className="flex items-center justify-center gap-4 flex-wrap w-full">
        {showInitialDecision ? (
         <>
          <button
           onClick={onAcceptAnalysis}
           disabled={isNavigating}
           className="btn-outline px-8"
          >
           {isNavigating ? <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> : <CheckCircle2 className="w-4 h-4" aria-hidden="true" />}
           Accept Results
          </button>
          <button
           onClick={onDeepAnalysis}
           disabled={isNavigating}
           className="btn-premium group px-8"
          >
           <Microscope className="w-4 h-4" aria-hidden="true" />
           Deep Analysis
           <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" aria-hidden="true" />
          </button>
         </>
        ) : (
         <>
          <button
           onClick={onNewUpload}
           className="btn-outline px-8"
          >
           <RotateCcw className="w-4 h-4" aria-hidden="true" />
           New Analysis
          </button>
          <button
           onClick={onViewResults}
           disabled={isNavigating}
           className="btn-premium group px-8"
          >
           {isNavigating ? <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> : <FileText className="w-4 h-4" aria-hidden="true" />}
           View Final Report
           <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" aria-hidden="true" />
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

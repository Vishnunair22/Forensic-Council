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
 progressText: _progressText,
 allAgentsDone,
 phase,
 awaitingDecision,
 pipelineStatus,
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
  return "waiting";
 };

 const showInitialDecision = phase === "initial" && (awaitingDecision || allAgentsDone);
 const showDeepComplete = phase === "deep" && (allAgentsDone || pipelineStatus === "complete");

 const runningCount = Object.keys(agentUpdates).filter(id => !completedAgents.some(c => c.agent_id === id)).length;
 const skippedCount = skippedAgentIds.size;

 return (
  <div className="flex flex-col w-full max-w-[1560px] mx-auto gap-6 pb-36">

    {/* ── Evidence Analysis Title & Phase ────────────────────────────────── */}
    <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-8 w-full mb-8">
      <div className="flex items-center gap-6">
        <div className="flex flex-col gap-1">
          <motion.h1
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            className="text-4xl font-black text-white tracking-tight"
          >
            Evidence Analysis
          </motion.h1>
          <div className="flex items-center gap-3">
            <div className="relative flex items-center justify-center w-5 h-5">
              <div className="absolute inset-0 bg-primary/20 rounded-full glow-pulse" />
              <Loader2 className="w-4 h-4 text-primary animate-premium-spin relative z-10" />
            </div>
            <p className="text-[10px] font-bold text-primary tracking-[0.3em] uppercase">
              {phase === "initial" ? "Initial Analysis" : "Deep Analysis"}
            </p>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-4">
        {/* Running Agents Summary */}
        <div className="flex flex-col gap-2">
          <button
            onClick={() => setIsRunningExpanded(!isRunningExpanded)}
            className="flex items-center gap-6 bg-white/[0.03] px-6 py-4 rounded-2xl border border-white/5 backdrop-blur-xl hover:bg-white/[0.06] transition-all group"
          >
            <div className="flex flex-col items-start">
              <span className="text-[9px] font-bold text-white/30 tracking-[0.2em] mb-0.5 uppercase">Status</span>
              <div className="flex items-center gap-2">
                <span className="text-sm font-black text-white font-mono">Running Agents</span>
                <span className="flex items-center justify-center w-6 h-6 rounded-lg bg-primary/10 text-primary text-xs font-black">
                  {runningCount}
                </span>
              </div>
            </div>
            <div className="w-8 h-8 rounded-full border border-primary/20 flex items-center justify-center group-hover:border-primary/50 transition-colors">
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
              >
                <Activity className="w-4 h-4 text-primary" />
              </motion.div>
            </div>
          </button>
          
          <AnimatePresence>
            {isRunningExpanded && runningCount > 0 && (
              <motion.div
                initial={{ opacity: 0, y: -10, height: 0 }}
                animate={{ opacity: 1, y: 0, height: "auto" }}
                exit={{ opacity: 0, y: -10, height: 0 }}
                className="overflow-hidden bg-white/[0.02] border border-white/5 rounded-xl p-3"
              >
                <div className="flex flex-wrap gap-2">
                  {allValidAgents.filter(a => getAgentStatus(a.id) === "running").map(a => (
                    <div key={a.id} className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/5 border border-white/5">
                      <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                      <span className="text-[10px] font-bold text-white/80">{a.name}</span>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Skipped Agents Summary */}
        {skippedCount > 0 && (
          <div className="flex flex-col gap-2">
            <button
              onClick={() => setIsSkippedExpanded(!isSkippedExpanded)}
              className="flex items-center gap-6 bg-white/[0.03] px-6 py-4 rounded-2xl border border-white/5 backdrop-blur-xl hover:bg-white/[0.06] transition-all group"
            >
              <div className="flex flex-col items-start">
                <span className="text-[9px] font-bold text-white/30 tracking-[0.2em] mb-0.5 uppercase">System</span>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-black text-white/40 font-mono">Skipped Agents</span>
                  <span className="flex items-center justify-center w-6 h-6 rounded-lg bg-white/5 text-white/30 text-xs font-black">
                    {skippedCount}
                  </span>
                </div>
              </div>
              <div className="w-8 h-8 rounded-full border border-white/10 flex items-center justify-center group-hover:border-white/30 transition-colors">
                <Ban className="w-4 h-4 text-white/30" />
              </div>
            </button>

            <AnimatePresence>
              {isSkippedExpanded && (
                <motion.div
                  initial={{ opacity: 0, y: -10, height: 0 }}
                  animate={{ opacity: 1, y: 0, height: "auto" }}
                  exit={{ opacity: 0, y: -10, height: 0 }}
                  className="overflow-hidden bg-white/[0.02] border border-white/5 rounded-xl p-3"
                >
                  <div className="flex flex-wrap gap-2">
                    {allValidAgents.filter(a => skippedAgentIds.has(a.id)).map(a => (
                      <div key={a.id} className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/5 border border-white/5">
                        <div className="w-2 h-2 rounded-full bg-white/20" />
                        <span className="text-[10px] font-bold text-white/40">{a.name}</span>
                      </div>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
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
       <div className="flex items-center gap-4 p-3 rounded-[2rem] bg-black/40 backdrop-blur-3xl border border-white/10 shadow-[0_32px_64px_rgba(0,0,0,0.6)] pointer-events-auto">
        {showInitialDecision ? (
         <>
          <button
           onClick={onAcceptAnalysis}
           disabled={isNavigating}
           className="flex-1 px-8 py-4 rounded-2xl bg-white/5 border border-white/10 text-white font-black text-xs tracking-[0.2em] hover:bg-white/10 transition-all flex items-center justify-center gap-3 disabled:opacity-50 uppercase"
          >
           {isNavigating ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4 text-emerald-400" />}
           Accept Results
          </button>
          <button
           onClick={onDeepAnalysis}
           disabled={isNavigating}
           className="flex-[1.5] px-8 py-4 rounded-2xl bg-primary text-black font-black text-xs tracking-[0.2em] hover:bg-primary/90 transition-all shadow-[0_0_30px_rgba(34,211,238,0.3)] flex items-center justify-center gap-3 disabled:opacity-50 uppercase"
          >
           <Microscope className="w-4 h-4" />
           Deep Investigation
           <ArrowRight className="w-4 h-4" />
          </button>
         </>
        ) : (
         <>
          <button
           onClick={onNewUpload}
           className="flex-1 px-8 py-4 rounded-2xl bg-white/5 border border-white/10 text-white font-black text-xs tracking-[0.2em] hover:bg-white/10 transition-all flex items-center justify-center gap-3 uppercase"
          >
           <RotateCcw className="w-4 h-4 text-primary" />
           New Upload
          </button>
          <button
           onClick={onViewResults}
           disabled={isNavigating}
           className="flex-[1.5] px-8 py-4 rounded-2xl bg-primary text-black font-black text-xs tracking-[0.2em] hover:bg-primary/90 transition-all shadow-[0_0_30px_rgba(34,211,238,0.3)] flex items-center justify-center gap-3 disabled:opacity-50 uppercase"
          >
           {isNavigating ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
           Generate Final Report
           <ArrowRight className="w-4 h-4" />
          </button>
         </>
        )}
       </div>
      </motion.div>
    )}
   </AnimatePresence>
  </div>
 );
}

"use client";

import React, { useState, useEffect, useMemo, useRef } from "react";
import {
 Loader2,
 FileText,
 ArrowRight,
 Activity,
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

const allValidAgents = AGENTS_DATA.filter((agent) => agent.id !== "Arbiter");

function isAgentSupportedForMime(agentId: string, mimeType?: string): boolean {
  if (!mimeType) return true;
  if (mimeType.startsWith("image/")) return !["Agent2", "Agent4"].includes(agentId);
  if (mimeType.startsWith("audio/")) return !["Agent1", "Agent3", "Agent4"].includes(agentId);
  if (mimeType.startsWith("video/")) return !["Agent1", "Agent2"].includes(agentId);
  return true;
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
 onNewUpload,
 onViewResults,
 playSound,
 isNavigating = false,
 mimeType,
}: AgentProgressDisplayProps) {
  const [validatedAgents, setValidatedAgents] = useState<Set<string>>(new Set());
  const [hiddenAgents, setHiddenAgents] = useState<Set<string>>(new Set());

  const playSoundRef = useRef(playSound);
  useEffect(() => { playSoundRef.current = playSound; }, [playSound]);

  // Validate each card with a per-card stagger — runs once on mount only.
  // Using a single effect with all timers avoids the chained-setTimeout pattern
  // that breaks when re-renders (from frequent WS updates) reset intermediate state.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    const timers = allValidAgents.map((agent, i) =>
      setTimeout(() => {
        setValidatedAgents(prev => new Set(prev).add(agent.id));
        playSoundRef.current?.("agent");
      }, 800 + i * 600) // 0.8s, 1.4s, 2.0s, 2.6s, 3.2s
    );
    return () => timers.forEach(t => clearTimeout(t));
  }, []); // intentional — one-time setup on mount

  // Auto-hide unsupported agents 10s after they are validated
  useEffect(() => {
    const timers: NodeJS.Timeout[] = [];
    validatedAgents.forEach(id => {
      if (!isAgentSupportedForMime(id, mimeType) && !hiddenAgents.has(id)) {
        timers.push(setTimeout(() => {
          setHiddenAgents(prev => new Set(prev).add(id));
        }, 10000));
      }
    });
    return () => timers.forEach(clearTimeout);
  }, [validatedAgents, mimeType]); // hiddenAgents intentionally omitted to prevent re-scheduling

  const visibleAgents = useMemo(() => {
    return allValidAgents.filter(a => !hiddenAgents.has(a.id));
  }, [hiddenAgents]);

  const getAgentStatus = (agentId: string) => {
    if (!validatedAgents.has(agentId)) return "validating";
    
    const isSupported = isAgentSupportedForMime(agentId, mimeType);
    if (!isSupported) return "unsupported";

    const completed = completedAgents.find((c) => c.agent_id === agentId);
    if (completed) {
      return (completed.status === "error" || completed.status === "failed" || completed.error) ? "error" : "complete";
    }
    
    if (agentUpdates[agentId]) return "running";
    if (pipelineStatus === "analyzing" || pipelineStatus === "initiating" || pipelineStatus === "processing") {
      return "checking";
    }
    return "waiting";
  };

  const containerVariants: import("framer-motion").Variants = {
    hidden: {},
    show: { transition: { staggerChildren: 0.15 } },
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

  const runningCount = Object.keys(agentUpdates).filter(id => !completedAgents.some(c => c.agent_id === id)).length;

  return (
    <div className="flex flex-col w-full max-w-[1560px] mx-auto gap-8 pb-36 pt-24">
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
              {pipelineMessage || progressText || (allAgentsDone ? "Analysis phase complete" : "Analysis in progress")}
            </p>
          </div>
        </div>

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

      <div className="w-full">
        <motion.div
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
          variants={containerVariants}
          initial="hidden"
          animate="show"
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
                  status={getAgentStatus(agent.id) as any}
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
        {awaitingDecision && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="fixed bottom-12 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 px-6 py-3 rounded-full bg-slate-900/90 border border-primary/20 backdrop-blur-md shadow-lg"
          >
            <Loader2 className="w-3.5 h-3.5 text-primary animate-spin shrink-0" />
            <span className="text-[11px] font-mono text-white/60 tracking-widest uppercase">Generating Report…</span>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {(allAgentsDone || pipelineStatus === "complete") && (
          <motion.div
            initial={{ opacity: 0, y: 100 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 100 }}
            className="fixed bottom-12 left-1/2 -translate-x-1/2 z-50 w-full max-w-2xl px-6 pointer-events-none"
          >
            <div className="horizon-card p-2 rounded-[2rem] shadow-[0_40px_100px_rgba(0,0,0,0.8)] pointer-events-auto">
              <div className="bg-[#020617] rounded-[1.8rem] p-3 flex items-center gap-4">
                <button onClick={onNewUpload} className="flex-1 btn-horizon-outline py-4 text-xs">New Upload</button>
                <button
                  onClick={onViewResults}
                  disabled={isNavigating}
                  className="flex-[1.5] btn-horizon-primary py-4 text-xs flex items-center justify-center gap-3"
                >
                  {isNavigating ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
                  View Results
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

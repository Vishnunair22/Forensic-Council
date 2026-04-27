"use client";

import React, { useState, useEffect, useMemo, useRef } from "react";
import {
  Loader2,
  FileText,
  ArrowRight,
  Activity,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { AGENTS as AGENTS_DATA } from "@/lib/constants";
import { QuotaMeter } from "./QuotaMeter";
import type { SoundType } from "@/hooks/useSound";
import { storage } from "@/lib/storage";
import { isAgentSupportedForMime, supportedAgentIdsForMime } from "@/lib/agentSupport";
import { AgentStatusCard } from "./AgentStatusCard";

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
 summary?: string;
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
  sessionId?: string | null;
  onNewUpload?: () => void;
  onViewResults?: () => void;
  onAcceptAnalysis?: () => void;
  onRunDeepAnalysis?: () => void;
  isNavigating?: boolean;
  mimeType?: string;
  playSound?: (type: SoundType) => void;
  revealQueue?: AgentUpdate[];
  revealPending?: boolean;
  arbiterDeliberating?: boolean;
}

const allValidAgents = AGENTS_DATA.filter((agent) => agent.id !== "Arbiter");

type AgentStatus = "waiting" | "checking" | "running" | "complete" | "error" | "unsupported" | "validating";

export function AgentProgressDisplay({
  agentUpdates,
  completedAgents,
  progressText,
  allAgentsDone,
  phase,
  awaitingDecision,
  pipelineStatus,
  pipelineMessage,
  sessionId,
  onNewUpload,
  onViewResults,
  onAcceptAnalysis,
  onRunDeepAnalysis,
  isNavigating = false,
  mimeType,
  playSound,
  revealQueue = [],
  revealPending = false,
  arbiterDeliberating = false,
}: AgentProgressDisplayProps) {
  const [hiddenAgents, setHiddenAgents] = useState(new Set<string>());
  const playSoundRef = useRef(playSound);
  useEffect(() => { playSoundRef.current = playSound; }, [playSound]);

  // Play page-load sound + staggered card entrance sounds once on mount
  const mountSoundsFiredRef = useRef(false);
  useEffect(() => {
    if (mountSoundsFiredRef.current) return;
    mountSoundsFiredRef.current = true;
    const ps = playSoundRef.current;
    if (!ps) return;
    ps("page_load");
    const count = allValidAgents.length;
    for (let i = 0; i < count; i++) {
      setTimeout(() => playSoundRef.current?.("hum"), i * 150 + 80);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const prevHiddenSizeRef = useRef(0);

  // Play a subtle sound when unsupported agents slide off the grid
  useEffect(() => {
    if (hiddenAgents.size > prevHiddenSizeRef.current) {
      playSoundRef.current?.("click");
    }
    prevHiddenSizeRef.current = hiddenAgents.size;
  }, [hiddenAgents.size]);

  useEffect(() => {
    if (!mimeType) return;
    const timers: NodeJS.Timeout[] = [];
    allValidAgents.forEach((agent) => {
      if (!isAgentSupportedForMime(agent.id, mimeType)) {
        const timer = setTimeout(() => {
          setHiddenAgents((prev) => {
            const next = new Set(prev);
            next.add(agent.id);
            return next;
          });
        }, 10000);
        timers.push(timer);
      }
    });
    return () => timers.forEach(clearTimeout);
  }, [mimeType]);

  const initialAgentIds = useMemo<string[]>(() => {
    if (phase !== "deep") return [];
    const raw = storage.getItem<AgentUpdate[]>("forensic_initial_agents", true);
    if (Array.isArray(raw) && raw.length) {
      return raw.map((a) => a.agent_id).filter((id): id is string => typeof id === "string");
    }
    // Fallback for refresh: derive from MIME so the deep grid is never empty
    return Array.from(supportedAgentIdsForMime(mimeType || undefined));
  }, [phase, mimeType]);

  const visibleAgents = useMemo(() => {
    return allValidAgents
      .filter((a) => !hiddenAgents.has(a.id))
      .filter((a) => phase === "deep" ? initialAgentIds.includes(a.id) : true);
  }, [hiddenAgents, phase, initialAgentIds]);

  const getAgentStatus = (agentId: string): AgentStatus => {
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
    show: { transition: { staggerChildren: 0.6, delayChildren: 0.1 } },
  };

  const itemVariants: import("framer-motion").Variants = {
    hidden: { opacity: 0, scale: 0.92, y: 40 },
    show: {
      opacity: 1,
      scale: 1,
      y: 0,
      transition: { type: "spring", damping: 22, stiffness: 110, duration: 0.55 },
    },
  };

  const runningCount = Object.keys(agentUpdates).filter(id => !completedAgents.some(c => c.agent_id === id)).length;

  return (
    <div 
      className="flex flex-col w-full max-w-[1560px] mx-auto gap-8 pb-36 pt-24"
      aria-label="Agent forensic analysis progress"
    >
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-10 w-full mb-12 px-2">
        <div className="flex flex-col gap-2">
          <motion.h1
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            className="text-5xl md:text-6xl font-heading font-bold text-white tracking-tight"
          >
            Analysis Pipeline
          </motion.h1>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-[var(--color-success-light)] animate-pulse shadow-[0_0_15px_rgba(167,255,210,0.5)]" />
              <p className="text-[10px] font-mono font-bold text-[var(--color-success-light)] tracking-[0.3em] uppercase">
                {phase === "initial" ? "Initial_Verification" : "Deep_Analysis"}
              </p>
            </div>
            <div className="w-[1px] h-3 bg-white/10" />
            <p className="text-sm font-medium text-white/40 italic" role="status" aria-live="polite" aria-atomic="false">
              {pipelineMessage || progressText || (allAgentsDone ? "Analysis phase complete" : "Coordination in progress")}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="glass-panel px-6 py-5 rounded-2xl flex items-center gap-6 border-white/10">
             <div className="flex flex-col items-start">
               <span className="text-[9px] font-mono font-bold text-white/20 uppercase tracking-[0.2em]">Active_Nodes</span>
               <span className="text-3xl font-mono font-bold text-white leading-none mt-1">0{runningCount}</span>
             </div>
             <div className="w-12 h-12 rounded-full border border-[var(--color-success-light)]/20 flex items-center justify-center bg-[var(--color-success-light)]/5">
                <motion.div animate={{ rotate: 360 }} transition={{ duration: 4, repeat: Infinity, ease: "linear" }}>
                  <Activity className="w-6 h-6 text-[var(--color-success-light)]" />
                </motion.div>
             </div>
          </div>
          {sessionId && <QuotaMeter sessionId={sessionId} />}
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
                  status={getAgentStatus(agent.id)}
                  thinking={agentUpdates[agent.id]?.thinking}
                  liveUpdate={agentUpdates[agent.id]}
                  completedData={completedAgents.find((c) => c.agent_id === agent.id)}
                  isRevealed={true}
                  fileMime={mimeType}
                  phase={phase}
                />
              </motion.div>
            ))}
          </AnimatePresence>
        </motion.div>
      </div>

      <AnimatePresence>
        {awaitingDecision && phase === "initial" && revealQueue.length === 0 && !arbiterDeliberating && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="fixed bottom-12 left-1/2 -translate-x-1/2 z-50 w-full max-w-2xl px-6"
          >
            <div className="glass-panel p-2 rounded-full shadow-[0_40px_100px_rgba(0,0,0,0.8)] border-white/10">
              <div className="bg-[#020203]/80 rounded-full p-2 flex items-center gap-3">
                <button
                  data-testid="accept-analysis-btn"
                  onClick={onAcceptAnalysis}
                  disabled={isNavigating}
                  className="flex-1 btn-horizon-outline py-3 text-xs"
                >
                  Accept Verdict
                </button>
                <button
                  data-testid="deep-analysis-btn"
                  onClick={onRunDeepAnalysis}
                  disabled={isNavigating}
                  className="flex-[1.5] btn-horizon-primary py-3 text-xs flex items-center justify-center gap-3"
                >
                  <span className="flex items-center gap-2 text-[#020617]">
                    {isNavigating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Activity className="w-4 h-4" />}
                    <span className="font-bold">DEEP ANALYSIS</span>
                    <ArrowRight className="w-4 h-4" />
                  </span>
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {!awaitingDecision && revealQueue.length === 0 && (allAgentsDone || pipelineStatus === "complete") && (
          <motion.div
            initial={{ opacity: 0, y: 100 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 100 }}
            className="fixed bottom-12 left-1/2 -translate-x-1/2 z-50 w-full max-w-2xl px-6"
          >
            <div className="glass-panel p-2 rounded-full shadow-[0_40px_100px_rgba(0,0,0,0.8)] border-white/10">
              <div className="bg-[#020203]/80 rounded-full p-2 flex items-center gap-3">
                <button data-testid="new-analysis-btn" onClick={onNewUpload} className="flex-1 btn-horizon-outline py-3 text-xs">New Ingestion</button>
                <button
                  data-testid="view-report-btn"
                  onClick={onViewResults}
                  disabled={isNavigating}
                  className="flex-[1.5] btn-horizon-primary py-3 text-xs flex items-center justify-center gap-3"
                >
                  <span className="flex items-center gap-2 text-[#020617]">
                    {isNavigating ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
                    <span className="font-bold">VIEW REPORT</span>
                    <ArrowRight className="w-4 h-4" />
                  </span>
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

    </div>
  );
}

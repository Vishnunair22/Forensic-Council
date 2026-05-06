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
import { storage } from "@/lib/storage";
import { isAgentSupportedForMime, supportedAgentIdsForMime } from "@/lib/agentSupport";
import { AgentStatusCard } from "./AgentStatusCard";
import { AgentStatusSummary } from "./AgentStatusSummary";
import { ArbiterCard } from "./ArbiterCard";
import type { SoundType } from "@/hooks/useSound";

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
 agent_verdict?: "AUTHENTIC" | "CLEAN" | "INCONCLUSIVE" | "SUSPICIOUS" | "TAMPERED" | "NEEDS_REVIEW" | "LIKELY_MANIPULATED" | "LIKELY_AI_GENERATED" | "LIKELY_SPOOFED" | "LIKELY_SYNTHETIC";
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
  onAcceptAnalysis?: () => void;
  onRunDeepAnalysis?: () => void;
  isNavigating?: boolean;
  mimeType?: string;
  playSound?: (type: SoundType) => void;
  revealQueue?: AgentUpdate[];
  revealPending?: boolean;
  arbiterDeliberating?: boolean;
  arbiterStatus?: string | null;
  arbiterThinking?: string | null;
  hasStartedAnalysis?: boolean;
}

type Agent = typeof AGENTS_DATA[number];
const allValidAgents: Agent[] = AGENTS_DATA.filter((agent) => agent.id !== "Arbiter");

type AgentStatus = "waiting" | "queued" | "checking" | "running" | "complete" | "error" | "unsupported" | "validating";

export function AgentProgressDisplay({
  agentUpdates,
  completedAgents = [],
  progressText,
  allAgentsDone,
  phase,
  awaitingDecision,
  pipelineStatus,
  pipelineMessage,
  onNewUpload,
  onViewResults,
  onAcceptAnalysis,
  onRunDeepAnalysis,
  isNavigating = false,
  mimeType,
  playSound,
  revealQueue = [],
  arbiterDeliberating = false,
  arbiterStatus = null,
  arbiterThinking = null,
  hasStartedAnalysis = false,
}: AgentProgressDisplayProps) {
  const [expandedCards, setExpandedCards] = useState<Record<string, boolean>>({});
  
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
    
    // Only play entrance hums for agents that are actually supported/visible
    const supported = allValidAgents.filter(a => isAgentSupportedForMime(a.id, mimeType));
    supported.forEach((_, i) => {
      setTimeout(() => playSoundRef.current?.("card_reveal"), i * 150 + 80);
    });
  }, [mimeType]);  

  useEffect(() => {
    if (!mimeType) return;
    setExpandedCards({});
  }, [mimeType]);

  const initialAgentIds = useMemo<string[]>(() => {
    if (phase !== "deep") return [];
    const raw = storage.getItem<AgentUpdate[]>("forensic_initial_agents", true);
    if (Array.isArray(raw) && raw.length) {
      return (raw as AgentUpdate[]).map((a) => a.agent_id).filter((id): id is string => typeof id === "string");
    }
    const fromMime = Array.from(supportedAgentIdsForMime(mimeType || undefined));
    if (fromMime.length) return fromMime;
    return allValidAgents.map(a => a.id);
  }, [phase, mimeType]);

  const visibleAgents = useMemo((): Agent[] => {
    return allValidAgents
      .filter((a): boolean => {
        if (phase === "deep") return initialAgentIds.includes(a.id);
        if (!mimeType) return true;
        return isAgentSupportedForMime(a.id, mimeType);
      });
  }, [phase, initialAgentIds, mimeType]);

  const skippedAgents = useMemo(() => {
    if (!mimeType) return [];
    return allValidAgents.filter(a => !isAgentSupportedForMime(a.id, mimeType));
  }, [mimeType]);

  const isQueuePending = /queue|queued|enqueued|awaiting available forensic worker|waiting for an available forensic worker/i.test(
    `${pipelineMessage || ""} ${progressText || ""}`
  );

  const getAgentStatus = (agentId: string): AgentStatus => {
    const completed = completedAgents?.find((c) => c.agent_id === agentId);
    if (completed) {
      if (completed.status === "skipped") return "unsupported";
      return (completed.status === "error" || completed.status === "failed" || completed.error) ? "error" : "complete";
    }

    const liveStatus = agentUpdates[agentId]?.status;
    if (liveStatus === "error" || liveStatus === "failed") return "error";
    if (liveStatus === "running") return "running";
    
    const isSupported = isAgentSupportedForMime(agentId, mimeType);
    if (!isSupported) return "waiting"; // Should not happen for visible agents

    if (agentUpdates[agentId]) return "running";
    if (isQueuePending) return "queued";
    if (pipelineStatus === "analyzing" || pipelineStatus === "initiating" || pipelineStatus === "processing") {
      return "checking";
    }
    return "waiting";
  };

  const containerVariants: import("framer-motion").Variants = {
    hidden: {},
    show: { transition: { staggerChildren: 0.18, delayChildren: 0.1 } },
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


  return (
    <div
      className="flex flex-col w-full max-w-[1560px] mx-auto gap-8 pb-24 pt-24"
      aria-label="Agent forensic analysis progress"
    >
      <div className="flex flex-col md:flex-row items-start justify-between gap-10 w-full mb-12 px-2">
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
              <div className="w-2 h-2 rounded-full bg-[var(--color-primary)] animate-pulse shadow-[0_0_15px_rgba(var(--color-primary-rgb),0.5)]" />
              <p className="text-[10px] font-mono font-bold text-[var(--color-primary)] tracking-[0.3em] uppercase">
                {phase === "initial" ? "Initial_Verification" : "Deep_Analysis"}
              </p>
            </div>
            <div className="w-[1px] h-3 bg-white/10" />
            <p className="text-sm font-medium text-white/40 italic" role="status" aria-live="polite" aria-atomic="false">
              {pipelineMessage || (allAgentsDone ? "Analysis phase complete" : progressText || "Coordination in progress")}
            </p>
          </div>
        </div>

        <div className="flex-shrink-0">
          <AgentStatusSummary 
            visibleAgents={visibleAgents}
            skippedAgents={skippedAgents}
            agentUpdates={agentUpdates}
            completedAgents={completedAgents}
          />
        </div>
      </div>


      <div className="w-full">
        <motion.div
          className={`grid gap-5 ${
            visibleAgents.length === 1 ? "grid-cols-1 max-w-xl mx-auto"
            : visibleAgents.length === 2 ? "grid-cols-1 md:grid-cols-2"
            : "grid-cols-1 md:grid-cols-2 lg:grid-cols-3"
          }`}
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
                  thinking={agentUpdates[agent.id]?.thinking || pipelineMessage || progressText}
                  liveUpdate={agentUpdates[agent.id]}
                  completedData={completedAgents?.find((c) => c.agent_id === agent.id)}
                  phase={phase}
                  isExpanded={!!expandedCards[agent.id]}
                  onToggleExpand={() => setExpandedCards(prev => ({ ...prev, [agent.id]: !prev[agent.id] }))}
                  onAnimationStart={() => playSoundRef.current?.("card_reveal")}
                />
              </motion.div>
            ))}
            </AnimatePresence>

            {/* Arbiter Pre-warming / Active Card */}
            <AnimatePresence>
              {(hasStartedAnalysis || awaitingDecision || arbiterStatus || arbiterDeliberating) && (
                <motion.div
                  key="arbiter-card"
                  layout
                  initial={{ opacity: 0, scale: 0.9, y: 20 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.8, transition: { duration: 0.3 } }}
                >
                  <ArbiterCard 
                    status={arbiterDeliberating ? "synthesizing" : arbiterStatus}
                    thinking={arbiterThinking || progressText}
                    phase={phase}
                    allAgentsDone={allAgentsDone}
                  />
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
      </div>

      <AnimatePresence>
        {awaitingDecision && phase === "initial" && revealQueue.length === 0 && !arbiterDeliberating && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="w-full max-w-2xl mx-auto px-6 py-8"
          >
            <div className="glass-panel p-2 rounded-full shadow-[0_40px_100px_rgba(0,0,0,0.8)] border-white/10">
              <div className="bg-[#020203]/80 rounded-full p-2 flex items-center gap-3">
                <button
                  data-testid="accept-analysis-btn"
                  onClick={onAcceptAnalysis}
                  disabled={isNavigating}
                  className="flex-1 btn-horizon-outline py-3 text-xs flex items-center justify-center gap-2"
                >
                  {isNavigating ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                  <span>Accept Result</span>
                </button>
                <button
                  data-testid="deep-analysis-btn"
                  onClick={onRunDeepAnalysis}
                  disabled={isNavigating || (phase as string) === "deep"}
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
        {phase === "deep" && revealQueue.length === 0 && (allAgentsDone || pipelineStatus === "complete") && !arbiterDeliberating && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="w-full max-w-2xl mx-auto px-6 py-8"
          >
            <div className="glass-panel p-2 rounded-full shadow-[0_40px_100px_rgba(0,0,0,0.8)] border-white/10">
              <div className="bg-[#020203]/80 rounded-full p-2 flex items-center gap-3">
                <button
                  data-testid="new-analysis-btn"
                  aria-label="New investigation"
                  onClick={onNewUpload}
                  className="flex-1 btn-horizon-outline py-3 text-xs"
                >
                  New Analysis
                </button>
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

"use client";

import React, { useState, useEffect, useMemo } from "react";
import {
  Loader2,
  FileText,
  ArrowRight,
  Activity,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { AGENTS as AGENTS_DATA } from "@/lib/constants";
import { storage } from "@/lib/storage";
import { isAgentSupportedForMime, supportedAgentIdsForMime } from "@/lib/agentSupport";
import { AgentStatusCard } from "./AgentStatusCard";
import { AgentStatusSummary } from "./AgentStatusSummary";
import { ArbiterCard } from "./ArbiterCard";
import type { SoundType } from "@/hooks/useSound";
import type { AgentUpdate } from "./types";

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
  arbiterDeliberating?: boolean;
  arbiterStatus?: string | null;
  arbiterThinking?: string | null;
  hasStartedAnalysis?: boolean;
  overlayVisible?: boolean;
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
  revealQueue = [],
  arbiterDeliberating = false,
  arbiterStatus = null,
  arbiterThinking = null,
  hasStartedAnalysis = false,
}: AgentProgressDisplayProps) {
  const [expandedCards, setExpandedCards] = useState<Record<string, boolean>>({});
  const [headerCollapsed, setHeaderCollapsed] = useState(false);

  useEffect(() => {
    if (!mimeType) return;
    setExpandedCards({});
  }, [mimeType]);

  const initialAgentIds = useMemo<string[]>(() => {
    if (phase !== "deep") return [];
    const sid = storage.getItem("forensic_session_id");
    if (sid) {
      const raw = storage.getItem<AgentUpdate[]>(`forensic_initial_agents:${sid}`, true);
      if (Array.isArray(raw) && raw.length) {
        return (raw as AgentUpdate[])
          .filter((a) => a.status !== "skipped")
          .map((a) => a.agent_id)
          .filter((id): id is string => typeof id === "string");
      }
    }
    const fromMime = Array.from(supportedAgentIdsForMime(mimeType || undefined));
    if (fromMime.length) return fromMime;
    return allValidAgents.map(a => a.id);
  }, [phase, mimeType]);

  const visibleAgents = useMemo((): Agent[] => {
    return allValidAgents
      .filter((a): boolean => {
        const completed = completedAgents?.find((c) => c.agent_id === a.id);
        const liveStatus = agentUpdates[a.id]?.status;
        if (completed?.status === "skipped" || liveStatus === "skipped") return false;
        const agentVerdict = (completed as unknown as { agent_verdict?: unknown })?.agent_verdict;
        if (agentVerdict === "NOT_APPLICABLE") return false;
        if (phase === "deep") return initialAgentIds.includes(a.id);
        if (!mimeType) return true;
        return isAgentSupportedForMime(a.id, mimeType);
      });
  }, [phase, initialAgentIds, mimeType, completedAgents, agentUpdates]);

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
    if (liveStatus === "skipped") return "unsupported";
    if (liveStatus === "complete") return "complete";
    if (liveStatus === "validating") return "validating";
    if (liveStatus === "running") return "running";

    const isSupported = isAgentSupportedForMime(agentId, mimeType);
    if (!isSupported) {
      return agentUpdates[agentId] ? "unsupported" : "waiting";
    }

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
    hidden: { opacity: 0, y: 4 },
    show: {
      opacity: 1,
      y: 0,
      transition: { duration: 0.16, ease: "easeOut" },
    },
  };


  return (
    <div
      className="flex flex-col w-full max-w-screen-2xl mx-auto gap-8 pb-24 pt-12"
      aria-label="Agent forensic analysis progress"
    >
      {/* Pipeline header */}
      <div className="w-full px-2 mb-4">
        {/* Always-visible row: title + summary + toggle */}
        <div className="flex items-start justify-between gap-6 w-full">
          <motion.h1
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.16, ease: "easeOut" }}
            className="text-5xl md:text-6xl font-heading font-bold text-white tracking-tight pt-1"
          >
            Analysis Pipeline
          </motion.h1>

          <div className="flex items-start gap-4 shrink-0">
            {/* Summary always visible — primary status signal */}
            <AgentStatusSummary
              visibleAgents={visibleAgents}
              skippedAgents={skippedAgents}
              agentUpdates={agentUpdates}
              completedAgents={completedAgents}
            />

            {/* Collapse toggle — only hides the phase/progress text row */}
            <button
              type="button"
              onClick={() => setHeaderCollapsed(v => !v)}
              aria-expanded={!headerCollapsed}
              aria-controls="pipeline-header-panel"
              className="flex items-center gap-1.5 fc-text-faint hover:text-white/60 transition-colors mt-2 shrink-0"
            >
              <span className="text-xs font-mono hidden sm:block">
                {headerCollapsed ? "Expand" : "Collapse"}
              </span>
              {headerCollapsed
                ? <ChevronDown className="w-4 h-4" />
                : <ChevronUp className="w-4 h-4" />
              }
            </button>
          </div>
        </div>

        {/* Collapsible: phase badge + progress text only */}
        <AnimatePresence initial={false}>
          {!headerCollapsed && (
            <motion.div
              id="pipeline-header-panel"
              key="pipeline-header-panel"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2, ease: "easeInOut" }}
              className="overflow-hidden"
            >
              <div className="flex items-center gap-4 mt-3">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                  <span className="fc-badge fc-badge-active text-xs">
                    {phase === "initial" ? "Initial Verification" : "Deep Analysis"}
                  </span>
                </div>
                <div className="w-[1px] h-3 bg-white/10" />
                <p className="text-sm font-medium fc-text-faint italic" role="status" aria-live="polite" aria-atomic="false">
                  {pipelineMessage || (allAgentsDone ? "Analysis phase complete" : progressText || "Coordination in progress")}
                </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>


      <div className="w-full flex flex-col gap-5">
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
                exit={{ opacity: 0, transition: { duration: 0.16 } }}
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
                />
              </motion.div>
            ))}
          </AnimatePresence>
        </motion.div>

        {/* Arbiter card — separate row below the agent grid, centered */}
        <AnimatePresence>
          {(hasStartedAnalysis || awaitingDecision || arbiterStatus || arbiterDeliberating) && (
            <motion.div
              key="arbiter-card"
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, transition: { duration: 0.16 } }}
              className="w-full max-w-lg mx-auto"
            >
              <ArbiterCard
                status={arbiterDeliberating ? "synthesizing" : arbiterStatus}
                thinking={
                  arbiterThinking ||
                  (arbiterDeliberating
                    ? "Council Arbiter is synthesizing agent findings into the final report."
                    : null)
                }
                phase={phase}
                allAgentsDone={allAgentsDone}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <AnimatePresence>
        {awaitingDecision && phase === "initial" && revealQueue.length === 0 && !arbiterDeliberating && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            className="w-full max-w-2xl mx-auto px-4 sm:px-6 pb-8"
          >
            <div className="fc-surface-elevated rounded-2xl px-4 py-4">
              <p className="text-center fc-eyebrow fc-text-muted mb-4">
                Initial analysis complete — choose your next step
              </p>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  data-testid="accept-analysis-btn"
                  onClick={onAcceptAnalysis}
                  disabled={isNavigating}
                  aria-label="Accept initial analysis and generate final report"
                  className="flex-1 fc-btn-secondary flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isNavigating ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                  <span>Accept Result</span>
                </button>
                <button
                  type="button"
                  data-testid="deep-analysis-btn"
                  onClick={onRunDeepAnalysis}
                  disabled={isNavigating}
                  aria-label="Run deep neural analysis with advanced models"
                  className="flex-[1.5] fc-btn-primary flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isNavigating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Activity className="w-4 h-4" />}
                  <span>Deep Analysis</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {phase === "deep" && revealQueue.length === 0 && (awaitingDecision || pipelineStatus === "awaiting_decision") && !arbiterDeliberating && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            className="w-full max-w-2xl mx-auto px-4 sm:px-6 pb-8"
          >
            <div className="fc-surface-elevated rounded-2xl px-4 py-4">
              <p className="text-center fc-eyebrow fc-text-muted mb-4">
                Deep analysis complete — view report or start a new investigation
              </p>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  data-testid="new-analysis-btn"
                  aria-label="Start a new investigation"
                  onClick={onNewUpload}
                  className="flex-1 fc-btn-secondary flex items-center justify-center gap-2"
                >
                  New Analysis
                </button>
                <button
                  type="button"
                  data-testid="view-report-btn"
                  onClick={onViewResults}
                  disabled={isNavigating}
                  aria-label="View the final forensic report"
                  className="flex-[1.5] fc-btn-primary flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isNavigating ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
                  <span>View Report</span>
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

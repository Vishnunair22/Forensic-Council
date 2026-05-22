"use client";

import React, { useState, useEffect, useMemo } from "react";
import {
  Loader2,
  FileText,
  ArrowRight,
  Activity,
  ChevronDown,
  ChevronUp,
  MinusCircle,
  Cpu,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { clsx } from "clsx";
import { AGENTS as AGENTS_DATA } from "@/lib/constants";
import { storage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";
import { isAgentSupportedForMime, supportedAgentIdsForMime } from "@/lib/agentSupport";
import { accentFor } from "@/lib/agentTheme";
import { getLiveProgressDescriptor } from "@/lib/tool-progress";
import { AgentStatusCard, AGENT_ICONS } from "./AgentStatusCard";
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
  overlayVisible?: boolean;
}

type Agent = typeof AGENTS_DATA[number];
const allValidAgents: Agent[] = AGENTS_DATA.filter((agent) => agent.id !== "Arbiter");

type AgentStatus = "waiting" | "queued" | "checking" | "running" | "complete" | "error" | "unsupported" | "validating";

const ALERT_VERDICTS = new Set([
  "FLAGGED", "SUSPICIOUS", "TAMPERED", "NEEDS_REVIEW",
  "LIKELY_MANIPULATED", "LIKELY_AI_GENERATED", "LIKELY_SPOOFED", "LIKELY_SYNTHETIC",
]);

function normalizeVerdict(v?: string): string {
  if (!v) return "Pending";
  return v.replace(/_/g, " ").toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
}

// ─── Active Agents Panel ────────────────────────────────────────────────────

interface ActiveAgentsPanelProps {
  visibleAgents: Agent[];
  agentUpdates: AgentProgressDisplayProps["agentUpdates"];
  completedAgents: AgentUpdate[];
  getAgentStatus: (id: string) => AgentStatus;
}

function ActiveAgentsPanel({ visibleAgents, agentUpdates, completedAgents, getAgentStatus }: ActiveAgentsPanelProps) {
  const [expanded, setExpanded] = useState(true);

  const doneCount = visibleAgents.filter(a => {
    const s = getAgentStatus(a.id);
    return s === "complete" || s === "error";
  }).length;

  return (
    <div className="fc-surface-quiet rounded-2xl overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        aria-expanded={expanded}
        aria-controls="active-agents-panel"
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-white/2 transition-colors"
      >
        <div className="flex items-center gap-2.5">
          <Activity className="w-3.5 h-3.5 text-primary shrink-0" />
          <span className="fc-eyebrow fc-text-secondary">Active Agents</span>
          <span className="fc-badge fc-badge-active">{visibleAgents.length}</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono fc-text-faint tabular-nums">
            {doneCount}/{visibleAgents.length}
          </span>
          {expanded
            ? <ChevronUp className="w-3.5 h-3.5 fc-text-faint" />
            : <ChevronDown className="w-3.5 h-3.5 fc-text-faint" />}
        </div>
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            id="active-agents-panel"
            key="active-agents-panel"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.16, ease: "easeOut" }}
            className="overflow-hidden border-t border-white/5"
          >
            {visibleAgents.map((agent) => {
              const status = getAgentStatus(agent.id);
              const liveUpdate = agentUpdates[agent.id];
              const completed = completedAgents?.find(c => c.agent_id === agent.id);
              const accent = accentFor(agent.id);
              const Icon = AGENT_ICONS[agent.id] ?? Cpu;
              const toolDesc = getLiveProgressDescriptor(
                agent.id,
                liveUpdate?.tool_name,
                liveUpdate?.tools_done ?? 0,
              );
              const isAlert =
                ALERT_VERDICTS.has(completed?.agent_verdict ?? "") ||
                (completed?.verdict_score ?? 0) > 0.6;

              return (
                <div
                  key={agent.id}
                  className="flex items-center gap-3 px-5 py-3 border-b border-white/4 last:border-0"
                >
                  {/* Status dot */}
                  <div className="shrink-0 w-1.5 h-1.5">
                    {status === "running" && (
                      <motion.div
                        className="w-1.5 h-1.5 rounded-full bg-primary"
                        animate={{ opacity: [1, 0.3, 1] }}
                        transition={{ duration: 1.2, repeat: Infinity }}
                      />
                    )}
                    {status === "complete" && <div className="w-1.5 h-1.5 rounded-full bg-success" />}
                    {status === "error" && <div className="w-1.5 h-1.5 rounded-full bg-danger" />}
                    {(status === "waiting" || status === "queued" || status === "checking" || status === "validating") && (
                      <div className="w-1.5 h-1.5 rounded-full bg-white/15" />
                    )}
                  </div>

                  {/* Agent icon */}
                  <Icon className={clsx("w-3.5 h-3.5 shrink-0", accent.textClass)} />

                  {/* Name + live status */}
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium fc-text-secondary leading-none">{agent.name}</p>
                    <p className="text-xs fc-text-faint mt-1 truncate leading-none">
                      {status === "running" && toolDesc.label}
                      {status === "checking" && "Synchronizing with pipeline..."}
                      {status === "validating" && "Verifying chain of custody..."}
                      {status === "complete" && completed && (
                        `${normalizeVerdict(completed.agent_verdict)} · ${Math.round((completed.confidence ?? 0) * 100)}%`
                      )}
                      {status === "queued" && "Queued — awaiting worker"}
                      {status === "waiting" && "Standby"}
                      {status === "error" && "Analysis error"}
                    </p>
                  </div>

                  {/* Right: confidence */}
                  {status === "complete" && completed?.confidence != null && (
                    <span className={clsx(
                      "text-xs font-mono font-bold tabular-nums shrink-0",
                      isAlert ? "text-danger" :
                      completed.agent_verdict === "INCONCLUSIVE" ? "text-warning" :
                      "text-success"
                    )}>
                      {Math.round(completed.confidence * 100)}%
                    </span>
                  )}
                </div>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Skipped Agents Panel ────────────────────────────────────────────────────

interface SkippedAgentsPanelProps {
  skippedAgents: Agent[];
  mimeType?: string;
}

function SkippedAgentsPanel({ skippedAgents, mimeType }: SkippedAgentsPanelProps) {
  const [expanded, setExpanded] = useState(true);

  const mimeCategory = mimeType?.split("/")?.[0] ?? "this";
  const reason = `Not applicable for ${mimeCategory} files`;

  return (
    <div className="fc-surface-quiet rounded-2xl overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        aria-expanded={expanded}
        aria-controls="skipped-agents-panel"
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-white/2 transition-colors"
      >
        <div className="flex items-center gap-2.5">
          <MinusCircle className="w-3.5 h-3.5 fc-text-faint shrink-0" />
          <span className="fc-eyebrow fc-text-muted">Skipped Agents</span>
          <span className="fc-badge">{skippedAgents.length}</span>
        </div>
        {expanded
          ? <ChevronUp className="w-3.5 h-3.5 fc-text-faint" />
          : <ChevronDown className="w-3.5 h-3.5 fc-text-faint" />}
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            id="skipped-agents-panel"
            key="skipped-agents-panel"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.16, ease: "easeOut" }}
            className="overflow-hidden border-t border-white/5"
          >
            {skippedAgents.map((agent) => {
              const Icon = AGENT_ICONS[agent.id] ?? Cpu;

              return (
                <div
                  key={agent.id}
                  className="flex items-center gap-3 px-5 py-3 border-b border-white/4 last:border-0"
                >
                  <div className="w-1.5 h-1.5 rounded-full bg-white/10 shrink-0" />
                  <Icon className="w-3.5 h-3.5 shrink-0 fc-text-faint" />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium fc-text-muted leading-none">{agent.name}</p>
                    <p className="text-xs fc-text-faint mt-1 leading-none">{reason}</p>
                  </div>
                  <span className="fc-eyebrow fc-text-faint shrink-0">N/A</span>
                </div>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────

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
}: AgentProgressDisplayProps) {
  const [expandedCards, setExpandedCards] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!mimeType) return;
    setExpandedCards({});
  }, [mimeType]);

  const initialAgentIds = useMemo<string[]>(() => {
    if (phase !== "deep") return [];
    const sid = storage.getItem(STORAGE_KEYS.SESSION_ID);
    if (sid) {
      const raw = storage.getItem<AgentUpdate[]>(`${STORAGE_KEYS.INITIAL_AGENTS}:${sid}`, true);
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

  const statusText = pipelineMessage || (allAgentsDone ? "Analysis phase complete" : progressText || "Coordination in progress");

  return (
    <div
      className="flex flex-col w-full max-w-screen-2xl mx-auto gap-8 pb-24 pt-12"
      aria-label="Agent forensic analysis progress"
    >
      {/* ── Page Header ─────────────────────────────────────────────────── */}
      <div className="w-full px-2">
        {/* Title + phase badge + live status */}
        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.16, ease: "easeOut" }}
          className="flex flex-wrap items-center gap-3 mb-5"
        >
          <h1 className="text-3xl md:text-4xl font-heading font-bold fc-text-primary tracking-tight">
            {phase === "deep" ? "Deep Analysis" : "Forensic Analysis"}
          </h1>
          <span className="fc-badge fc-badge-active">
            {phase === "initial" ? "Initial Verification" : "Phase 2"}
          </span>
          <p
            className="text-sm font-medium fc-text-faint italic ml-auto hidden md:block"
            role="status"
            aria-live="polite"
            aria-atomic="false"
          >
            {statusText}
          </p>
        </motion.div>

        {/* Active + Skipped panels */}
        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.16, delay: 0.05, ease: "easeOut" }}
          className={clsx(
            "grid gap-4",
            skippedAgents.length > 0 ? "grid-cols-1 md:grid-cols-2" : "grid-cols-1"
          )}
        >
          <ActiveAgentsPanel
            visibleAgents={visibleAgents}
            agentUpdates={agentUpdates}
            completedAgents={completedAgents}
            getAgentStatus={getAgentStatus}
          />
          {skippedAgents.length > 0 && (
            <SkippedAgentsPanel
              skippedAgents={skippedAgents}
              mimeType={mimeType}
            />
          )}
        </motion.div>
      </div>

      {/* ── Agent Cards Grid ────────────────────────────────────────────── */}
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

      </div>

      {/* ── Initial analysis decision gate ──────────────────────────────── */}
      <AnimatePresence>
        {awaitingDecision && phase === "initial" && revealQueue.length === 0 && !arbiterDeliberating && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            transition={{ duration: 0.16 }}
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
                  className="flex-1 fc-btn-secondary flex items-center justify-center gap-2"
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
                  className="flex-[1.5] fc-btn-primary flex items-center justify-center gap-2"
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

      {/* ── Deep analysis decision gate ──────────────────────────────────── */}
      <AnimatePresence>
        {phase === "deep" && revealQueue.length === 0 && (awaitingDecision || pipelineStatus === "awaiting_decision") && !arbiterDeliberating && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            transition={{ duration: 0.16 }}
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
                  className="flex-[1.5] fc-btn-primary flex items-center justify-center gap-2"
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

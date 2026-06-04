"use client";

import React, { useState, useEffect, useMemo, useRef } from "react";
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
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { clsx } from "clsx";
import { AGENTS as AGENTS_DATA } from "@/lib/constants";
import { storage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";
import { isAgentSupportedForMime, supportedAgentIdsForMime, type ServerCapabilities } from "@/lib/agentSupport";
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
  capabilities?: ServerCapabilities | null;
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
  const str = typeof v === "string" ? v : String(v);
  return str.replace(/_/g, " ").toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
}

// ─── Active Agents Panel ────────────────────────────────────────────────────

interface ActiveAgentsPanelProps {
  visibleAgents: Agent[];
  agentUpdates: AgentProgressDisplayProps["agentUpdates"];
  completedAgents: AgentUpdate[];
  getAgentStatus: (id: string) => AgentStatus;
  expanded?: boolean;
  setExpanded?: React.Dispatch<React.SetStateAction<boolean>>;
}

function ActiveAgentsPanel({
  visibleAgents = [],
  agentUpdates: _agentUpdates = {},
  completedAgents: _completedAgents = [],
  getAgentStatus,
  expanded = false,
  setExpanded,
}: ActiveAgentsPanelProps) {
  const prefersReducedMotion = useReducedMotion();
  const agentUpdates = _agentUpdates || {};
  const completedAgents = _completedAgents;

  const doneCount = visibleAgents.filter(a => {
    const s = getAgentStatus(a.id);
    return s === "complete" || s === "error";
  }).length;

  return (
    <div className="fc-surface-quiet rounded-2xl overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded?.(v => !v)}
        aria-expanded={expanded}
        aria-controls="active-agents-panel"
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-white/5 fc-transition fc-focus-ring rounded-2xl"
      >
        <div className="flex items-center gap-2.5">
          <Activity className="w-4 h-4 text-primary shrink-0" />
          <span className="fc-eyebrow fc-text-secondary">Active Agents</span>
          <span className="fc-badge fc-badge-active">{visibleAgents.length}</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm font-mono fc-text-muted tabular-nums">
            {doneCount}/{visibleAgents.length}
          </span>
          {expanded
            ? <ChevronUp className="w-4 h-4 fc-text-muted" />
            : <ChevronDown className="w-4 h-4 fc-text-muted" />}
        </div>
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            id="active-agents-panel"
            key="active-agents-panel"
            initial={prefersReducedMotion ? false : { height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={prefersReducedMotion ? {} : { height: 0, opacity: 0 }}
            transition={{ duration: 0.16, ease: "easeOut" }}
            className="overflow-hidden border-t border-white/5"
          >
            {visibleAgents.map((agent) => {
              const status = getAgentStatus(agent.id);
              const liveUpdate = agentUpdates[agent.id];
              const completed = completedAgents.find(c => c.agent_id === agent.id);
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
                  <div className="shrink-0 w-2 h-2">
                    {status === "running" && (
                      <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                    )}
                    {status === "complete" && <div className="w-2 h-2 rounded-full bg-success" />}
                    {status === "error" && <div className="w-2 h-2 rounded-full bg-danger" />}
                    {(status === "waiting" || status === "queued" || status === "checking" || status === "validating") && (
                      <div className="w-2 h-2 rounded-full bg-white/20" />
                    )}
                  </div>

                  {/* Agent icon */}
                  <Icon className={clsx("w-4 h-4 shrink-0", accent.textClass)} />

                  {/* Name + live status */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium fc-text-primary leading-none">{agent.name}</p>
                    <p className="text-sm fc-text-secondary mt-1 truncate leading-none">
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
  agentUpdates: Record<string, { status: string; thinking: string; tools_done?: number; tools_total?: number; tool_name?: string }>;
  mimeType?: string;
}

function SkippedAgentsPanel({ skippedAgents, agentUpdates, mimeType }: SkippedAgentsPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const prefersReducedMotion = useReducedMotion();

  const mimeCategory = mimeType?.split("/")?.[0] ?? "this";
  const fallbackReason = `Not applicable for ${mimeCategory} files`;
  const getReason = (agentId: string) => agentUpdates[agentId]?.thinking || fallbackReason;

  return (
    <div className="fc-surface-quiet rounded-2xl overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        aria-expanded={expanded}
        aria-controls="skipped-agents-panel"
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-white/5 fc-transition fc-focus-ring rounded-2xl"
      >
        <div className="flex items-center gap-2.5">
          <MinusCircle className="w-4 h-4 fc-text-muted shrink-0" />
          <span className="fc-eyebrow fc-text-muted">Skipped Agents</span>
          <span className="fc-badge">{skippedAgents.length}</span>
        </div>
        {expanded
          ? <ChevronUp className="w-4 h-4 fc-text-muted" />
          : <ChevronDown className="w-4 h-4 fc-text-muted" />}
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            id="skipped-agents-panel"
            key="skipped-agents-panel"
            initial={prefersReducedMotion ? false : { height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={prefersReducedMotion ? {} : { height: 0, opacity: 0 }}
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
                  <Icon className="w-4 h-4 shrink-0 fc-text-muted" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium fc-text-secondary leading-none">{agent.name}</p>
                    <p className="text-sm fc-text-muted mt-1 leading-none">{getReason(agent.id)}</p>
                  </div>
                  <span className="fc-eyebrow fc-text-muted shrink-0">N/A</span>
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
  agentUpdates = {},
  completedAgents = [],
  progressText = "",
  allAgentsDone = false,
  phase = "initial",
  awaitingDecision = false,
  pipelineStatus = "idle",
  pipelineMessage = "",
  onNewUpload,
  onViewResults,
  onAcceptAnalysis,
  onRunDeepAnalysis,
  isNavigating = false,
  mimeType,
  capabilities,
  revealQueue = [],
  arbiterDeliberating = false,
}: AgentProgressDisplayProps) {
  const prefersReducedMotion = useReducedMotion();
  const [activeAgentsExpanded, setActiveAgentsExpanded] = useState(false);
  const [isBootstrapping, setIsBootstrapping] = useState(() =>
    (typeof process !== "undefined" && process.env.NODE_ENV === "test") || typeof jest !== "undefined" ? false : true
  );



  useEffect(() => {
    const timer = setTimeout(() => {
      setIsBootstrapping(false);
    }, 400);
    return () => clearTimeout(timer);
  }, []);

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
    const fromMime = Array.from(supportedAgentIdsForMime(mimeType || undefined, capabilities));
    if (fromMime.length) return fromMime;
    return allValidAgents.map(a => a.id);
  }, [phase, mimeType, capabilities]);

  const visibleAgents = useMemo((): Agent[] => {
      return allValidAgents
        .filter((a): boolean => {
          const completed = completedAgents.find((c) => c.agent_id === a.id);
          const liveStatus = agentUpdates[a.id]?.status;
        if (completed?.status === "skipped" || liveStatus === "skipped") return false;
        const agentVerdict = (completed as unknown as { agent_verdict?: unknown })?.agent_verdict;
        if (agentVerdict === "NOT_APPLICABLE") return false;
        if (phase === "deep") return initialAgentIds.includes(a.id);
        if (!mimeType) return true;
        return isAgentSupportedForMime(a.id, mimeType, capabilities);
      });
  }, [phase, initialAgentIds, mimeType, capabilities, completedAgents, agentUpdates]);

  const skippedAgents = useMemo(() => {
    if (!mimeType) return [];
    return allValidAgents.filter(a => {
      const completed = completedAgents.find((c) => c.agent_id === a.id);
      const liveStatus = agentUpdates[a.id]?.status;
      const isSkippedOrUnsupported = completed?.status === "skipped" || liveStatus === "skipped" || liveStatus === "unsupported";
      return !isAgentSupportedForMime(a.id, mimeType, capabilities) || isSkippedOrUnsupported;
    });
  }, [mimeType, capabilities, completedAgents, agentUpdates]);

  const isQueuePending = /queue|queued|enqueued|awaiting available forensic worker|waiting for an available forensic worker/i.test(
    `${pipelineMessage || ""} ${progressText || ""}`
  );

  const getAgentStatus = (agentId: string): AgentStatus => {
    const completed = completedAgents.find((c) => c.agent_id === agentId);
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

  // Throttled SR-only text so screen readers aren't overwhelmed by rapid pipeline updates
  const srTextRef = useRef<string>("");
  const srThrottleRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [srText, setSrText] = useState("");
  useEffect(() => {
    if (statusText === srTextRef.current) return;
    srTextRef.current = statusText;
    if (srThrottleRef.current) clearTimeout(srThrottleRef.current);
    srThrottleRef.current = setTimeout(() => setSrText(statusText), 2000);
    return () => {
      if (srThrottleRef.current) clearTimeout(srThrottleRef.current);
    };
  }, [statusText]);

  return (
    <div
      className="flex flex-col w-full max-w-7xl mx-auto gap-8 pb-16 pt-2"
      aria-label="Agent forensic analysis progress"
    >
      {/* ── Page Header ─────────────────────────────────────────────────── */}
      <div className="w-full">
        {/* Title + phase badge + live status */}
        <motion.div
          initial={prefersReducedMotion ? false : { opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.16, ease: "easeOut" }}
          className="flex flex-wrap items-center gap-3 mb-5"
        >
          <h1 className="text-3xl md:text-5xl lg:text-6xl font-heading font-extrabold fc-text-primary text-hero-gradient tracking-tight leading-tight">
            {allAgentsDone && phase === "initial"
              ? "Initial Analysis"
              : phase === "deep"
              ? "Deep Analysis"
              : "Analysis Pipeline"}
          </h1>
          <span className={clsx(
            "fc-badge",
            allAgentsDone && phase === "initial" ? "fc-badge-success" : "fc-badge-active"
          )}>
            {allAgentsDone && phase === "initial"
              ? "Complete"
              : phase === "initial"
              ? "Initial Verification"
              : "Phase 2"}
          </span>
          <p className="text-sm font-normal fc-text-secondary w-full md:w-auto md:ml-auto" aria-hidden="true">
            {statusText}
          </p>
          {/* Throttled SR announcement — updates at most once per 2 s to prevent read-every-frame */}
          <p role="status" aria-live="polite" aria-atomic="true" className="sr-only">
            {srText}
          </p>
        </motion.div>

        {/* Active + Skipped panels */}
        <motion.div
          initial={prefersReducedMotion ? false : { opacity: 0, y: 4 }}
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
            expanded={activeAgentsExpanded}
            setExpanded={setActiveAgentsExpanded}
          />
          {skippedAgents.length > 0 && (
            <SkippedAgentsPanel
              skippedAgents={skippedAgents}
              agentUpdates={agentUpdates}
              mimeType={mimeType}
            />
          )}
        </motion.div>
      </div>

      {/* ── Agent Cards Grid ────────────────────────────────────────────── */}
      <div className="w-full flex flex-col gap-5">
        <motion.div
          className={`grid gap-4 md:gap-5 xl:gap-6 ${
            visibleAgents.length === 1 ? "grid-cols-1 max-w-xl mx-auto"
            : visibleAgents.length === 2 ? "grid-cols-1 md:grid-cols-2"
            : "grid-cols-1 md:grid-cols-2 xl:grid-cols-3"
          }`}
          variants={containerVariants}
          initial="hidden"
          animate="show"
        >
          <AnimatePresence mode="popLayout">
            {isBootstrapping ? (
              visibleAgents.map((agent) => (
                <div
                  key={`skeleton-${agent.id}`}
                  className="w-full h-40 rounded-2xl bg-white/5 border border-white/5 p-5 flex flex-col gap-4 relative overflow-hidden"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-white/5 fc-skeleton" />
                    <div className="flex-1 flex flex-col gap-2">
                      <div className="h-4 bg-white/10 rounded w-1/3 fc-skeleton" />
                      <div className="h-3 bg-white/5 rounded w-1/2 fc-skeleton" />
                    </div>
                  </div>
                  <div className="flex-1 mt-2">
                    <div className="h-3 bg-white/5 rounded w-full fc-skeleton" />
                    <div className="h-3 bg-white/5 rounded w-5/6 mt-2 fc-skeleton" />
                  </div>
                </div>
              ))
            ) : (
              visibleAgents.map((agent) => (
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
                    completedData={completedAgents.find((c) => c.agent_id === agent.id)}
                    phase={phase}
                  />
                </motion.div>
              ))
            )}
          </AnimatePresence>
        </motion.div>
      </div>

      {/* ── Elevated Initial Analysis Decision Gate ──────────────────────────────── */}
      <AnimatePresence>
        {awaitingDecision && revealQueue.length === 0 && !arbiterDeliberating && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, filter: "blur(4px)" }}
            animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0, scale: 1.05, filter: "blur(4px)" }}
            transition={{ type: "spring", stiffness: 300, damping: 25 }}
            className="w-full max-w-2xl mx-auto px-4 sm:px-6 pb-8 relative z-20"
          >
            <div className="fc-surface-elevated rounded-2xl p-6 md:p-8">
              <div className="flex items-center justify-center gap-3 mb-4">
                <Activity className="w-4 h-4 text-primary" aria-hidden="true" />
                <p className="text-center text-sm font-semibold fc-text-primary">
                  Decision Required
                </p>
              </div>

              <p className="text-center text-sm fc-text-secondary mb-6 max-w-md mx-auto">
                Baseline verification complete. Accept the current findings or run deep-model analysis for higher confidence.
              </p>

              <div className="flex flex-col sm:flex-row items-center gap-4">
                <button
                  type="button"
                  data-testid="accept-analysis-btn"
                  onClick={onAcceptAnalysis}
                  disabled={isNavigating}
                  className="w-full sm:flex-1 fc-btn-secondary flex items-center justify-center gap-2 h-12"
                >
                  {isNavigating ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                  <span>Accept Baseline</span>
                </button>

                <button
                  type="button"
                  data-testid="deep-analysis-btn"
                  onClick={onRunDeepAnalysis}
                  disabled={isNavigating}
                  className="w-full sm:flex-[1.5] relative fc-btn-primary flex items-center justify-center gap-2 h-12"
                >
                  <span className="flex items-center gap-2">
                    {isNavigating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Cpu className="w-4 h-4" />}
                    <span>Authorize Deep Analysis</span>
                    <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                  </span>
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Deep analysis decision gate ──────────────────────────────────── */}
      <AnimatePresence>
        {phase === "deep" && revealQueue.length === 0 && completedAgents.length > 0 && pipelineStatus === "awaiting_decision" && !isNavigating && !arbiterDeliberating && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, filter: "blur(4px)" }}
            animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0, scale: 1.05, filter: "blur(4px)" }}
            transition={{ type: "spring", stiffness: 300, damping: 25 }}
            className="w-full max-w-2xl mx-auto px-4 sm:px-6 pb-8"
          >
            <div className="fc-surface-elevated rounded-2xl px-4 py-4">
              <p className="text-center text-sm fc-text-secondary mb-4">
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

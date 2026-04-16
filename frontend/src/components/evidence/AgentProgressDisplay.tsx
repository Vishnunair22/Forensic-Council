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
import { AGENTS as AGENTS_DATA } from "@/lib/constants";
import { SoundType } from "@/hooks/useSound";
import { AgentStatusCard } from "./AgentStatusCard";
import { ForensicTimeline } from "./ForensicTimeline";

export interface FindingPreview {
  tool: string;
  summary: string;
  verdict?: "CLEAN" | "FLAGGED" | "ERROR" | "NOT_APPLICABLE";
  severity?: "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  elapsed_s?: number;
  confidence?: number;
  key_signal?: string;
  section?: string;
  verdict_score?: number;
}

export interface AgentUpdate {
  agent_id: string;
  agent_name?: string;
  status?: string;
  message?: string;
  error?: string;
  completed_at?: string;
  tools_ran?: number;
  findings_count?: number;
  findings_preview?: FindingPreview[];
  agent_verdict?: string;
  confidence?: number;
  tool_error_rate?: number;
  tools_skipped?: number;
  tools_failed?: number;
  deep_analysis_pending?: boolean;
  section_flags?: string[];
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

const allValidAgents = AGENTS_DATA.filter((a) => a.name !== "Council Arbiter");

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
  playSound,
  isNavigating = false,
  mimeType,
}: AgentProgressDisplayProps) {
  const [revealedAgents, setRevealedAgents] = useState<Set<string>>(new Set());
  const [skippedAgentIds, setSkippedAgentIds] = useState<Set<string>>(new Set());
  const [showTimeline, setShowTimeline] = useState(false);

  // Track which agents are unsupported (for skipped count only — they stay in the grid)
  useEffect(() => {
    completedAgents.forEach((agent) => {
      const isUnsupported = agent.status === "skipped" ||
        (agent.error && /not applicable|not supported|skipping|skipped/i.test(agent.error));
      if (isUnsupported && !skippedAgentIds.has(agent.agent_id)) {
        setSkippedAgentIds(prev => new Set([...prev, agent.agent_id]));
      }
    });
  }, [completedAgents, skippedAgentIds]);

  // Stagger-reveal agent cards on mount / phase change
  useEffect(() => {
    setRevealedAgents(new Set());
    if (!allValidAgents.length) return;
    let idx = 0;
    const id = setInterval(() => {
      if (idx >= allValidAgents.length) { clearInterval(id); return; }
      const aid = allValidAgents[idx]?.id;
      if (aid) {
        setRevealedAgents((prev: Set<string>) => new Set([...prev, aid]));
        if (playSound) playSound(idx === 0 ? "scan" : "agent");
      }
      idx++;
    }, 100);
    return () => clearInterval(id);
  }, [phase, playSound]);

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
    if (revealedAgents.has(agentId)) return "checking";
    return "waiting";
  };

  // Show initial decision dock when backend signals pause OR all agents are done
  // (allAgentsDone fallback handles cases where PIPELINE_PAUSED isn't received)
  const showInitialDecision = phase === "initial" && (awaitingDecision || allAgentsDone);
  const showDeepComplete = phase === "deep" && (allAgentsDone || pipelineStatus === "complete");

  // Metrics — exclude skipped agents from trust/threat
  const activeCompleted = completedAgents.filter((a) => {
    const skip = a.status === "skipped" || (a.error ? /not applicable|not supported|skipping|skipped/i.test(a.error) : false);
    return !skip;
  });
  const avgTrust = activeCompleted.length > 0
    ? activeCompleted.reduce((s, c) => s + (c.confidence || 0), 0) / activeCompleted.length
    : 0;
  const totalFlagged = activeCompleted.reduce((s, c) => s + (c.findings_count || 0), 0);
  const hasErrors = activeCompleted.some((a) => a.error && !/not applicable|not supported|skipping|skipped/i.test(a.error));

  void avgTrust; // consumed by status badge in future; suppress unused warning

  const threat =
    totalFlagged > 0 ? { label: "ELEVATED", color: "text-rose-400" }
    : hasErrors     ? { label: "DEGRADED",  color: "text-amber-400" }
                    : { label: "NOMINAL",   color: "text-emerald-400" };

  void threat;

  const runningCount = Object.keys(agentUpdates).filter(id => !completedAgents.some(c => c.agent_id === id)).length;
  const finishedCount = completedAgents.filter(a => {
    const skip = a.status === "skipped" || (a.error ? /not applicable|not supported|skipping|skipped/i.test(a.error) : false);
    return !skip;
  }).length;
  const skippedCount = skippedAgentIds.size;
  const alertCount = totalFlagged;

  return (
    <div className="flex flex-col w-full max-w-[1400px] mx-auto pt-8 gap-10 pb-32">

      {/* ── Compact Header ────────────────────────────────────────────────── */}
      <div className="glass-panel p-6 rounded-2xl mt-6 w-full relative overflow-hidden max-w-4xl mx-auto">
        <div className="absolute inset-0 bg-cyan-500/5 mix-blend-overlay pointer-events-none" />
        <div className="flex flex-col items-center justify-center text-center gap-3 relative z-10">
          <motion.h1
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="text-4xl md:text-5xl font-bold text-white tracking-tighter uppercase font-heading"
          >
            Evidence Analysis
          </motion.h1>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 }}
            className="flex flex-col sm:flex-row items-center justify-center gap-3 px-6 py-2.5 rounded-full glass-panel"
          >
            <div className="flex items-center justify-center gap-2">
              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse shadow-[0_0_10px_rgba(34,211,238,0.8)]" />
              <span className="text-[11px] font-black uppercase tracking-[0.3em] text-cyan-400">
                {phase === "deep" ? "Deep Analysis" : "Initial Analysis"}
              </span>
            </div>
            <div className="hidden sm:block w-px h-4 bg-white/20" />
            <span className="text-[11px] font-mono font-black text-white/80 uppercase tracking-widest">
               {allAgentsDone ? `${allValidAgents.length}/${allValidAgents.length} FINISHED` : `${finishedCount}/${allValidAgents.length} FINISHED • ${runningCount} RUNNING`}
            </span>
          </motion.div>
        </div>

        <p className="text-[11px] text-white/40 font-mono font-medium uppercase tracking-[0.4em] max-w-2xl mx-auto relative z-10 mt-4 text-center">
          {">> "}{pipelineMessage || progressText}
        </p>
      </div>

      {/* ── Agent Cards Grid ──────────────────────────────────────────────── */}
      <div className="w-full max-w-6xl mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {allValidAgents.map((agent) => (
            <AgentStatusCard
              key={agent.id}
              agentId={agent.id}
              name={agent.name}
              badge={agent.badge}
              status={getAgentStatus(agent.id)}
              thinking={agentUpdates[agent.id]?.thinking}
              completedData={completedAgents.find((c) => c.agent_id === agent.id)}
              isRevealed={revealedAgents.has(agent.id)}
              fileMime={mimeType}
            />
          ))}
        </div>
      </div>

      {/* ── Status Row + View Ledger ──────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-6 glass-panel p-6 rounded-2xl w-full max-w-6xl mx-auto">
        <div className="flex items-center gap-8">
          {[
            { label: "Running",  value: runningCount,  color: "text-cyan-400" },
            { label: "Finished", value: finishedCount, color: "text-emerald-400" },
            { label: "Skipped",  value: skippedCount,  color: "text-white/20" },
            { label: "Alerts",   value: alertCount,    color: alertCount > 0 ? "text-rose-400" : "text-white/10" },
          ].map((s) => (
            <div key={s.label} className="flex flex-col items-center">
              <span className={clsx("text-xl font-black font-heading leading-none", s.color)}>{s.value}</span>
              <span className="text-[8px] font-black uppercase tracking-[0.2em] text-white/20 mt-1">{s.label}</span>
            </div>
          ))}
        </div>

        <button
          onClick={() => setShowTimeline(!showTimeline)}
          className={clsx(
            "flex items-center gap-3 px-8 py-3 rounded-full border transition-all duration-300 font-bold tracking-widest text-[10px] uppercase",
            showTimeline
              ? "bg-cyan-500/20 border-cyan-500/50 text-cyan-300 shadow-[0_0_20px_rgba(34,211,238,0.2)]"
              : "glass-panel hover:border-white/30 text-white/70"
          )}
        >
          <FileText className="w-4 h-4" />
          <span>{showTimeline ? "Hide Ledger" : "View Ledger"}</span>
          <div className={clsx("w-2 h-2 rounded-full", showTimeline ? "bg-cyan-400 animate-pulse" : "bg-white/20")} />
        </button>
      </div>

      {/* ── Evidence Ledger (Timeline) — Collapsible ─────────────────────── */}
      <AnimatePresence>
        {showTimeline && (
          <motion.div
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

      {/* ── Universal Bottom Dock ─────────────────────────────────────────── */}
      <AnimatePresence>
        {(showInitialDecision || showDeepComplete) && (
          <motion.div
            initial={{ opacity: 0, y: "100%" }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 200 }}
            className="fixed bottom-0 left-0 right-0 z-50 glass-dock pb-8 pt-6 px-6 pointer-events-auto shadow-[0_-20px_50px_rgba(0,0,0,0.8)] flex flex-col items-center justify-center text-center"
          >
            <div className="flex flex-col items-center max-w-4xl mx-auto gap-4">
              <div className="flex flex-col flex-1 items-center justify-center">
                <span className="flex items-center justify-center gap-2 text-[11px] font-black text-cyan-400 uppercase tracking-[0.2em] mb-1">
                  <div className="w-2 h-2 bg-cyan-400 rounded-full animate-pulse blur-[1px]" />
                  Pipeline Resolved
                </span>
                <span className="text-[13px] text-white/70 font-medium tracking-tight">
                  {showInitialDecision
                    ? "Initial triage complete. Cryptographic signatures established."
                    : "Deep analysis complete. All forensic signals verified and sealed."}
                </span>
              </div>

              <div className="flex items-center justify-center gap-6 mt-2 flex-wrap">
                {showInitialDecision ? (
                  <>
                    <button
                      onClick={onAcceptAnalysis}
                      disabled={isNavigating}
                      className="btn-pill-secondary px-8"
                    >
                      {isNavigating ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                      Accept Analysis
                    </button>
                    <button
                      onClick={onDeepAnalysis}
                      disabled={isNavigating}
                      className="btn-pill-primary group px-8"
                    >
                      <Microscope className="w-4 h-4" />
                      Deep Analysis
                      <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={onNewUpload}
                      className="btn-pill-secondary px-8"
                    >
                      <RotateCcw className="w-4 h-4" />
                      New Investigation
                    </button>
                    <button
                      onClick={onViewResults}
                      disabled={isNavigating}
                      className="btn-pill-primary group px-8"
                    >
                      {isNavigating ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
                      View Results
                      <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
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

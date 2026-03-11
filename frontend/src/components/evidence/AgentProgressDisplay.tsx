/**
 * AgentProgressDisplay Component
 * =============================
 *
 * Shows all 5 agents in a card grid with real-time status,
 * findings text, and decision buttons after each analysis phase.
 * 
 * Features:
 * - Staggered card loading (3s between each agent)
 * - "Checking file type..." message for initial state
 * - Unsupported file type detection with card fade-out after 10s
 */

import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle2, AlertTriangle, Loader2, ArrowRight, RotateCcw, Microscope, FileText, FileX } from "lucide-react";
import { AgentIcon } from "@/components/ui/AgentIcon";
import { AGENTS_DATA } from "@/lib/constants";
import { useState, useEffect } from "react";

export interface AgentUpdate {
  agent_id: string;
  agent_name: string;
  message: string;
  status: "running" | "complete" | "error";
  confidence?: number;
  findings_count?: number;
  thinking?: string;
  error?: string | null;
  deep_analysis_pending?: boolean;
}

interface AgentProgressDisplayProps {
  key?: React.Key;
  agentUpdates: Record<string, { status: string; thinking: string }>;
  completedAgents: AgentUpdate[];
  progressText: string;
  allAgentsDone: boolean;
  phase: "initial" | "deep";
  awaitingDecision: boolean;
  onAcceptAnalysis?: () => void;
  onDeepAnalysis?: () => void;
  onNewUpload?: () => void;
  onViewResults?: () => void;
}

export function AgentProgressDisplay({
  agentUpdates,
  completedAgents,
  progressText,
  allAgentsDone,
  phase,
  awaitingDecision,
  onAcceptAnalysis,
  onDeepAnalysis,
  onNewUpload,
  onViewResults,
}: AgentProgressDisplayProps) {
  const validAgentsData = AGENTS_DATA.filter(a => a.name !== "Council Arbiter");

  // Guard against empty validAgentsData at render time
  const hasValidAgents = validAgentsData && validAgentsData.length > 0;
  const firstAgentId = hasValidAgents ? validAgentsData[0].id : null;

  // Track which agents have been "revealed" (staggered loading)
  const [revealedAgents, setRevealedAgents] = useState<Set<string>>(new Set());

  // Track unsupported agents (show as N/A, never hidden)
  const [unsupportedAgents, setUnsupportedAgents] = useState<Set<string>>(new Set());

  // Staggered loading: reveal one agent every 3 seconds
  useEffect(() => {
    // Reset on phase change
    if (phase === "initial") {
      setRevealedAgents(new Set());
      setUnsupportedAgents(new Set());
    }

    // Reveal agents one by one (only if we have valid agents)
    if (!hasValidAgents || !firstAgentId) {
      return; // No agents to reveal
    }

    let currentIndex = 0;
    const revealInterval = setInterval(() => {
      // Guard against empty validAgentsData or index out of bounds
      if (!validAgentsData || validAgentsData.length === 0 || currentIndex >= validAgentsData.length) {
        clearInterval(revealInterval);
        return;
      }
      const agentId = validAgentsData[currentIndex]?.id;
      if (agentId) {
        setRevealedAgents(prev => new Set([...prev, agentId]));
      }
      currentIndex++;
    }, 3000); // 3 seconds between each agent

    // Immediately reveal first agent (guard against empty array)
    if (firstAgentId) {
      setRevealedAgents(new Set([firstAgentId]));
    }

    return () => clearInterval(revealInterval);
  }, [phase, hasValidAgents, firstAgentId]);

  // Detect unsupported agents — mark them but never hide them
  useEffect(() => {
    completedAgents.forEach(agent => {
      const isUnsupported = agent.error?.includes("not supported") ||
        agent.error?.includes("Format not supported") ||
        agent.message?.includes("not supported") ||
        agent.message?.includes("Skipped") ||
        (agent.findings_count === 0 && agent.confidence === 0 && agent.error);

      if (isUnsupported && !unsupportedAgents.has(agent.agent_id)) {
        setUnsupportedAgents(prev => new Set([...prev, agent.agent_id]));
      }
    });
  }, [completedAgents, unsupportedAgents]);

  const getAgentStatus = (agentId: string): "waiting" | "checking" | "running" | "complete" | "error" | "unsupported" => {
    // Check if marked as unsupported (always show, never hide)
    if (unsupportedAgents.has(agentId)) return "unsupported";

    const completed = completedAgents.find(c => c.agent_id === agentId);
    if (completed) {
      // Check if it's an unsupported format error
      const isUnsupported = completed.error?.includes("not supported") ||
        completed.error?.includes("Format not supported") ||
        completed.message?.includes("not supported") ||
        completed.message?.includes("Skipped");
      if (isUnsupported) return "unsupported";
      return completed.error ? "error" : "complete";
    }

    if (agentUpdates[agentId]) return "running";

    // If revealed but no update yet, show "checking"
    if (revealedAgents.has(agentId)) return "checking";

    return "waiting";
  };

  const getAgentThinking = (agentId: string): string => {
    return agentUpdates[agentId]?.thinking || "";
  };

  const getAgentFindings = (agentId: string): AgentUpdate | undefined => {
    return completedAgents.find(c => c.agent_id === agentId);
  };

  // Count only active/supported agents
  const activeCompletedCount = completedAgents.filter(c =>
    !unsupportedAgents.has(c.agent_id)
  ).length;

  const visibleAgentsCount = validAgentsData.length;

  // Show decision buttons after initial analysis OR after deep analysis
  const showInitialDecision = awaitingDecision && phase === "initial";
  const showDeepComplete = allAgentsDone && phase === "deep";

  return (
    <motion.div
      key="progress"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className="flex flex-col items-center pt-8"
    >
      {/* Header */}
      <div className="text-center mb-8">
        <h2 className="text-2xl font-bold text-white mb-2">
          {showInitialDecision
            ? "Initial Analysis Complete"
            : showDeepComplete
              ? "Deep Analysis Complete"
              : "Evidence Analysis"}
        </h2>
        <p className="text-sm text-slate-400">
          {showInitialDecision || showDeepComplete
            ? `${activeCompletedCount} of ${visibleAgentsCount} agents reported`
            : `${activeCompletedCount}/${visibleAgentsCount} agents complete`}
        </p>
      </div>

      {/* Agent Cards Grid */}
      <div className="w-full max-w-5xl grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {validAgentsData.map((agent, i) => {
          const status = getAgentStatus(agent.id);
          const thinking = getAgentThinking(agent.id);
          const completed = getAgentFindings(agent.id);
          const isRevealed = revealedAgents.has(agent.id);

          return (
            <AnimatePresence key={agent.id}>
              {isRevealed && (
                <motion.div
                  initial={{ opacity: 0, y: 20, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -10, scale: 0.95 }}
                  transition={{ duration: 0.5, delay: 0.1 }}
                  className={`
                    relative rounded-xl border p-5 transition-colors duration-300
                    ${status === "running"
                      ? "bg-cyan-500/[0.04] border-cyan-500/25"
                      : status === "complete"
                        ? "bg-white/[0.03] border-emerald-500/20"
                        : status === "error"
                          ? "bg-red-500/[0.04] border-red-500/20"
                          : status === "unsupported"
                            ? "bg-amber-500/[0.04] border-amber-500/20"
                            : status === "checking"
                              ? "bg-purple-500/[0.04] border-purple-500/20"
                              : "bg-white/[0.02] border-white/[0.08]"
                    }
                  `}
                >
                  {/* Top row: Icon + Name + Status badge */}
                  <div className="flex items-center gap-3 mb-3">
                    <div className={`
                      w-10 h-10 rounded-lg flex items-center justify-center shrink-0
                      ${status === "running"
                        ? "bg-cyan-500/15 text-cyan-400"
                        : status === "complete"
                          ? "bg-emerald-500/15 text-emerald-400"
                          : status === "error"
                            ? "bg-red-500/15 text-red-400"
                            : status === "unsupported"
                              ? "bg-amber-500/15 text-amber-400"
                              : status === "checking"
                                ? "bg-purple-500/15 text-purple-400"
                                : "bg-white/5 text-slate-500"
                      }
                    `}>
                      <AgentIcon agentId={agent.id} className="w-5 h-5" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="text-sm font-semibold text-white truncate">{agent.name}</h3>
                      <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">
                        {agent.role}
                      </span>
                    </div>
                    <div className="shrink-0">
                      {status === "waiting" && (
                        <span className="inline-flex items-center gap-1.5 text-[11px] text-slate-500 font-medium">
                          <span className="w-1.5 h-1.5 rounded-full bg-slate-600" />
                          Waiting
                        </span>
                      )}
                      {status === "checking" && (
                        <span className="inline-flex items-center gap-1.5 text-[11px] text-purple-400 font-medium">
                          <Loader2 className="w-3 h-3 animate-spin" />
                          Checking
                        </span>
                      )}
                      {status === "running" && (
                        <span className="inline-flex items-center gap-1.5 text-[11px] text-cyan-400 font-medium">
                          <Loader2 className="w-3 h-3 animate-spin" />
                          Active
                        </span>
                      )}
                      {status === "complete" && (
                        <span className="inline-flex items-center gap-1.5 text-[11px] text-emerald-400 font-medium">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          Done
                        </span>
                      )}
                      {status === "error" && (
                        <span className="inline-flex items-center gap-1.5 text-[11px] text-red-400 font-medium">
                          <AlertTriangle className="w-3.5 h-3.5" />
                          Error
                        </span>
                      )}
                      {status === "unsupported" && (
                        <span className="inline-flex items-center gap-1.5 text-[11px] text-amber-400 font-medium">
                          <FileX className="w-3.5 h-3.5" />
                          Skipped
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Checking file type message */}
                  {status === "checking" && (
                    <p className="text-xs text-purple-300/70 leading-relaxed">
                      Checking file type compatibility...
                    </p>
                  )}

                  {/* Thinking text (shown when running) */}
                  {status === "running" && thinking && (
                    <p className="text-xs text-cyan-300/70 leading-relaxed line-clamp-2">
                      {thinking}
                    </p>
                  )}

                  {/* Findings summary (shown when complete) */}
                  {status === "complete" && completed && (
                    <div className="space-y-2">
                      <p className="text-xs text-slate-300 leading-relaxed line-clamp-3">
                        {completed.message || "Analysis complete."}
                      </p>
                      <div className="flex items-center gap-3 text-[11px] text-slate-500">
                        {completed.findings_count !== undefined && (
                          <span>{completed.findings_count} finding{completed.findings_count !== 1 ? "s" : ""}</span>
                        )}
                        {completed.confidence !== undefined && (
                          <span>· {Math.round(completed.confidence * 100)}% conf.</span>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Unsupported file type message */}
                  {status === "unsupported" && completed && (
                    <div className="space-y-2">
                      <p className="text-xs text-amber-300/70 leading-relaxed">
                        {completed.message || completed.error || "File type not supported for this agent."}
                      </p>
                      <p className="text-[10px] text-amber-400/50 italic">
                        Not applicable for this evidence type.
                      </p>
                    </div>
                  )}

                  {/* Waiting message */}
                  {status === "waiting" && (
                    <p className="text-xs text-slate-600">Queued for analysis</p>
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          );
        })}
      </div>

      {/* === Decision Buttons === */}

      {/* After initial analysis: Accept Analysis / Deep Analysis */}
      {showInitialDecision && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="mt-10 w-full max-w-lg flex gap-4"
        >
          <button
            onClick={onAcceptAnalysis}
            className="flex-1 flex items-center justify-center gap-2 px-5 py-4 rounded-xl
              bg-emerald-600/20 border border-emerald-500/30 text-emerald-300
              hover:bg-emerald-600/35 hover:border-emerald-500/50
              transition-all font-semibold text-sm"
          >
            <FileText className="w-4 h-4" />
            Accept Analysis
          </button>
          <button
            onClick={onDeepAnalysis}
            className="flex-1 flex items-center justify-center gap-2 px-5 py-4 rounded-xl
              bg-cyan-600/20 border border-cyan-500/30 text-cyan-300
              hover:bg-cyan-600/35 hover:border-cyan-500/50
              transition-all font-semibold text-sm"
          >
            <Microscope className="w-4 h-4" />
            Deep Analysis
            <ArrowRight className="w-4 h-4" />
          </button>
        </motion.div>
      )}

      {/* After deep analysis: New File / View Results */}
      {showDeepComplete && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="mt-10 w-full max-w-lg flex gap-4"
        >
          <button
            onClick={onNewUpload}
            className="flex-1 flex items-center justify-center gap-2 px-5 py-4 rounded-xl
              bg-white/[0.04] border border-white/[0.10] text-slate-300
              hover:bg-white/[0.08] hover:border-white/20 hover:text-white
              transition-all font-semibold text-sm"
          >
            <RotateCcw className="w-4 h-4" />
            New File
          </button>
          <button
            onClick={onViewResults}
            className="flex-1 flex items-center justify-center gap-2 px-5 py-4 rounded-xl
              bg-emerald-600/20 border border-emerald-500/30 text-emerald-300
              hover:bg-emerald-600/35 hover:border-emerald-500/50
              transition-all font-semibold text-sm"
          >
            <FileText className="w-4 h-4" />
            View Results
            <ArrowRight className="w-4 h-4" />
          </button>
        </motion.div>
      )}

      {/* Running progress indicator (only when agents are still working) */}
      {!showInitialDecision && !showDeepComplete && (
        <div className="mt-8 text-center">
          <p className="text-sm text-slate-400">{progressText}</p>
          {!allAgentsDone && (
            <div className="flex justify-center gap-1 mt-3">
              {[0, 1, 2].map((i) => (
                <motion.div
                  key={i}
                  animate={{ opacity: [0.3, 1, 0.3] }}
                  transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.2 }}
                  className="w-1.5 h-1.5 rounded-full bg-cyan-400"
                />
              ))}
            </div>
          )}
        </div>
      )}
    </motion.div>
  );
}

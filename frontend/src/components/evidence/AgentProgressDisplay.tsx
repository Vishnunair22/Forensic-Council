/**
 * AgentProgressDisplay Component
 * =============================
 *
 * Shows all 5 agents in a card grid with real-time status,
 * findings text, and decision buttons after each analysis phase.
 */

import { motion } from "framer-motion";
import { CheckCircle2, AlertTriangle, Loader2, ArrowRight, RotateCcw, Microscope, FileText } from "lucide-react";
import { AgentIcon } from "@/components/ui/AgentIcon";
import { AGENTS_DATA } from "@/lib/constants";

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
  onNewAnalysis?: () => void;
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
  onNewAnalysis,
  onViewResults,
}: AgentProgressDisplayProps) {
  const validAgentsData = AGENTS_DATA.filter(a => a.name !== "Council Arbiter");

  const getAgentStatus = (agentId: string): "waiting" | "running" | "complete" | "error" => {
    const completed = completedAgents.find(c => c.agent_id === agentId);
    if (completed) return completed.error ? "error" : "complete";
    if (agentUpdates[agentId]) return "running";
    return "waiting";
  };

  const getAgentThinking = (agentId: string): string => {
    return agentUpdates[agentId]?.thinking || "";
  };

  const getAgentFindings = (agentId: string): AgentUpdate | undefined => {
    return completedAgents.find(c => c.agent_id === agentId);
  };

  const completedCount = completedAgents.filter(c =>
    validAgentsData.some(v => v.id === c.agent_id)
  ).length;

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
            ? `${completedCount} of ${validAgentsData.length} agents reported`
            : `${completedCount}/${validAgentsData.length} agents complete`}
        </p>
      </div>

      {/* Agent Cards Grid */}
      <div className="w-full max-w-5xl grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {validAgentsData.map((agent, i) => {
          const status = getAgentStatus(agent.id);
          const thinking = getAgentThinking(agent.id);
          const completed = getAgentFindings(agent.id);

          return (
            <motion.div
              key={agent.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.06 }}
              className={`
                relative rounded-xl border p-5 transition-colors duration-300
                ${status === "running"
                  ? "bg-cyan-500/[0.04] border-cyan-500/25"
                  : status === "complete"
                    ? "bg-white/[0.03] border-emerald-500/20"
                    : status === "error"
                      ? "bg-red-500/[0.04] border-red-500/20"
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
                </div>
              </div>

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

              {/* Waiting message */}
              {status === "waiting" && (
                <p className="text-xs text-slate-600">Queued for analysis</p>
              )}
            </motion.div>
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

      {/* After deep analysis: New Analysis / View Results */}
      {showDeepComplete && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="mt-10 w-full max-w-lg flex gap-4"
        >
          <button
            onClick={onNewAnalysis}
            className="flex-1 flex items-center justify-center gap-2 px-5 py-4 rounded-xl
              bg-white/[0.04] border border-white/[0.10] text-slate-300
              hover:bg-white/[0.08] hover:border-white/20 hover:text-white
              transition-all font-semibold text-sm"
          >
            <RotateCcw className="w-4 h-4" />
            New Analysis
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

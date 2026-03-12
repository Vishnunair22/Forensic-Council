/**
 * AgentProgressDisplay Component
 * =============================
 *
 * Shows agent cards in a grid with real-time status, findings text, and
 * decision buttons after each analysis phase.
 *
 * Behaviour per phase:
 *   initial — all 5 cards stagger in (3 s apart); unsupported agents show amber "Skipped"
 *   deep    — ONLY supported agents shown (unsupported ones hidden); they stagger in fresh
 */

import { motion, AnimatePresence } from "framer-motion";
import {
  CheckCircle2, AlertTriangle, Loader2, ArrowRight,
  RotateCcw, Microscope, FileText, FileX,
} from "lucide-react";
import { AgentIcon } from "@/components/ui/AgentIcon";
import { AGENTS_DATA } from "@/lib/constants";
import { useState, useEffect, useRef } from "react";
import { SoundType } from "@/hooks/useSound";

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
  pipelineStatus?: string;
  onAcceptAnalysis?: () => void;
  onDeepAnalysis?: () => void;
  onNewUpload?: () => void;
  onViewResults?: () => void;
  playSound?: (type: SoundType) => void;
  isNavigating?: boolean;
}

export function AgentProgressDisplay({
  agentUpdates,
  completedAgents,
  progressText,
  allAgentsDone,
  phase,
  awaitingDecision,
  pipelineStatus,
  onAcceptAnalysis,
  onDeepAnalysis,
  onNewUpload,
  onViewResults,
  playSound,
  isNavigating = false,
}: AgentProgressDisplayProps) {
  const allValidAgents = AGENTS_DATA.filter(a => a.name !== "Council Arbiter");

  // Track unsupported agents (populated from AGENT_COMPLETE messages)
  const [unsupportedAgents, setUnsupportedAgents] = useState<Set<string>>(new Set());

  // In deep phase: only show supported agents; initial phase shows all
  const visibleAgents = phase === "deep"
    ? allValidAgents.filter(a => !unsupportedAgents.has(a.id))
    : allValidAgents;

  const hasVisibleAgents = visibleAgents.length > 0;
  const firstVisibleAgent = visibleAgents[0];
  const firstVisibleId = firstVisibleAgent ? firstVisibleAgent.id : null;

  // Stagger reveal state
  const [revealedAgents, setRevealedAgents] = useState<Set<string>>(new Set());
  const prevRevealedRef = useRef<Set<string>>(new Set());

  // Play ascending chime when a new card appears
  useEffect(() => {
    if (!playSound) return;
    revealedAgents.forEach(id => {
      if (!prevRevealedRef.current.has(id)) {
        playSound("agent");
      }
    });
    prevRevealedRef.current = new Set(revealedAgents);
  }, [revealedAgents, playSound]);

  // Stagger effect — resets on phase change
  useEffect(() => {
    setRevealedAgents(new Set());
    prevRevealedRef.current = new Set();

    if (!hasVisibleAgents || !firstVisibleId) return;

    // Immediately reveal first card
    setRevealedAgents(new Set([firstVisibleId]));

    let currentIndex = 1;
    const id = setInterval(() => {
      if (currentIndex >= visibleAgents.length) { clearInterval(id); return; }
      const agentId = visibleAgents[currentIndex]?.id;
      if (agentId) setRevealedAgents(prev => new Set([...prev, agentId]));
      currentIndex++;
    }, 3000);

    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, visibleAgents.length, firstVisibleId]);

  // Detect unsupported agents
  useEffect(() => {
    completedAgents.forEach(agent => {
      const isUnsupported =
        agent.error?.includes("not supported") ||
        agent.error?.includes("Format not supported") ||
        agent.message?.includes("not supported") ||
        agent.message?.includes("Skipped") ||
        (agent.findings_count === 0 && agent.confidence === 0 && !!agent.error);
      if (isUnsupported && !unsupportedAgents.has(agent.agent_id)) {
        setUnsupportedAgents(prev => new Set([...prev, agent.agent_id]));
      }
    });
  }, [completedAgents, unsupportedAgents]);

  const getAgentStatus = (agentId: string): "waiting" | "checking" | "running" | "complete" | "error" | "unsupported" => {
    if (unsupportedAgents.has(agentId)) return "unsupported";
    const completed = completedAgents.find(c => c.agent_id === agentId);
    if (completed) {
      const isUnsupported =
        completed.error?.includes("not supported") ||
        completed.error?.includes("Format not supported") ||
        completed.message?.includes("not supported") ||
        completed.message?.includes("Skipped");
      if (isUnsupported) return "unsupported";
      return completed.error ? "error" : "complete";
    }
    if (agentUpdates[agentId]) return "running";
    if (revealedAgents.has(agentId)) return "checking";
    return "waiting";
  };

  const getAgentThinking = (agentId: string) => agentUpdates[agentId]?.thinking || "";
  const getAgentFindings = (agentId: string) => completedAgents.find(c => c.agent_id === agentId);

  const activeCompletedCount = completedAgents.filter(c => !unsupportedAgents.has(c.agent_id)).length;
  const visibleAgentsCount = visibleAgents.length;

  const showInitialDecision = awaitingDecision && phase === "initial";
  const showDeepComplete = phase === "deep" && (allAgentsDone || pipelineStatus === "complete");

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
              : phase === "deep"
                ? "Deep Analysis Running"
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
        {visibleAgents.map((agent) => {
          const status = getAgentStatus(agent.id);
          const thinking = getAgentThinking(agent.id);
          const completed = getAgentFindings(agent.id);
          const isRevealed = revealedAgents.has(agent.id);

          return (
            <AnimatePresence key={agent.id}>
              {isRevealed && (
                <motion.div
                  initial={{ opacity: 0, y: 30, scale: 0.88 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -10, scale: 0.95 }}
                  transition={{ type: "spring", stiffness: 260, damping: 20 }}
                  className={`
                    relative rounded-xl border p-5 transition-colors duration-300 overflow-hidden
                    ${status === "running" ? "bg-cyan-500/[0.04] border-cyan-500/25"
                      : status === "complete" ? "bg-white/[0.03] border-emerald-500/20"
                      : status === "error" ? "bg-red-500/[0.04] border-red-500/20"
                      : status === "unsupported" ? "bg-amber-500/[0.04] border-amber-500/20"
                      : status === "checking" ? "bg-purple-500/[0.04] border-purple-500/20"
                      : "bg-white/[0.02] border-white/[0.08]"}
                  `}
                >
                  {/* Scan-sweep on entry */}
                  <motion.div
                    initial={{ x: "-100%", opacity: 0.7 }}
                    animate={{ x: "200%", opacity: 0 }}
                    transition={{ duration: 0.7, ease: "easeOut", delay: 0.05 }}
                    className="absolute inset-y-0 w-1/2 bg-gradient-to-r from-transparent via-white/10 to-transparent pointer-events-none z-10"
                  />

                  {/* Top row */}
                  <div className="flex items-center gap-3 mb-3">
                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0
                      ${status === "running" ? "bg-cyan-500/15 text-cyan-400"
                        : status === "complete" ? "bg-emerald-500/15 text-emerald-400"
                        : status === "error" ? "bg-red-500/15 text-red-400"
                        : status === "unsupported" ? "bg-amber-500/15 text-amber-400"
                        : status === "checking" ? "bg-purple-500/15 text-purple-400"
                        : "bg-white/5 text-slate-500"}
                    `}>
                      <AgentIcon agentId={agent.id} className="w-5 h-5" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="text-sm font-semibold text-white truncate">{agent.name}</h3>
                      <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">{agent.role}</span>
                    </div>
                    <div className="shrink-0">
                      {status === "waiting" && <span className="inline-flex items-center gap-1.5 text-[11px] text-slate-500 font-medium"><span className="w-1.5 h-1.5 rounded-full bg-slate-600" />Waiting</span>}
                      {status === "checking" && <span className="inline-flex items-center gap-1.5 text-[11px] text-purple-400 font-medium"><Loader2 className="w-3 h-3 animate-spin" />Initiating</span>}
                      {status === "running" && <span className="inline-flex items-center gap-1.5 text-[11px] text-cyan-400 font-medium"><Loader2 className="w-3 h-3 animate-spin" />Active</span>}
                      {status === "complete" && <span className="inline-flex items-center gap-1.5 text-[11px] text-emerald-400 font-medium"><CheckCircle2 className="w-3.5 h-3.5" />Done</span>}
                      {status === "error" && <span className="inline-flex items-center gap-1.5 text-[11px] text-red-400 font-medium"><AlertTriangle className="w-3.5 h-3.5" />Error</span>}
                      {status === "unsupported" && <span className="inline-flex items-center gap-1.5 text-[11px] text-amber-400 font-medium"><FileX className="w-3.5 h-3.5" />Skipped</span>}
                    </div>
                  </div>

                  {/* Body */}
                  {status === "checking" && <p className="text-xs text-purple-300/70 leading-relaxed">Initiating analysis...</p>}
                  {status === "running" && <p className="text-xs text-cyan-300/70 leading-relaxed line-clamp-3">{thinking || "Analyzing evidence..."}</p>}
                  {status === "complete" && completed && (
                    <div className="space-y-2">
                      <p className="text-xs text-slate-300 leading-relaxed line-clamp-3">{completed.message || "Analysis complete."}</p>
                      <div className="flex items-center gap-3 text-[11px] text-slate-500">
                        {completed.findings_count !== undefined && <span>{completed.findings_count} finding{completed.findings_count !== 1 ? "s" : ""}</span>}
                        {completed.confidence !== undefined && <span>· {Math.round(completed.confidence * 100)}% conf.</span>}
                      </div>
                    </div>
                  )}
                  {status === "unsupported" && completed && (
                    <div className="space-y-2">
                      <p className="text-xs text-amber-300/70 leading-relaxed">{completed.message || completed.error || "File type not supported."}</p>
                      <p className="text-[10px] text-amber-400/50 italic">Not applicable for this evidence type.</p>
                    </div>
                  )}
                  {status === "error" && completed && <p className="text-xs text-red-300/70 leading-relaxed line-clamp-2">{completed.error || "An error occurred."}</p>}
                  {status === "waiting" && <p className="text-xs text-slate-600">Queued for analysis</p>}
                </motion.div>
              )}
            </AnimatePresence>
          );
        })}
      </div>

      {/* Decision Buttons */}

      {/* After initial analysis */}
      {showInitialDecision && (
        <motion.div
          initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
          className="mt-10 w-full max-w-lg flex gap-4"
        >
          <button onClick={onAcceptAnalysis}
            disabled={isNavigating}
            className="flex-1 flex items-center justify-center gap-2 px-5 py-4 rounded-xl
              bg-emerald-600/20 border border-emerald-500/30 text-emerald-300
              hover:bg-emerald-600/35 hover:border-emerald-500/50 transition-all font-semibold text-sm
              disabled:opacity-60 disabled:cursor-not-allowed">
            {isNavigating ? (
              <><Loader2 className="w-4 h-4 animate-spin" />Compiling Report...</>
            ) : (
              <><FileText className="w-4 h-4" />Accept Analysis</>
            )}
          </button>
          <button onClick={onDeepAnalysis}
            disabled={isNavigating}
            className="flex-1 flex items-center justify-center gap-2 px-5 py-4 rounded-xl
              bg-cyan-600/20 border border-cyan-500/30 text-cyan-300
              hover:bg-cyan-600/35 hover:border-cyan-500/50 transition-all font-semibold text-sm
              disabled:opacity-60 disabled:cursor-not-allowed">
            <Microscope className="w-4 h-4" />
            Deep Analysis
            <ArrowRight className="w-4 h-4" />
          </button>
        </motion.div>
      )}

      {/* After deep analysis */}
      {showDeepComplete && (
        <motion.div
          initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
          className="mt-10 w-full max-w-lg flex gap-4"
        >
          <button onClick={onNewUpload}
            disabled={isNavigating}
            className="flex-1 flex items-center justify-center gap-2 px-5 py-4 rounded-xl
              bg-white/[0.04] border border-white/[0.10] text-slate-300
              hover:bg-white/[0.08] hover:border-white/20 hover:text-white
              transition-all font-semibold text-sm
              disabled:opacity-60 disabled:cursor-not-allowed">
            <RotateCcw className="w-4 h-4" />
            New Analysis
          </button>
          <button onClick={onViewResults}
            disabled={isNavigating}
            className="flex-1 flex items-center justify-center gap-2 px-5 py-4 rounded-xl
              bg-gradient-to-r from-emerald-600/30 to-cyan-600/20
              border border-emerald-500/40 text-emerald-300
              hover:from-emerald-600/50 hover:to-cyan-600/35
              hover:shadow-[0_0_20px_rgba(52,211,153,0.2)]
              transition-all font-semibold text-sm
              disabled:opacity-60 disabled:cursor-not-allowed">
            {isNavigating ? (
              <><Loader2 className="w-4 h-4 animate-spin" />Compiling Report...</>
            ) : (
              <><FileText className="w-4 h-4" />View Results<ArrowRight className="w-4 h-4" /></>
            )}
          </button>
        </motion.div>
      )}

      {/* Still running */}
      {!showInitialDecision && !showDeepComplete && (
        <div className="mt-8 text-center">
          <p className="text-sm text-slate-400">{progressText}</p>
          {!allAgentsDone && (
            <div className="flex justify-center gap-1 mt-3">
              {[0, 1, 2].map((i) => (
                <motion.div key={i} animate={{ opacity: [0.3, 1, 0.3] }}
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

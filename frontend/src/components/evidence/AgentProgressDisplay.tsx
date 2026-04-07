"use client";

import React, { useState, useEffect, useRef, useMemo } from "react";
import { clsx } from "clsx";
import { 
  ChevronDown, 
  Loader2, 
  FileText, 
  ArrowRight, 
  Microscope, 
  RotateCcw,
  CheckCircle2
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { AGENTS_DATA } from "@/lib/constants";
import { SoundType } from "@/hooks/useSound";
import { Badge } from "@/components/ui/Badge";
import AnimatedWave from "@/components/ui/AnimatedWave";
import { AgentCard } from "./AgentCard";
export interface FindingPreview {
  tool: string;
  summary: string;
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
}: AgentProgressDisplayProps) {
  const [revealedAgents, setRevealedAgents] = useState<Set<string>>(new Set());
  const [unsupportedAgents, setUnsupportedAgents] = useState<Set<string>>(new Set());
  const [hiddenUnsupportedAgents, setHiddenUnsupportedAgents] = useState<Set<string>>(new Set());
  const [fadingOutAgents, setFadingOutAgents] = useState<Set<string>>(new Set());

  const baseVisibleAgents = useMemo(
    () => (phase === "deep" ? allValidAgents.filter((a) => !unsupportedAgents.has(a.id)) : allValidAgents),
    [phase, unsupportedAgents]
  );
  
  const visibleAgents = useMemo(
    () => baseVisibleAgents.filter((a) => !hiddenUnsupportedAgents.has(a.id)),
    [baseVisibleAgents, hiddenUnsupportedAgents]
  );

  useEffect(() => {
    setRevealedAgents(new Set());
    if (!visibleAgents.length) return;
    
    let idx = 0;
    const id = setInterval(() => {
      if (idx >= visibleAgents.length) {
        clearInterval(id);
        return;
      }
      const aid = visibleAgents[idx]?.id;
      if (aid) {
        setRevealedAgents((prev) => new Set([...prev, aid]));
        if (playSound) playSound(idx === 0 ? "scan" : "agent");
      }
      idx++;
    }, 100);
    return () => clearInterval(id);
  }, [phase, visibleAgents, playSound]);

  useEffect(() => {
    completedAgents.forEach((agent) => {
      const isUnsupported = agent.status === "skipped" || 
        (agent.error && /not applicable|not supported|skipping/i.test(agent.error));
      if (isUnsupported) {
        setUnsupportedAgents((prev) => new Set([...prev, agent.agent_id]));
      }
    });
  }, [completedAgents]);

  const hideTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  useEffect(() => {
    revealedAgents.forEach((id) => {
      if (unsupportedAgents.has(id) && !hideTimersRef.current.has(id)) {
        const timer = setTimeout(() => {
          setFadingOutAgents((prev) => new Set([...prev, id]));
          setTimeout(() => {
            setHiddenUnsupportedAgents((prev) => new Set([...prev, id]));
            setFadingOutAgents((prev) => {
              const next = new Set(prev);
              next.delete(id);
              return next;
            });
          }, 500);
        }, 8000);
        hideTimersRef.current.set(id, timer);
      }
    });
    return () => {
      hideTimersRef.current.forEach(clearTimeout);
      hideTimersRef.current.clear();
    };
  }, [revealedAgents, unsupportedAgents]);

  const getAgentStatus = (agentId: string) => {
    if (unsupportedAgents.has(agentId)) return "unsupported";
    const completed = completedAgents.find((c) => c.agent_id === agentId);
    if (completed) return completed.error ? "error" : "complete";
    if (agentUpdates[agentId]) return "running";
    if (revealedAgents.has(agentId)) return "checking";
    return "waiting";
  };

  const showInitialDecision = awaitingDecision && phase === "initial";
  const showDeepComplete = phase === "deep" && (allAgentsDone || pipelineStatus === "complete");

  return (
    <div className="flex flex-col items-center pt-8 relative min-h-[70vh] w-full max-w-7xl mx-auto px-4">
      {/* Background Ambience */}
      <div className="absolute inset-0 -z-10 pointer-events-none opacity-30">
        <AnimatedWave speed={0.005} waveColor="#22d3ee" wireframe opacity={0.5} />
      </div>

      {/* Header Info */}
      <motion.div 
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center mb-10 space-y-4"
      >
        <div className="inline-flex items-center gap-3 px-4 py-1.5 rounded-full bg-cyan-500/5 border border-cyan-500/20 text-cyan-400 font-mono text-[10px] font-black uppercase tracking-widest">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
          {completedAgents.length} / {allValidAgents.length} Agents Verified
        </div>
        <h2 className="text-3xl md:text-4xl font-black text-white tracking-tighter uppercase font-heading">
          {showInitialDecision ? "Analysis Concluded" : 
           showDeepComplete ? "Final Verdict Ready" : 
           phase === "deep" ? "Deep Forensic Analysis" : "Initial Forensic Scan"}
        </h2>
        <p className="text-white/40 text-xs font-medium max-w-lg mx-auto leading-relaxed">
          {progressText}
        </p>
      </motion.div>

      {/* Agent Grid */}
      <div className="w-full grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 mb-12">
        {visibleAgents.map((agent) => (
          <AgentCard
            key={agent.id}
            agentId={agent.id}
            name={agent.name}
            badge={agent.badge}
            status={getAgentStatus(agent.id)}
            thinking={agentUpdates[agent.id]?.thinking}
            completedData={completedAgents.find((c) => c.agent_id === agent.id)}
            isRevealed={revealedAgents.has(agent.id)}
            isFadingOut={fadingOutAgents.has(agent.id)}
          />
        ))}
      </div>

      {/* Decision Buttons */}
      <AnimatePresence>
        {(showInitialDecision || showDeepComplete) && (
          <motion.div 
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="w-full max-w-4xl mx-auto"
          >
            <div className="glass-panel rounded-3xl p-8 border-white/10 shadow-[0_0_50px_rgba(0,0,0,0.5)]">
              <div className="flex flex-col md:flex-row items-center justify-between gap-8">
                <div className="text-center md:text-left space-y-1">
                  <h3 className="text-xl font-black text-white uppercase font-heading tracking-tight">
                    {showInitialDecision ? "Select Investigation Depth" : "Analysis Complete"}
                  </h3>
                  <p className="text-white/30 text-xs font-medium">
                    {showInitialDecision 
                      ? "Choose to finalize this report or proceed for a deeper ML pass." 
                      : "Evidence has been processed by the council. Ready for sign-off."}
                  </p>
                </div>

                <div className="flex flex-col sm:flex-row gap-4 w-full md:w-auto">
                  {showInitialDecision ? (
                    <>
                      <button
                        onClick={onAcceptAnalysis}
                        disabled={isNavigating}
                        className="btn-pill-secondary px-8 py-4 gap-3 bg-white/5 hover:bg-white/10 border-white/10 text-white/70"
                      >
                        {isNavigating ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
                        Accept Analysis
                      </button>
                      <button
                        onClick={onDeepAnalysis}
                        disabled={isNavigating}
                        className="btn-pill-primary px-8 py-4 gap-3 shadow-[0_0_30px_rgba(34,211,238,0.2)]"
                      >
                        <Microscope className="w-4 h-4" />
                        Deep Analysis
                        <ArrowRight className="w-4 h-4" />
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        onClick={onNewUpload}
                        className="btn-pill-secondary px-8 py-4 gap-3 bg-white/5 hover:bg-white/10 border-white/10 text-white/50"
                      >
                        <RotateCcw className="w-4 h-4" />
                        New Analysis
                      </button>
                      <button
                        onClick={onViewResults}
                        disabled={isNavigating}
                        className="btn-pill-primary px-10 py-4 gap-3 shadow-[0_0_40px_rgba(34,211,238,0.3)]"
                      >
                        {isNavigating ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                        Access Ledger
                        <ArrowRight className="w-4 h-4" />
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Skipped Agents Sub-menu */}
      {hiddenUnsupportedAgents.size > 0 && (
        <SkippedAgentsPanel hidden={hiddenUnsupportedAgents} />
      )}
    </div>
  );
}

function SkippedAgentsPanel({ hidden }: { hidden: Set<string> }) {
  const [show, setShow] = useState(false);
  return (
    <div className="mt-12 flex flex-col items-center gap-4">
      <button 
        onClick={() => setShow(!show)}
        className="group flex items-center gap-2 px-5 py-2 rounded-full border border-white/5 bg-white/[0.02] hover:bg-white/[0.05] transition-all text-[9px] font-black text-white/30 uppercase tracking-[0.3em] font-mono"
      >
        <span>{hidden.size} Units Incompatible</span>
        <ChevronDown className={clsx("w-3 h-3 transition-transform duration-300", show && "rotate-180")} />
      </button>
      <AnimatePresence>
        {show && (
          <motion.div 
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="w-full max-w-sm overflow-hidden"
          >
            <div className="grid grid-cols-1 gap-2 p-4 rounded-2xl bg-white/[0.01] border border-white/5">
              {Array.from(hidden).map((id) => {
                const agent = AGENTS_DATA.find(a => a.id === id);
                return (
                  <div key={id} className="flex items-center justify-between px-3 py-2 rounded-lg bg-white/[0.02]">
                    <span className="text-xs text-white/40 font-medium">{agent?.name}</span>
                    <span className="text-[8px] font-mono text-white/10 uppercase font-black">Skipped</span>
                  </div>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

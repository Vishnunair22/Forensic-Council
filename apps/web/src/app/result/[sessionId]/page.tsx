"use client";

import React from "react";
import { motion } from "framer-motion";
import { useResult } from "@/hooks/useResult";
import { GlassPanel } from "@/components/ui/GlassPanel";
import { AgentFindingCard } from "@/components/ui/AgentFindingCard";
import { ForensicProgressOverlay } from "@/components/ui/ForensicProgressOverlay";
import { Shield, Activity, CheckCircle2, AlertTriangle, Cpu, Scale } from "lucide-react";

interface ResultPageProps {
  params: Promise<{ sessionId: string }>;
}

export default function DynamicResultPage({ params }: ResultPageProps) {
  const resolvedParams = React.use(params);
  const sessionId = resolvedParams.sessionId;
  
  const rs = useResult(sessionId);

  if (!rs.mounted) return null;

  const isPending = rs.state === "arbiter" || rs.state === "loading";

  // Get the verdict configuration
  const verdict = rs.report?.overall_verdict || "INCONCLUSIVE";
  const isAuthentic = verdict === "AUTHENTIC";
  const isManipulated = verdict === "MANIPULATED";

  return (
    <main className="relative min-h-screen px-6 py-32 mx-auto max-w-5xl space-y-12 overflow-x-hidden">
      {/* Background Glow */}
      <div className="absolute top-[-20%] right-[-10%] w-[50%] h-[50%] bg-primary/5 blur-[150px] rounded-full pointer-events-none -z-10" />
      
      {isPending && (
        <ForensicProgressOverlay
          title={rs.state === "arbiter" ? "Neural Synthesis" : "Intake Verification"}
          liveText={rs.arbiterMsg || "Polling operational diagnostics..."}
          telemetryLabel="Analyzing Artifact Layers"
          showElapsed
        />
      )}

      {/* Verdict Banner */}
      {rs.state === "ready" && rs.report && (
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
        >
          <GlassPanel
            className={`p-10 rounded-[2.5rem] border-2 flex flex-col md:flex-row items-center gap-8 justify-between shadow-2xl relative overflow-hidden ${
              isAuthentic
                ? "border-primary/20 bg-primary/[0.03]"
                : isManipulated
                ? "border-red-500/20 bg-red-500/[0.03]"
                : "border-white/5 bg-[#020203]/60"
            }`}
            data-testid="result-verdict-banner"
          >
            {/* Decorative background icon */}
            <div className="absolute -right-8 -bottom-8 opacity-[0.03] pointer-events-none">
              {isAuthentic ? <CheckCircle2 className="w-48 h-48" /> : <Shield className="w-48 h-48" />}
            </div>

            <div className="flex items-center gap-6 relative z-10">
              <div
                className={`w-20 h-20 rounded-3xl flex items-center justify-center border-2 shadow-[0_0_40px_rgba(0,0,0,0.3)] ${
                  isAuthentic
                    ? "border-primary/30 bg-primary/10 text-primary shadow-[0_0_30px_rgba(var(--color-primary-rgb),0.2)]"
                    : isManipulated
                    ? "border-red-500/30 bg-red-500/10 text-red-400 shadow-[0_0_30px_rgba(239,68,68,0.2)]"
                    : "border-white/10 bg-white/5 text-white/40"
                }`}
              >
                {isAuthentic ? (
                  <CheckCircle2 className="w-10 h-10" />
                ) : isManipulated ? (
                  <AlertTriangle className="w-10 h-10" />
                ) : (
                  <Shield className="w-10 h-10" />
                )}
              </div>
              <div className="space-y-2 text-center md:text-left">
                <div className="flex items-center gap-2 justify-center md:justify-start">
                  <span className="text-[10px] uppercase font-mono font-black tracking-[0.3em] text-white/30">
                    Forensic_Verdict
                  </span>
                  <div className={`w-1 h-1 rounded-full ${isAuthentic ? 'bg-primary' : isManipulated ? 'bg-red-500' : 'bg-white/20'}`} />
                </div>
                <h2 className="text-4xl md:text-5xl font-black tracking-tighter text-white leading-none">
                  {verdict}
                </h2>
              </div>
            </div>

            <div className="flex flex-col items-center md:items-end gap-2 text-center md:text-right font-mono relative z-10">
              <span className="text-[10px] text-white/20 font-black tracking-widest uppercase">
                Session_ID
              </span>
              <span className="text-xs text-primary/60 font-black tracking-wider bg-primary/5 px-3 py-1 rounded-full border border-primary/10">
                {sessionId.slice(0, 18)}...
              </span>
            </div>
          </GlassPanel>
        </motion.div>
      )}

      {/* Agent Finding Cards Surface */}
      {rs.state === "ready" && rs.report && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3, duration: 0.8 }}
          className="space-y-10"
        >
          <div className="flex items-center justify-between border-b border-white/5 pb-4 px-2">
            <div className="flex items-center gap-3">
              <Activity className="w-4 h-4 text-primary" />
              <span className="text-[10px] uppercase tracking-[0.3em] font-mono font-black text-white/40">
                Autonomous_Modal_Protocols
              </span>
            </div>
            <div className="flex gap-4 opacity-20 hidden md:flex">
               <Cpu className="w-3 h-3" />
               <Scale className="w-3 h-3" />
               <Shield className="w-3 h-3" />
            </div>
          </div>

          <div className="grid gap-6">
            {Object.keys(rs.report.per_agent_findings || {}).map((agentId) => (
              <motion.div
                key={agentId}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5 }}
                data-testid={`result-finding-card-${agentId}`}
              >
                <AgentFindingCard
                  agentId={agentId}
                  initialFindings={rs.report?.per_agent_findings[agentId] || []}
                  deepFindings={[]}
                  metrics={rs.report?.per_agent_metrics[agentId]}
                  narrative={rs.report?.per_agent_analysis[agentId]}
                  phase={rs.isDeepPhase ? "deep" : "initial"}
                  defaultOpen={false}
                />
              </motion.div>
            ))}
          </div>
        </motion.div>
      )}

      {rs.state === "error" && (
        <GlassPanel className="p-16 text-center rounded-[2.5rem] border-2 border-red-500/20 bg-red-500/[0.03] space-y-6 shadow-2xl">
          <div className="w-20 h-20 rounded-3xl bg-red-500/10 border border-red-500/20 flex items-center justify-center mx-auto shadow-[0_0_30px_rgba(239,68,68,0.1)]">
            <AlertTriangle className="w-10 h-10 text-red-500 animate-pulse" />
          </div>
          <div className="space-y-3">
            <h3 className="text-2xl font-black text-white tracking-tighter uppercase">
              Pipeline_Degradation
            </h3>
            <p className="text-sm text-white/40 max-w-sm mx-auto leading-relaxed font-medium">
              {rs.errorMsg || "The forensic synthesis pipeline encountered an unrecoverable state violation."}
            </p>
          </div>
          <button 
            onClick={() => window.location.reload()}
            className="px-8 py-3 rounded-full bg-white/5 border border-white/10 text-white text-[10px] font-black uppercase tracking-widest hover:bg-white/10 transition-all"
          >
            [ Restart_Synthesis ]
          </button>
        </GlassPanel>
      )}
    </main>
  );
}

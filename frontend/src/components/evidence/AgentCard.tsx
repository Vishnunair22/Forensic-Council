"use client";

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  CheckCircle2, 
  Loader2, 
  AlertTriangle, 
  Clock, 
  Wrench,
  ChevronRight,
} from "lucide-react";
import { clsx } from "clsx";
import { AgentIcon } from "@/components/ui/AgentIcon";
import { Badge } from "@/components/ui/Badge";
import { fmtTool } from "@/lib/fmtTool";
import type { AgentUpdate, FindingPreview } from "./AgentProgressDisplay";

interface AgentCardProps {
  agentId: string;
  name: string;
  badge: string;
  status: "waiting" | "checking" | "running" | "complete" | "error" | "unsupported";
  thinking?: string;
  completedData?: AgentUpdate;
  isRevealed: boolean;
  isFadingOut?: boolean;
}

const statusConfig = {
  waiting: { color: "text-slate-500", bg: "bg-slate-500/5", border: "border-slate-500/10", label: "Queued" },
  checking: { color: "text-cyan-400", bg: "bg-cyan-500/5", border: "border-cyan-500/20", label: "Linking" },
  running: { color: "text-cyan-400", bg: "bg-cyan-500/10", border: "border-cyan-500/30", label: "Analysing" },
  complete: { color: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/20", label: "Success" },
  error: { color: "text-rose-400", bg: "bg-rose-500/10", border: "border-rose-500/20", label: "Failed" },
  unsupported: { color: "text-slate-500", bg: "bg-slate-500/5", border: "border-slate-500/10", label: "N/A" },
};

export function AgentCard({
  agentId,
  name,
  badge,
  status,
  thinking,
  completedData,
  isRevealed,
  isFadingOut,
}: AgentCardProps) {
  const config = statusConfig[status];

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.95, y: 10 }}
      animate={{ 
        opacity: isFadingOut ? 0 : isRevealed ? (status === "waiting" ? 0.5 : 1) : 0,
        scale: isFadingOut ? 0.9 : 1,
        y: 0,
      }}
      transition={{ duration: 0.4, ease: [0.23, 1, 0.32, 1] }}
      className={clsx(
        "group relative flex flex-col h-full rounded-2xl border transition-all duration-500 overflow-hidden glass-panel",
        config.border,
        status === "running" && "shadow-[0_0_40px_rgba(34,211,238,0.12)]",
        status === "complete" && "shadow-[0_0_20px_rgba(52,211,153,0.04)]",
      )}
      role="listitem"
      aria-label={`${name}: ${config.label}`}
      aria-live="polite"
    >
      {/* Premium Glow effect */}
      <div className="absolute inset-0 bg-gradient-to-br from-white/[0.03] via-transparent to-transparent pointer-events-none" />
      
      {/* Animated Status Bar */}
      <AnimatePresence mode="popLayout">
        <motion.div
          key={status}
          initial={{ scaleX: 0 }}
          animate={{ scaleX: 1 }}
          className={clsx(
            "absolute top-0 left-0 right-0 h-[2px] origin-left z-20",
            status === "running" ? "bg-cyan-400" : 
            status === "complete" ? "bg-emerald-400" :
            status === "error" ? "bg-rose-400" : "bg-white/10"
          )}
          style={{
            boxShadow: status === "running" ? "0 0 12px rgba(34,211,238,0.8)" : "none"
          }}
        />
      </AnimatePresence>

      {/* Header */}
      <div className="p-5 flex items-center gap-4 border-b border-white/[0.04]">
        <div 
          className={clsx(
            "w-12 h-12 rounded-xl flex items-center justify-center shrink-0 border transition-colors duration-500",
            status === "running" ? "bg-cyan-500/10 border-cyan-500/30 text-cyan-400" : "bg-white/5 border-white/10 text-white/30"
          )}
        >
          <AgentIcon agentId={agentId} className="w-7 h-7" />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-bold text-white uppercase tracking-tight font-heading">
            {name}
          </h3>
          <span className="text-[10px] uppercase font-mono font-bold tracking-[0.2em] text-white/30">
            {badge}
          </span>
        </div>
        <div className="shrink-0 flex flex-col items-end gap-1">
          <Badge 
            variant="outline" 
            className={clsx(
              "text-[9px] font-black uppercase tracking-widest font-mono border-none px-2 py-0.5 rounded-full",
              config.bg, config.color
            )}
          >
            {status === "running" && <Loader2 className="w-2.5 h-2.5 animate-spin mr-1" />}
            {status === "complete" && <CheckCircle2 className="w-2.5 h-2.5 mr-1" />}
            {config.label}
          </Badge>
          {completedData?.completed_at && (
            <span className="text-[8px] font-mono text-white/20 uppercase">
              {new Date(completedData.completed_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
        </div>
      </div>

      {/* Content Area */}
      <div className="p-5 flex-1 flex flex-col gap-4">
        {/* Real-time Thinking */}
        {(status === "running" || status === "checking") && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <span className="w-1 h-1 rounded-full bg-cyan-400 animate-pulse" />
              <p className="text-[11px] font-mono text-cyan-400/80 leading-relaxed italic">
                {thinking || "Initializing..."}
              </p>
            </div>
            {/* Progress Bar Mockup/Real */}
            <div className="h-1 bg-white/5 rounded-full overflow-hidden">
              <motion.div 
                className="h-full bg-cyan-500/50"
                initial={{ width: 0 }}
                animate={{ width: "65%" }}
                transition={{ duration: 2, repeat: Infinity, repeatType: "reverse" }}
              />
            </div>
          </div>
        )}

        {/* Results / Findings Preview */}
        {status === "complete" && completedData && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-2">
              <div className="bg-white/[0.02] border border-white/[0.05] rounded-lg p-2 text-center">
                <span className="block text-[8px] uppercase tracking-widest text-white/30 font-bold mb-1">Tools</span>
                <span className="text-xs font-mono font-bold text-white">{completedData.tools_ran || 0}</span>
              </div>
              <div className="bg-white/[0.02] border border-white/[0.05] rounded-lg p-2 text-center">
                <span className="block text-[8px] uppercase tracking-widest text-white/30 font-bold mb-1">Findings</span>
                <span className="text-xs font-mono font-bold text-white">{completedData.findings_count || 0}</span>
              </div>
            </div>

            {completedData.findings_preview && completedData.findings_preview.length > 0 && (
              <div className="space-y-2">
                <p className="text-[9px] font-black uppercase tracking-[0.15em] text-white/20">Key Signals</p>
                <div className="space-y-1.5">
                  {completedData.findings_preview.slice(0, 2).map((finding, i) => (
                    <div key={i} className="flex items-start gap-2 group/tool">
                      <ChevronRight className="w-3 h-3 text-cyan-500/50 mt-0.5 shrink-0" />
                      <p className="text-[10px] text-white/60 leading-tight">
                        <span className="font-bold text-cyan-300/80 mr-1">{fmtTool(finding.tool)}:</span>
                        {finding.summary}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Error State */}
        {status === "error" && (
          <div className="flex flex-col items-center justify-center py-4 text-center gap-2">
            <AlertTriangle className="w-8 h-8 text-rose-500/50" />
            <p className="text-xs text-rose-400/80 font-mono italic">
              {completedData?.error || "Critical agent failure"}
            </p>
          </div>
        )}

        {/* Unsupported State */}
        {status === "unsupported" && (
          <div className="flex flex-col items-center justify-center py-4 text-center gap-2">
            <div className="text-white/10 uppercase font-mono text-[10px] tracking-widest">
              Standard format required
            </div>
            <p className="text-[10px] text-white/30 italic">
              Evidence type not applicable for this agent.
            </p>
          </div>
        )}
        
        {/* Placeholder for idle/waiting */}
        {status === "waiting" && (
          <div className="space-y-2 opacity-20">
            <div className="h-2 w-full bg-white/20 rounded-full" />
            <div className="h-2 w-3/4 bg-white/20 rounded-full" />
            <div className="h-2 w-1/2 bg-white/20 rounded-full" />
          </div>
        )}
      </div>

      {/* Footer Metrics */}
      {status === "complete" && completedData && (
        <div className="px-5 py-3 border-t border-white/[0.04] bg-white/[0.01] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex flex-col">
              <span className="text-[8px] uppercase tracking-tighter text-white/30">Verdict</span>
              <span 
                className={clsx(
                  "text-[10px] font-black uppercase tracking-tight",
                  completedData.agent_verdict === "AUTHENTIC" ? "text-emerald-400" :
                  completedData.agent_verdict === "LIKELY_MANIPULATED" ? "text-rose-400" : "text-amber-400"
                )}
              >
                {completedData.agent_verdict || "Inconclusive"}
              </span>
            </div>
          </div>
          <div className="text-right">
            <span className="text-[8px] uppercase tracking-tighter text-white/30 block">Confidence</span>
            <span className="text-[10px] font-mono font-bold text-white">
              {Math.round((completedData.confidence || 0) * 100)}%
            </span>
          </div>
        </div>
      )}
    </motion.div>
  );
}

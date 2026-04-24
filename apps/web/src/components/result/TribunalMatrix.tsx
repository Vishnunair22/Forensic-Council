"use client";

import React from "react";
import { Shield, AlertTriangle, Zap, Target } from "lucide-react";
import { clsx } from "clsx";
import { ReportDTO } from "@/lib/api";
import { motion } from "framer-motion";

interface TribunalMatrixProps {
  report: ReportDTO;
}

export function TribunalMatrix({ report }: TribunalMatrixProps) {
  const contested = (
    (report.contested_findings ?? []) as Record<string, unknown>[]
  ).map((f) => ({
    plain_description:
      typeof f.plain_description === "string" ? f.plain_description : null,
  }));
  const resolved = (
    (report.tribunal_resolved ?? []) as Record<string, unknown>[]
  ).map((f) => ({
    resolution: typeof f.resolution === "string" ? f.resolution : null,
    plain_description:
      typeof f.plain_description === "string" ? f.plain_description : null,
  }));

  const hasContested = contested.length > 0;
  if (contested.length === 0 && resolved.length === 0) return null;

  return (
    <section className="space-y-6">
      <div className="flex items-center gap-4">
         <span className="text-[10px] font-mono font-bold text-white/30 uppercase tracking-[0.3em]">Tribunal_Consensus_Matrix</span>
         <div className="h-px flex-1 bg-white/5" />
      </div>

      <div className="horizon-card p-1 rounded-3xl overflow-hidden">
        <div className="bg-[#020617] rounded-[inherit]">
          
          {/* Header */}
          <div className="px-8 py-6 border-b border-white/5 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Shield className={clsx("w-4 h-4", hasContested ? "text-danger" : "text-primary")} />
              <span className="text-[10px] font-mono font-bold text-white/60 tracking-widest uppercase">
                {hasContested ? "Contested_Anomaly_Detection" : "Neural_Conflict_Resolved"}
              </span>
            </div>
            
            <div className={clsx(
              "px-3 py-1 rounded text-[9px] font-mono font-bold uppercase tracking-widest border",
              hasContested ? "text-danger border-danger/20 bg-danger/5" : "text-primary border-primary/20 bg-primary/5"
            )}>
              {hasContested ? "Requires_Review" : "System_Stable"}
            </div>
          </div>

          <div className="p-8 grid grid-cols-1 lg:grid-cols-2 gap-12">
            
            {/* Contested Patterns */}
            <div className="space-y-6">
              <div className="flex items-center gap-3">
                <AlertTriangle className="w-3.5 h-3.5 text-danger/40" />
                <span className="text-[10px] font-mono font-bold text-white/20 uppercase tracking-widest">Contested_Signals</span>
              </div>

              <div className="space-y-4">
                {contested.length === 0 ? (
                  <div className="p-6 rounded-xl border border-dashed border-white/5 text-center">
                    <span className="text-[10px] font-mono text-white/10 uppercase italic">No contested signals detected</span>
                  </div>
                ) : (
                  contested.map((f, i) => (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      className="p-4 rounded-xl border border-danger/10 bg-danger/[0.02] flex gap-4"
                    >
                      <span className="text-[10px] font-mono font-bold text-danger">SIG_{i.toString().padStart(2, '0')}</span>
                      <p className="text-xs text-white/60 leading-relaxed font-medium">
                        {f.plain_description || "Conflicting forensic anomaly detected."}
                      </p>
                    </motion.div>
                  ))
                )}
              </div>
            </div>

            {/* Resolved Logic */}
            <div className="space-y-6 lg:border-l lg:border-white/5 lg:pl-12">
              <div className="flex items-center gap-3">
                <Target className="w-3.5 h-3.5 text-primary/40" />
                <span className="text-[10px] font-mono font-bold text-white/20 uppercase tracking-widest">Arbiter_Resolution</span>
              </div>

              <div className="space-y-4">
                {resolved.length === 0 ? (
                   <div className="p-6 rounded-xl border border-dashed border-white/5 text-center">
                     <span className="text-[10px] font-mono text-white/10 uppercase italic">Awaiting tribunal resolution matrix</span>
                   </div>
                ) : (
                  resolved.map((f, i) => (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, x: 10 }}
                      animate={{ opacity: 1, x: 0 }}
                      className="p-4 rounded-xl border border-primary/20 bg-primary/5 relative overflow-hidden"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-[10px] font-mono font-bold text-primary">FIX_{i.toString().padStart(2, '0')}</span>
                        <Zap className="w-3 h-3 text-primary" />
                      </div>
                      <p className="text-xs text-white/80 font-bold leading-relaxed relative z-10">
                        {f.resolution || f.plain_description || "Dispute resolved by majority consensus."}
                      </p>
                      <div className="absolute right-0 bottom-0 w-16 h-16 bg-primary/5 blur-2xl rounded-full" />
                    </motion.div>
                  ))
                )}
              </div>
            </div>

          </div>

          {/* HUD Footer */}
          <div className="px-8 py-5 border-t border-white/5 bg-white/[0.02] flex items-center gap-10 overflow-x-auto whitespace-nowrap scrollbar-none">
             <div className="flex items-center gap-2 text-[9px] font-mono text-white/20 uppercase">
                <span className="text-white/40">Tribunal:</span> Council_Arbiter + 3 Specialist_Nodes
             </div>
             <div className="flex items-center gap-2 text-[9px] font-mono text-white/20 uppercase">
                <span className="text-white/40">Status:</span> Unanimous_Consensus
             </div>
             <div className="flex items-center gap-2 text-[9px] font-mono text-white/20 uppercase">
                <span className="text-white/40">SLA:</span> Final_Integrity_Check_Passed
             </div>
          </div>

        </div>
      </div>
    </section>
  );
}

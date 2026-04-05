"use client";

import React from "react";
import { Shield, AlertTriangle, Zap, Target } from "lucide-react";
import { ReportDTO } from "@/lib/api";

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

  if (contested.length === 0 && resolved.length === 0) return null;

  return (
    <div className="rounded-2xl overflow-hidden glass-panel border border-amber-500/10 bg-amber-500/[0.01]">
      <div className="px-5 py-3.5 border-b border-white/[0.05] bg-white/[0.02] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Shield className="w-3.5 h-3.5 text-amber-400" />
          <span className="text-[10px] font-bold uppercase tracking-widest text-foreground/60">
            Tribunal Consensus Matrix
          </span>
        </div>
        <span className="text-[8px] font-mono font-black text-amber-500/50 uppercase tracking-widest">
          Dispute Resolution Active
        </span>
      </div>
      <div className="p-5 space-y-4">
        {/* Contested Findings List */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-3">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="w-3 h-3 text-rose-500" />
              <span className="text-[9px] font-bold uppercase text-foreground/40 tracking-wider">
                Disputed Logic Patterns
              </span>
            </div>
            <div className="space-y-2">
              {contested.length === 0 ? (
                <p className="text-[10px] text-foreground/20 font-mono italic">
                  No contested findings currently in record.
                </p>
              ) : (
                contested.map((f, i) => (
                  <div
                    key={i}
                    className="p-3 rounded-xl bg-rose-500/[0.05] border border-rose-500/10 flex items-start gap-3"
                  >
                    <span className="text-[10px] font-mono text-rose-400 font-bold">
                      #0{i + 1}
                    </span>
                    <p className="text-[10px] text-foreground/60 leading-relaxed font-medium">
                      {f.plain_description ||
                        "Conflicting forensic anomaly detected."}
                    </p>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="space-y-3 border-l border-white/[0.05] pl-4">
            <div className="flex items-center gap-2 mb-2">
              <Target className="w-3 h-3 text-emerald-400" />
              <span className="text-[9px] font-bold uppercase text-foreground/40 tracking-wider">
                Final Arbiter Resolutions
              </span>
            </div>
            <div className="space-y-2">
              {resolved.length === 0 ? (
                <p className="text-[10px] text-foreground/20 font-mono italic">
                  Awaiting tribunal resolution matrix...
                </p>
              ) : (
                resolved.map((f, i) => (
                  <div
                    key={i}
                    className="p-3 rounded-xl bg-emerald-500/[0.05] border border-emerald-500/10 space-y-1.5 relative overflow-hidden"
                  >
                    <div className="flex items-center justify-between relative z-10">
                      <span className="text-[9px] font-mono font-black text-emerald-400 tracking-tighter uppercase whitespace-nowrap">
                        Resolution Applied
                      </span>
                      <Zap className="w-3 h-3 text-emerald-400" />
                    </div>
                    <p className="text-[10px] text-foreground/70 leading-relaxed font-bold relative z-10 transition-colors">
                      {f.resolution ||
                        f.plain_description ||
                        "Dispute resolved by majority consensus."}
                    </p>
                    <div className="absolute right-0 bottom-0 w-24 h-24 bg-emerald-500/[0.03] blur-3xl rounded-full" />
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Status indicator bar */}
        <div className="mt-4 flex items-center gap-4 text-[8px] font-mono text-foreground/30 border-t border-white/[0.03] pt-4">
          <span>TRIBUNAL SEATS: COUNCIL_ARBITER + 3 SPECIALISTS</span>
          <span>VOTE STATUS: UNANIMOUS CONSENSUS</span>
          <span>SLA: COMPLETED_INTERNAL</span>
        </div>
      </div>
    </div>
  );
}

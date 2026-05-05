"use client";

import React from "react";
import { Cpu, Zap } from "lucide-react";
import { ReportDTO } from "@/lib/api";

interface DeepModelTelemetryProps {
 report: ReportDTO;
}

const TOOL_LABELS: Record<string, string> = {
  neural_copy_move: "BusterNet-V2 (SOTA)",
  neural_splicing: "TruFor Transformer",
  anomaly_tracer: "ManTra-Net Tracer",
  f3_net_frequency: "F3-Net Frequency",
  neural_ela: "Neural ELA (ViT-L)",
  diffusion_artifact_detector: "Diffusion Discriminator",
  gemini_deep_forensic: "Gemini 2.5 Multi-Modal",
};

export function DeepModelTelemetry({ report }: DeepModelTelemetryProps) {
 // Extract findings that occurred in the deep phase
 const allFindings = Object.values(report.per_agent_findings || {}).flat();
 const deepFindings = allFindings.filter(
  (f) => (f.metadata as Record<string, unknown>)?.analysis_phase === "deep",
 );

 if (deepFindings.length === 0) return null;

 // Extract unique "tools/models" from deep findings
 const models = Array.from(new Set(deepFindings.map((f) => f.finding_type)));

 return (
  <div className="bg-[#070A12] border border-violet-500/20 rounded-2xl shadow-[0_4px_24px_rgba(0,0,0,0.5),0_1px_0_rgba(255,255,255,0.04)_inset] overflow-hidden">
   <div className="px-5 py-3.5 border-b border-white/[0.05] bg-white/[0.02] flex items-center justify-between">
    <div className="flex items-center gap-2">
     <Cpu className="w-3.5 h-3.5 text-violet-400" />
     <span className="text-[10px] font-bold tracking-wide text-foreground/60">
      Deep Model Telemetry
     </span>
    </div>
    <div className="flex items-center gap-1.5">
     <div className="w-1.5 h-1.5 rounded-full bg-violet-500 animate-pulse" />
     <span className="text-[10px] font-mono font-bold text-violet-400/70 tracking-tighter">
      Heavy-Compute Active
     </span>
    </div>
   </div>
   <div className="p-5">
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
     {models.slice(0, 6).map((model, idx) => {
      const count = deepFindings.filter(
       (f) => f.finding_type === model,
      ).length;
      const avgConf = Math.round(
       (deepFindings
        .filter((f) => f.finding_type === model)
        .reduce((acc, f) => acc + (f.raw_confidence_score || 0), 0) /
        count) *
        100,
      );

      return (
       <div
        key={idx}
        className="p-3 rounded-xl bg-black/20 border border-white/[0.03] space-y-2 relative overflow-hidden group"
       >
        <div className="flex items-center justify-between relative z-10">
         <div className="flex items-center gap-2">
          <Zap className="w-3 h-3 text-violet-400/50" />
          <span className="text-[10px] font-mono text-foreground/70 font-bold truncate max-w-[150px]">
           {TOOL_LABELS[model] || model.replace(/_/g, " ").toUpperCase()}
          </span>
         </div>
         <span className="text-[10px] font-mono text-violet-400 font-black">
          {avgConf}%
         </span>
        </div>
        <div className="h-1 w-full bg-white/[0.05] rounded-full overflow-hidden relative z-10">
         <div
          className="h-full bg-gradient-to-r from-violet-600 to-indigo-400 transition-all duration-1000"
          style={{ width: `${avgConf}%` }}
          role="progressbar"
          aria-valuenow={avgConf}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`${model} confidence`}
         />
        </div>
        <div className="flex justify-between items-center text-[10px] font-mono text-foreground/30 relative z-10">
         <span>LOGIC: {model.startsWith("neural_") || model === "anomaly_tracer" ? "TRANSFORMER_V2" : "TENSOR_V4"}</span>
         <span>INVOCATIONS: {count}</span>
        </div>
        <div className="absolute -right-4 -bottom-4 w-12 h-12 bg-violet-600/10 blur-2xl rounded-full group-hover:bg-violet-600/20 transition-colors" />
       </div>
      );
     })}
    </div>
   </div>
  </div>
 );
}

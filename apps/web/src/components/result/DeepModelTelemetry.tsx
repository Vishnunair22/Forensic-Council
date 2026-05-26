"use client";

import React from "react";
import { Cpu } from "lucide-react";
import { motion } from "framer-motion";
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
  const allFindings = Object.values(report.per_agent_findings ?? {}).flat();
  const deepFindings = allFindings.filter(
    (f) => f != null && (f.metadata as Record<string, unknown>)?.analysis_phase === "deep",
  );

  if (deepFindings.length === 0) return null;
  if (!report.cross_modal_fusion || Object.keys(report.cross_modal_fusion).length === 0) return null;

  const models = Array.from(
    new Set(deepFindings.map((f) => f.finding_type).filter(Boolean))
  );

  return (
    <div className="relative flex flex-col overflow-hidden fc-surface">
      {/* Header */}
      <div className="px-5 py-3.5 border-b border-white/[0.06] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Cpu className="w-3.5 h-3.5 text-primary/60" />
          <span className="fc-eyebrow fc-text-muted">
            Deep Model Telemetry
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <div
            className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse"
          />
          <span className="fc-eyebrow fc-text-muted">
            Heavy-Compute Active
          </span>
        </div>
      </div>

      {/* Elevated Model Rows */}
      <div className="p-6 bg-[radial-gradient(ellipse_at_top,rgba(255,255,255,0.02),transparent_50%)]">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-8 gap-y-6">
          {models.slice(0, 6).map((model, index) => {
            const modelFindings = deepFindings.filter((f) => f.finding_type === model);
            const count = modelFindings.length;
            const avgConf = Math.round(
              (modelFindings.reduce((acc, f) => acc + (f.raw_confidence_score ?? f.confidence_raw ?? 0), 0) / count) * 100,
            );

            const totalBlocks = 25;
            const activeBlocks = Math.round((avgConf / 100) * totalBlocks);

            return (
              <motion.div
                key={model}
                initial={{ opacity: 0, y: 5 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.05 }}
                className="space-y-3 relative group"
              >
                <div className="absolute -inset-x-3 -inset-y-2 border border-white/0 group-hover:border-white/5 bg-transparent group-hover:bg-white/[0.01] rounded-lg transition-all pointer-events-none" />

                <div className="flex items-center justify-between relative z-10">
                  <div className="flex items-center gap-2.5">
                    <div className="w-1.5 h-1.5 rounded-sm bg-primary/40 group-hover:bg-primary transition-colors" />
                    <span className="text-xs font-mono text-white/90 tracking-widest uppercase">
                      {TOOL_LABELS[model] || model.replace(/_/g, " ").toUpperCase()}
                    </span>
                  </div>
                  <span className="text-sm font-mono font-black text-primary drop-shadow-[0_0_5px_rgba(var(--color-primary-rgb),0.5)]">
                    {avgConf}%
                  </span>
                </div>

                {/* Segmented Neural Activation Bar */}
                <div className="flex gap-[2px] h-2 w-full relative z-10" aria-label={`${model} confidence`}>
                  {Array.from({ length: totalBlocks }).map((_, i) => (
                    <div
                      key={i}
                      className="flex-1 rounded-sm transition-all duration-300"
                      style={{
                        backgroundColor: i < activeBlocks
                          ? `rgba(var(--color-primary-rgb), ${0.4 + (i / totalBlocks) * 0.6})`
                          : 'rgba(255,255,255,0.05)',
                        boxShadow: 'none',
                      }}
                    />
                  ))}
                </div>

                <div className="flex justify-between items-center text-xs font-mono fc-text-muted uppercase tracking-widest relative z-10">
                  <span>
                    {model.startsWith("neural_") || model === "anomaly_tracer" ? "Transformer V2" : "Tensor V4"}
                  </span>
                  <span>{count} INVOCATION{count !== 1 ? "S" : ""}</span>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
